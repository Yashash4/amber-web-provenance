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

## Phase 2 — the agent-memory / temporal-persistence layer (Cognee)

> **Layer boundary (same physical split as the jury).** The memory layer reads
> the SIGNED Layer-1 `facts.json` and builds analysis *over* it — a self-hosted
> Cognee temporal knowledge graph plus a deterministic persistence verdict. It
> NEVER writes into the signed packet and never imports the signing core; an LLM
> never computes a fact or number into the signed bundle.

`amber/memory/` answers the question that turns a price gap into a *margin-leak*
signal: **is the net-of-tax gap persistent, or just noise?** A one-off gap is
nothing; a gap the same SKU shows across captures is real diversion / leakage —
which is exactly the Finance / anti-diversion persistence angle. Cognee is the
**Best Use of Agent Memory**: a brand's agent *remembers* every signed
observation and can ask the graph "has this SKU shown a gap before? which
countries/SKUs recur? is it sustained?".

### Honesty — real captures only (never a fabricated history)

Price history is **never** fabricated. The persistence analysis runs only over
the captures that genuinely exist, and every summary frames the window honestly:
**"N captures over [real window]; the baseline compounds from day one."** With a
single signed capture the answer is a one-point **BASELINE** — persistence is
*not* asserted from one capture. Faking a multi-week chart is disqualifying; we
do not do it.

### Cognee on the Gemini backend (one key, no extra credentials)

Cognee is self-hosted. Both the LLM and the embedding model are configured to
use **Gemini** via its OpenAI-compatible endpoint, with the single direct
`GEMINI_API_KEY` (read from the env or the gitignored `code/.env`; never printed).
One key covers chat + embeddings, so the layer needs no extra credentials and
stays inside the Gemini free tier.

| Role | Model |
|---|---|
| LLM | `gemini-2.0-flash` |
| Embeddings | `text-embedding-004` (768 dims) |

```bash
# Deterministic persistence verdict — OFFLINE, no Gemini calls, no credits:
amber-memory persistence samples/live_packet         # add --json for the report
#   -> VERDICT: BASELINE (one real capture; net-of-tax delta 10.75 EUR, dearer: DE;
#      within-country control corroborated; "1 capture ... the baseline compounds
#      from day one")

# Ingest signed packet(s) into the self-hosted Cognee temporal graph (Gemini):
amber-memory ingest samples/live_packet              # real captures only
amber-memory ingest p1 p2 p3                          # a real time series

# Ask the graph an agent-memory question (TEMPORAL = time-aware persistence):
amber-memory query "has the AirPods 4 SKU shown a net-of-tax gap before, and \
    is it persistent?" --temporal

amber-memory creds                                    # secret-free Gemini key state
```

The `persistence` subcommand is the reproducible ground truth (deterministic, no
LLM) that the graph's natural-language answers can be checked against — the same
discipline as the jury's gold set: the receipts, not the model's vibes.

### Memory tests

The memory suite mocks Cognee + Gemini (no credits) and covers the observation
mapping (asserted against the **real** AirPods facts), the persistence verdicts
(baseline / persistent / intermittent / transient), the honest "N captures over
real window" framing (never fabricates points), the Gemini-backend wiring (key
passed to LLM **and** embeddings, never leaked), and the boundary (ingesting a
packet never writes a file into it). One opt-in live smoke test ingests the real
packet and runs one query:

```bash
AMBER_MEMORY_LIVE=1 pytest tests/test_memory_live_smoke.py
```

## Phase 2 — the event-driven automated workflow (TriggerWare.ai)

> **Layer boundary (same physical split as the jury / memory layers).** The
> workflow layer only *reads* a packet's signed Layer-1 `facts.json`. It never
> writes into the signed packet, never imports the Phase-1 spine, and lets no
> value flow back into the signed bundle. (Confirmed: a packet still verifies
> GREEN after the workflow runs over it.)

