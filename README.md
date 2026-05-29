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

## Phase 2 — the Layer-2 legal jury (AI/ML API)

> **Layer split (physical, not rhetorical).** The signed packet (Layer 1) holds
> only raw captures + deterministic facts. The legal *characterization* is
> **Layer 2: an AI-assisted interpretation that is UNSIGNED and physically
> separate** — `amber-jury` writes `<packet>.legal_advisory.json` as a *sibling*
> of the packet directory, never inside it. An LLM never computes a fact or
> number into the signed bundle.

`amber/jury/` runs a **three-model jury** over a signed observation's
`facts.json`. Three causally-different model families (one OpenAI, one Google,
one Anthropic), reached through the single OpenAI-compatible **AI/ML API**
gateway, *independently* classify the Reg (EU) 2018/302 legal taxonomy and give
a rule-grounded rationale. A strict **majority** (≥ 2 of 3) becomes the advisory;
any split routes to a human — the jury never auto-resolves disagreement.

The jury models (resolved against the gateway's model list):

| Family | Model id |
|---|---|
| OpenAI | `gpt-4o-mini` |
| Google | `google/gemini-2.0-flash` |
| Anthropic | `claude-sonnet-4-5-20250929` |

```bash
# Classify a packet; writes an UNSIGNED advisory beside it (not inside it):
amber-jury classify samples/floor_demo_packet
#   -> samples/floor_demo_packet.legal_advisory.json   (the packet stays GREEN)

# The gold-set evidence (precision/recall — see below):
amber-jury goldset           # add --json for the full per-example report
```

The API key is read from `AIMLAPI_KEY` in the process env or the gitignored
`code/.env`; it is never printed or written into any output.

### Methodology — gold-set precision / recall (not consensus theater)

We do **not** report inter-model agreement (Fleiss' κ) as evidence of quality:
correlated frontier models agreeing tells you nothing about correctness
(consensus ≠ accuracy). Instead we measure each model and the consensus against
a **hand-labeled gold set** of 16 synthetic Layer-1 observations whose
ground-truth Reg 2018/302 label is fixed by the rule (access-denial →
prohibited; net-of-tax-zero → tax artifact; permitted price differential;
soft-block / single-country → insufficient info). Every gold example is a
clearly-labeled *methodology fixture* (`GOLD-FIXTURE (METHODOLOGY — NOT
PRODUCTION DATA)`); no real price history is fabricated. Reproduce with
`amber-jury goldset`.

Live results (16 examples; macro = mean over the labels present):

| Classifier | Accuracy | Macro P | Macro R | Macro F1 |
|---|---|---|---|---|
| OpenAI `gpt-4o-mini` | 0.750 (12/16) | 0.625 | 0.750 | 0.667 |
| Google `gemini-2.0-flash` | **1.000 (16/16)** | 1.000 | 1.000 | 1.000 |
| Anthropic `claude-sonnet-4-5` | 0.875 (14/16) | 0.800 | 0.700 | 0.733 |
| **3-model consensus** | 0.875 (14/16) | 0.800 | 0.700 | 0.733 |

Per-label, the consensus is **perfect (P = R = 1.0) on the legally decisive
categories** — `PROHIBITED_GEO_BLOCKING`, `TAX_DUTY_ARTIFACT`, and
`INSUFFICIENT_INFO`. Its only misses are two *permitted price-differential*
cases where the three models split three ways and the case was therefore routed
to a human (recall 0.50 on `PERMITTED_OBJECTIVE_JUSTIFICATION`). That is the
honest finding the gold set is designed to surface: the consensus does **not**
beat the single best model here — routing a genuinely borderline
permitted-differential case to a human is the correct, conservative behavior,
not a number to inflate.

### Jury tests

The jury suite mocks the AI/ML API (no credits burned) and covers the consensus
logic (majority, tie → `ROUTE_TO_HUMAN`, a model error counting as a non-vote),
`.env` key-stripping, taxonomy/reply parsing, and the gold-set metric math. It
also seals a real packet and asserts the advisory lands **outside** the packet
and the packet still verifies GREEN. One opt-in live smoke test exercises the
real gateway:

```bash
AMBER_JURY_LIVE=1 pytest tests/test_jury_live_smoke.py
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

## Credits

Built by Yashash Sheshagiri. A mention is appreciated if you use Amber.

## License

MIT — see [LICENSE](LICENSE).
