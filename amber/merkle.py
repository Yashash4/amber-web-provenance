"""RFC 6962-style SHA-256 Merkle tree.

Ported from Reef's Go implementation
(``lobstertrap-reef/internal/audit/merkle.go``) — same domain-separation and
lone-node-promotion rules, re-expressed in Python. We port rather than import
``pymerkle`` because that library is GPL-licensed and Amber ships under MIT;
see the project license-hygiene rule (MIT/Apache/BSD only).

Domain separation (RFC 6962) defends against second-preimage attacks across
the leaf-vs-internal boundary:

    leaf hash     = SHA-256(0x00 || leaf_bytes)
    internal hash = SHA-256(0x01 || left || right)

Odd nodes at a level are PROMOTED directly to the next level rather than being
hashed with a copy of themselves. This avoids the ambiguity where a tree of N
leaves and a tree of 2N leaves (last element repeated) would otherwise collide.

The functions here operate on already-computed leaf hashes (``bytes``), so the
caller decides what a leaf *is* (a capture body, ``manifest.json``,
``facts.json`` — see ``amber.packet``).
"""

from __future__ import annotations

import hashlib

LEAF_PREFIX = b"\x00"
INTERNAL_PREFIX = b"\x01"


def leaf_hash(leaf_bytes: bytes) -> bytes:
    """Return the RFC 6962 leaf hash: SHA-256(0x00 || leaf_bytes)."""
    h = hashlib.sha256()
    h.update(LEAF_PREFIX)
    h.update(leaf_bytes)
    return h.digest()


def internal_hash(left: bytes, right: bytes) -> bytes:
    """Return the RFC 6962 internal-node hash: SHA-256(0x01 || left || right)."""
    h = hashlib.sha256()
    h.update(INTERNAL_PREFIX)
    h.update(left)
    h.update(right)
    return h.digest()


def merkle_root(leaf_hashes: list[bytes]) -> bytes:
    """Compute the Merkle root over a list of pre-computed leaf hashes.

    ``leaf_hashes`` must be the RFC 6962 leaf hashes (i.e. already passed
    through :func:`leaf_hash`). Raises ``ValueError`` on an empty list — an
    empty tree has no defined root, and silently returning a sentinel would be
    a swallowed error.
    """
    if not leaf_hashes:
        raise ValueError("merkle_root: cannot compute a root over zero leaves")

    level = list(leaf_hashes)
    while len(level) > 1:
        nxt: list[bytes] = []
        for i in range(0, len(level), 2):
            if i + 1 == len(level):
                # Lone node at the end of an odd-length level: promote it
                # directly to the next level (RFC 6962), do NOT hash with self.
                nxt.append(level[i])
            else:
                nxt.append(internal_hash(level[i], level[i + 1]))
        level = nxt
    return level[0]


def merkle_root_hex(leaf_hashes: list[bytes]) -> str:
    """Hex-encoded :func:`merkle_root`."""
    return merkle_root(leaf_hashes).hex()
