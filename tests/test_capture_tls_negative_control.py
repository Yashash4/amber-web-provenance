"""Negative-control TLS tests for the Bright Data proxy adapter (FIX 3).

The forensic claim rests on "verification stays ON": the residential capture's
intercepted CONNECT tunnel is validated against the committed Bright Data CA +
the system roots, with ``check_hostname`` and ``CERT_REQUIRED`` kept on; only
OpenSSL's strict X.509 extension-presence flag is relaxed. The docstrings have
always promised that a leaf which does NOT chain to a trusted root — or whose
hostname is wrong, or which is expired — still fails the handshake. This file is
that promise's regression guard: it runs REAL in-process TLS handshakes through
the EXACT context :class:`amber.capture.brightdata._BrightDataTLSAdapter` builds
and asserts each forgery is REJECTED while a cert chaining to the trusted CA is
ACCEPTED.

To exercise the adapter's own ``_build_context`` (same flags, same hostname +
CERT_REQUIRED settings) without Bright Data's private key, we substitute a
locally-generated test CA for the committed BD CA via the module's cached CA
accessor. The leaf certs are minted locally with ``cryptography``. Nothing here
touches the network or the real BD CA's trust beyond the pin test.
"""

from __future__ import annotations

import datetime as dt
import socket
import ssl
import threading

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from amber.capture import brightdata

_LEAF_HOST = "geo.brdtest.com"


# --------------------------------------------------------------------------- #
# Local cert factory (test CA + leaves of each failure shape).
# --------------------------------------------------------------------------- #
def _new_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _ca_cert(key: rsa.RSAPrivateKey, name: str) -> x509.Certificate:
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    now = dt.datetime.now(dt.UTC)
    return (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)  # self-signed root
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )


def _leaf_cert(
    *,
    issuer_cert: x509.Certificate,
    issuer_key: rsa.RSAPrivateKey,
    leaf_key: rsa.RSAPrivateKey,
    hostname: str,
    not_before: dt.datetime,
    not_after: dt.datetime,
) -> x509.Certificate:
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)])
    return (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer_cert.subject)
        .public_key(leaf_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(hostname)]),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(issuer_key, hashes.SHA256())
    )


def _pem(cert: x509.Certificate) -> bytes:
    return cert.public_bytes(serialization.Encoding.PEM)


def _key_pem(key: rsa.RSAPrivateKey) -> bytes:
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )


# --------------------------------------------------------------------------- #
# In-process TLS handshake using the adapter's exact client context.
# --------------------------------------------------------------------------- #
def _handshake(
    *,
    trusted_ca_pem: bytes,
    server_cert_pem: bytes,
    server_key_pem: bytes,
    server_hostname: str,
) -> Exception | None:
    """Run a real TLS handshake: the server presents ``server_cert_pem`` and the
    client validates with the adapter's context (trusting only ``trusted_ca_pem``,
    via the module's CA accessor). Returns the client-side exception, or None on a
    successful handshake. Proves the ACTUAL verification behaviour, not a mock.
    """
    import tempfile
    from pathlib import Path

    # Server context: present the test leaf (+ its key). Written to temp files
    # because load_cert_chain requires file paths.
    with tempfile.TemporaryDirectory() as td:
        cert_path = Path(td) / "leaf.pem"
        key_path = Path(td) / "leaf.key"
        cert_path.write_bytes(server_cert_pem)
        key_path.write_bytes(server_key_pem)
        server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_ctx.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))

        # Client context = the adapter's REAL _build_context (same flags, hostname
        # check, CERT_REQUIRED) but trusting our locally-minted test CA (we do not
        # hold Bright Data's private key, so the ACCEPT case uses a test CA).
        client_ctx = _adapter_context_trusting(trusted_ca_pem)

        client_sock, server_sock = socket.socketpair()
        client_err: list[Exception | None] = [None]

        def _serve() -> None:
            try:
                with server_ctx.wrap_socket(server_sock, server_side=True) as ss:
                    ss.recv(16)
            except OSError:
                pass  # the client rejecting the cert tears the server side down

        t = threading.Thread(target=_serve)
        t.start()
        try:
            with client_ctx.wrap_socket(client_sock, server_hostname=server_hostname) as cs:
                cs.send(b"ok")
        except Exception as exc:  # noqa: BLE001 - we return it for the assertion
            client_err[0] = exc
        finally:
            t.join(timeout=5)
            try:
                client_sock.close()
            except OSError:
                pass
        return client_err[0]