`amber/workflow/` closes the loop: **a signed Amber web-data change → a
TriggerWare trigger → an agent decision → a real-world brand-protection alert.**
This is the textbook automated workflow — TriggerWare.ai's *"Best Use of
Automated Workflows"* challenge.

**What TriggerWare.ai is** (confirmed live against the API, and from
`https://docs.triggerware.com/`): a *"SQL Over Everything"* platform. Base URL
`https://api.triggerware.com`, auth via an `Api-Key:` header. It exposes data
sources as queryable virtual tables (`POST /query`, natural-language or SQL) and
lets you register **triggers** — a saved SQL query polled on a schedule. The
platform accumulates the *deltas* (rows added/removed since the last poll); your
agent polls `POST /triggers/{name}/poll` and acts on the `added`/`deleted` rows.

Amber maps a signed observation onto that primitive: the deterministic
`cross_country_comparison` (net-of-tax delta / access-denial) becomes a one-row
SQL `SELECT` of the signed signal columns, gated by the brand's alert threshold
(`net_of_tax_delta_eur > <threshold>`). The trigger fires *exactly when* the
signed delta crosses the threshold — so the first poll returns the event as an
`added` delta and Amber raises a brand-protection alert that states the signed
**FACT** ("PRICE DELTA DETECTED — signed, net-of-tax, chain of custody"), never
a legal verdict. The threshold is the operator's alert knob, **not** a legal
number; the legal characterisation stays in the separate, unsigned Layer-2 jury
advisory.

```bash
# OFFLINE — derive the event (and the query/trigger SQL) from signed facts:
amber-workflow event samples/live_packet
#   -> NET_OF_TAX_PRICE_DELTA, net-of-tax delta 10.75 EUR (DE dearer than BE)

# LIVE — register a TriggerWare trigger from a real capture, then poll it once
# to confirm it FIRES on the signed delta, and render the alert:
amber-workflow arm samples/live_packet --threshold 1.00
#   -> created trigger 'amber_apple_airpods_4_...'; poll: added=1 fired=True
#   -> AMBER BRAND-PROTECTION ALERT (signed FACT, not a verdict)

# LIVE — expose the signed observation as a queryable API row a brand agent polls:
amber-workflow query samples/live_packet

amber-workflow poll <trigger_name>      # the accumulated delta (event signal)
amber-workflow list                     # registered triggers
amber-workflow disarm <trigger_name>    # delete a trigger
amber-workflow creds                    # secret-free TriggerWare key state
```

The key is read from `TRIGGERWARE_API_KEY` (env or the gitignored `code/.env`)
and is **never** printed, logged, or placed in any returned object.

> **Real-API findings (surfaced honestly, not papered over).** TriggerWare's SQL
> engine compares quoted string literals as strings, so money columns are emitted
> as **numeric** literals (a quoted `'10.75' > 1.00` errors as "invalid operands
> for infix operator >"). Its trigger validator rejects bare `NULL`/`TRUE`/`FALSE`
> literals and starts timing out past ~13 columns, so Amber serialises NULL/bool
> as well-typed string literals and projects the **compact signal columns** into
> the trigger; the verbose human prose (the banner, the SKU label) lives on the
> locally-rendered alert. These are root serialisation fixes, verified live.

### Workflow tests

The workflow suite mocks the TriggerWare API (no live calls in the suite) and
covers the deterministic event extraction (asserted against the **real** AirPods
facts → the 10.75 EUR delta), the threshold boundary (delta must strictly exceed
the threshold), the trigger-SQL construction (numeric money columns, well-typed
NULL/bool, the compact signal projection), the client (key loading, the API
surface, errors surfaced not swallowed), and the **boundary** (arming a trigger
never writes a file into the signed packet, which still verifies GREEN). One
opt-in live smoke test arms a trigger on the real packet, polls it, asserts it
fires on the 10.75 EUR delta, and deletes the trigger (cleanup):

```bash
AMBER_WORKFLOW_LIVE=1 pytest tests/test_workflow_live_smoke.py
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
