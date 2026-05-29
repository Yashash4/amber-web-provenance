# Amber — Web Provenance

**A forensically-signed, geo-attributed observation of public web state.**

This repository holds Amber's signing/verification core plus the residential
capture + measurement-validity floor that produces the signed facts:

- **Component 1** — the signed-provenance primitive and the offline `verify_packet`
  verifier. An Amber **evidence packet** bundles the raw bytes that were actually
  fetched together with deterministic Layer-1 facts, commits to all of them with
  an RFC 6962 Merkle tree, and ed25519-signs the Merkle root. Anyone can
  re-verify a packet offline — no network, no Amber service — GREEN / RED.
- **Component 2** — the **Bright Data residential capture + the deterministic
  measurement-validity floor** (`amber/capture/`). It captures the same product
  URL from Germany and Belgium plus a within-country control (several distinct
  residential exits per country) in a same-second batch, then computes — with NO
  LLM — the Layer-1 facts: the net-of-tax price spread (sourced VAT table), the
  GTIN / SKU-identity confidence, the per-geo factual state (with the
  `GEO_BLOCKED` ≥2-causally-independent-signal floor and a soft-block gate that
  forces `INCONCLUSIVE`), two-source signed geo-attribution (exit-IP RIR + the
  response geo-signals), and the within-country control. These feed Component 1's
  `seal_packet`.

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

## Component 2 — residential capture + measurement floor

The capture client (`amber/capture/`) reads Bright Data credentials from the
process environment or a gitignored `code/.env` (copy `.env.example`). Two modes
are supported: residential **proxy** (sticky sessions give the distinct exit IPs
the within-country control needs) and the Web Unlocker **api** token.

```bash
amber-capture creds                                  # secret-free credential state
amber-capture capture https://shop.example/p/HERO \
    --countries DE,BE --sessions 3 --out samples/live_packet
verify_packet samples/live_packet                    # GREEN on the real capture
amber-capture discover candidates.json --countries DE,BE   # rank own-brand SKUs
```

With **no credentials present**, the live commands report the pending live step
and exit non-zero — they never fabricate a capture. The full deterministic floor
runs offline; see the GATE-2 demonstration (constructed fixtures, clearly
labelled — not a Bright Data capture):

```bash
python scripts/gate2_floor_demo.py          # floor -> seal -> verify, GREEN
verify_packet samples/floor_demo_packet      # GREEN
```

The offline RIR country snapshot (`amber/capture/data/rir_country_blocks.tsv`,
real RIPE NCC delegation data) backs the network-side geo-attribution; refresh it
with `python scripts/build_rir_snapshot.py`.

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

## Credits

Built by Yashash Sheshagiri. A mention is appreciated if you use Amber.

## License

MIT — see [LICENSE](LICENSE).