def _adapter_context_trusting(ca_pem: bytes) -> ssl.SSLContext:
    """Build the adapter's context but trusting a SPECIFIC CA PEM (the test CA).

    Uses the real :meth:`_BrightDataTLSAdapter._build_context`, so the flags,
    ``check_hostname`` and ``CERT_REQUIRED`` are exactly the shipped settings; only
    the trust anchor is swapped to our locally-minted CA (we don't hold BD's key).
    """
    adapter = brightdata._BrightDataTLSAdapter(ca_pem.decode("ascii"))
    return adapter._build_context()


# --------------------------------------------------------------------------- #
# Shared fixtures: the trusted test CA + a "forging" CA with the SAME name.
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def trusted_ca() -> tuple[x509.Certificate, rsa.RSAPrivateKey]:
    key = _new_key()
    return _ca_cert(key, "Amber Test Trusted Root CA"), key


@pytest.fixture(scope="module")
def forging_ca() -> tuple[x509.Certificate, rsa.RSAPrivateKey]:
    """A DIFFERENT CA that forges the trusted CA's NAME but uses a different key."""
    key = _new_key()
    return _ca_cert(key, "Amber Test Trusted Root CA"), key  # same CN, different key


# --------------------------------------------------------------------------- #
# (e) ACCEPT: a leaf that genuinely chains to the trusted CA, right hostname.
# --------------------------------------------------------------------------- #
def test_accepts_leaf_chaining_to_trusted_ca(trusted_ca):
    ca_cert, ca_key = trusted_ca
    leaf_key = _new_key()
    now = dt.datetime.now(dt.UTC)
    leaf = _leaf_cert(
        issuer_cert=ca_cert,
        issuer_key=ca_key,
        leaf_key=leaf_key,
        hostname=_LEAF_HOST,
        not_before=now - dt.timedelta(days=1),
        not_after=now + dt.timedelta(days=365),
    )
    err = _handshake(
        trusted_ca_pem=_pem(ca_cert),
        server_cert_pem=_pem(leaf),
        server_key_pem=_key_pem(leaf_key),
        server_hostname=_LEAF_HOST,
    )
    assert err is None, (
        f"a valid chained cert with the right hostname must be ACCEPTED, got {err!r}"
    )


# --------------------------------------------------------------------------- #
# (a) REJECT: an untrusted self-signed cert (chains to nothing trusted).
# --------------------------------------------------------------------------- #
def test_rejects_untrusted_self_signed_cert(trusted_ca):
    ca_cert, _ca_key = trusted_ca
    rogue_key = _new_key()
    rogue = _ca_cert(rogue_key, _LEAF_HOST)  # self-signed, not chaining to trusted CA
    err = _handshake(
        trusted_ca_pem=_pem(ca_cert),
        server_cert_pem=_pem(rogue),
        server_key_pem=_key_pem(rogue_key),
        server_hostname=_LEAF_HOST,
    )
    assert isinstance(err, ssl.SSLCertVerificationError)
    assert "self" in str(err).lower() or "unable to get local issuer" in str(err).lower()


