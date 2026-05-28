# Amber — Web Provenance (Component 1)

**A forensically-signed, geo-attributed observation of public web state.**

This repository holds Amber's signing/verification core: the signed-provenance
primitive and the offline `verify_packet` verifier. An Amber **evidence packet**
bundles the raw bytes that were actually fetched together with deterministic
Layer-1 facts, commits to all of them with an RFC 6962 Merkle tree, and
ed25519-signs the Merkle root. Anyone can re-verify a packet offline — no
network, no Amber service — and get a GREEN / RED verdict.

> The signed bundle contains **only** raw captures + deterministic Layer-1
> facts. No AI-derived label is ever signed.

## The packet

```
amber_packet/
  captures/<capture_id>.body   raw bytes of each fetched HTTP response
  manifest.json                per-capture metadata + sha256(body)
  facts.json                   Layer-1 deterministic facts (no LLM)
  merkle.json                  ordered leaf hashes + the Merkle root
  signature.json               ed25519 signature over the root + the public key
```

The Merkle leaves, in a fixed order, are: each capture body, then
`manifest.json`, then `facts.json`. Because `facts.json` is itself a leaf,
**editing any number in it changes the root and the signature fails** — the
verifier flashes RED. The same holds for flipping any captured byte or
reordering manifest entries. That is THE TAMPER PROOF.

## Install

```bash
python -m venv .venv
. .venv/Scripts/activate    # Windows; use source .venv/bin/activate on POSIX
pip install -e ".[dev]"
```

Only `cryptography` (Apache-2.0 / BSD) is required at runtime.

## Verify a packet (offline)

```bash
verify_packet path/to/amber_packet
# or:  python -m amber.cli path/to/amber_packet
```

Exit code `0` + green `VERIFIED` if the chain of custody is intact; non-zero +
red `CHAIN OF CUSTODY BROKEN` (naming the broken node) on any tampering.

## Reproduce the real signed golden packet

```bash
python scripts/build_real_packet.py        # does ONE real HTTP GET, seals a packet
verify_packet samples/real_packet           # prints GREEN
```

## Tests

```bash
pytest          # GREEN on the intact packet; RED on each of the 4 tamper cases
```

## Reuse / provenance

The ed25519 signer/verifier are lifted from the Reef project
(`atlas/app/crypto/signer.py`, `verifier.py`); the Merkle tree is ported from
Reef's Go implementation (`internal/audit/merkle.go`, RFC 6962
domain-separated). `pymerkle` is GPL and is therefore **not** imported — Amber
ships under MIT.

## License

MIT — see [LICENSE](LICENSE).