# --------------------------------------------------------------------------- #
# (b) REJECT: a leaf forging the trusted CA's ISSUER NAME but signed by a
#     DIFFERENT key (the impersonation attack the pin/verification must stop).
# --------------------------------------------------------------------------- #
def test_rejects_leaf_forging_ca_name_with_different_key(trusted_ca, forging_ca):
    ca_cert, _ca_key = trusted_ca
    forge_ca_cert, forge_ca_key = forging_ca
    leaf_key = _new_key()
    now = dt.datetime.now(dt.UTC)
    # Issued by the forging CA (same CN as the trusted CA) but a different key.
    leaf = _leaf_cert(
        issuer_cert=forge_ca_cert,
        issuer_key=forge_ca_key,
        leaf_key=leaf_key,
        hostname=_LEAF_HOST,
        not_before=now - dt.timedelta(days=1),
        not_after=now + dt.timedelta(days=365),
    )
    err = _handshake(
        trusted_ca_pem=_pem(ca_cert),  # we trust ONLY the real key's CA
        server_cert_pem=_pem(leaf),
        server_key_pem=_key_pem(leaf_key),
        server_hostname=_LEAF_HOST,
    )
    assert isinstance(err, ssl.SSLCertVerificationError), (
        "a leaf forging the CA name but signed by a different key must be REJECTED"
    )


# --------------------------------------------------------------------------- #
# (c) REJECT: an expired leaf that otherwise chains to the trusted CA.
# --------------------------------------------------------------------------- #
def test_rejects_expired_leaf(trusted_ca):
    ca_cert, ca_key = trusted_ca
    leaf_key = _new_key()
    now = dt.datetime.now(dt.UTC)
    leaf = _leaf_cert(
        issuer_cert=ca_cert,
        issuer_key=ca_key,
        leaf_key=leaf_key,
        hostname=_LEAF_HOST,
        not_before=now - dt.timedelta(days=30),
        not_after=now - dt.timedelta(days=1),  # expired yesterday
    )
    err = _handshake(
        trusted_ca_pem=_pem(ca_cert),
        server_cert_pem=_pem(leaf),
        server_key_pem=_key_pem(leaf_key),
        server_hostname=_LEAF_HOST,
    )
    assert isinstance(err, ssl.SSLCertVerificationError)
    assert "expired" in str(err).lower()


# --------------------------------------------------------------------------- #
# (d) REJECT: a valid chained leaf presented for the WRONG hostname.
# --------------------------------------------------------------------------- #
def test_rejects_wrong_hostname(trusted_ca):
    ca_cert, ca_key = trusted_ca
    leaf_key = _new_key()
    now = dt.datetime.now(dt.UTC)
    leaf = _leaf_cert(
        issuer_cert=ca_cert,
        issuer_key=ca_key,
        leaf_key=leaf_key,
        hostname="not-the-host.example",  # cert is for a different name
        not_before=now - dt.timedelta(days=1),
        not_after=now + dt.timedelta(days=365),
    )
    err = _handshake(
        trusted_ca_pem=_pem(ca_cert),
        server_cert_pem=_pem(leaf),
        server_key_pem=_key_pem(leaf_key),
        server_hostname=_LEAF_HOST,  # we connect expecting geo.brdtest.com
    )
    assert isinstance(err, ssl.SSLCertVerificationError)
    assert "hostname" in str(err).lower() or "match" in str(err).lower()


# --------------------------------------------------------------------------- #
# The CA pin itself: a substituted CA file fails CLOSED.
# --------------------------------------------------------------------------- #
def test_ca_pin_rejects_substituted_ca(tmp_path, monkeypatch):
    """A CA file whose bytes do not match the pinned SHA256 must RAISE — the trust
    store is never silently widened by a swapped CA."""
    rogue = _ca_cert(_new_key(), "Rogue Root CA")
    bad = tmp_path / "rogue_ca.crt"
    bad.write_bytes(_pem(rogue))
    brightdata._brightdata_ca_data.cache_clear()
    monkeypatch.setattr(brightdata, "BRIGHTDATA_CA_PATH", bad)
    try:
        with pytest.raises(brightdata.CaptureError) as ei:
            brightdata._brightdata_ca_data()
        assert "hash mismatch" in str(ei.value).lower()
    finally:
        brightdata._brightdata_ca_data.cache_clear()


def test_ca_pin_accepts_the_committed_ca():
    """The committed CA file matches the pin and loads (the positive control)."""
    brightdata._brightdata_ca_data.cache_clear()
    pem = brightdata._brightdata_ca_data()
    assert "BEGIN CERTIFICATE" in pem
