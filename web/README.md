# Amber — Component 3: the split-frame catch + THE TAMPER PROOF

The demo UI (Next.js 14 + Tailwind). It renders a signed Amber evidence packet
as a side-by-side split-frame catch and runs **THE TAMPER PROOF** — the climax —
where the **RED/GREEN verdict is the REAL `verify_packet` process exit code**,
never a hardcoded UI state.

## One-command offline run (no server, no network) — GATE 3

```
cd code/web
npm install
npm run demo
```

`npm run demo` (`scripts/offline-demo.mjs`) drives the full cycle against the
committed golden packet, **entirely offline**, through the real Python verifier:

```
export -> verify (GREEN, exit 0) -> tamper a price -> verify (RED, exit 1) -> revert -> verify (GREEN, exit 0)
```

It asserts the GREEN→RED→GREEN sequence and exits non-zero if the real verifier
ever disagrees, so it is also the GATE-3 self-check. The committed packet under
`samples/` is **never mutated** — the cycle runs on a private working copy under
`web/.amber-demo/` (gitignored).

## Interactive UI

```
cd code/web
npm run dev          # http://localhost:3000
```

Same machinery as `npm run demo`, with buttons:

1. **Export packet** — copies the committed packet to the editable working copy and runs the real verifier (GREEN).
2. **Edit a price** — changes a number in `facts.json` (a Merkle leaf), then runs the real verifier → **RED "CHAIN OF CUSTODY BROKEN"** at `facts.json`.
3. **Revert** — restores the sealed bytes and re-verifies → **GREEN "VERIFIED"**.

You can also free-edit the working `facts.json` in the textarea and click
"Save my edits + verify".

## How the tamper-proof invokes the REAL verifier (proof it is not faked)

`app/api/verify/route.ts` → `lib/verify.ts` spawns:

```
<python> -m amber.cli <working_packet_dir> --pubkey <trusted_signer>
```

from the repo root (`code/`), with `NO_COLOR=1`. The verdict is derived ONLY
from the child process **exit code**:

```ts
verdict: exitCode === 0 ? "VERIFIED" : "BROKEN"
```

There is no other code path that produces a verdict; a spawn failure surfaces an
error, it never fabricates GREEN. The exact command and the verifier's verbatim
stdout are shown in the UI so it is auditable that it is real.

### Python interpreter resolution

`lib/paths.ts` picks the interpreter in this order:

1. `AMBER_PYTHON` env (explicit interpreter path), else
2. the repo virtualenv `code/.venv/Scripts/python.exe` (Windows) / `code/.venv/bin/python` (POSIX) — where Components 1/2 installed the `amber` package, else
3. `py` (Windows) / `python3` (POSIX) on PATH.

If none has the `amber` package, the route returns a clear error telling you to
set `AMBER_PYTHON`.

## Fixture vs real — and swapping in the real packet

The default packet is `samples/floor_demo_packet`, a **CONSTRUCTED FIXTURE**
(its capture bodies carry a `_note` and its SKU label ends `(DEMO FIXTURE)`).
The UI detects this from the actual bytes and shows a loud
**"SAMPLE / FIXTURE DATA"** banner — fixture numbers are never presented as a
real catch.

The real Bright Data DE/BE capture (a Component-2 `facts@2` packet, pending
credentials) swaps in with **one environment variable** — the UI renders
whatever packet directory it is pointed at:

```
# absolute, or relative to code/
AMBER_PACKET_DIR=samples/live_packet npm run dev
AMBER_PACKET_DIR=samples/live_packet npm run demo
```

When the swapped packet is not a fixture, the banner flips to
**"REAL CAPTURED PACKET"**.

## The ONE live cell

The live-capture cell (`app/api/live/route.ts`) calls Component 2's real
credential probe (`python -m amber.capture_cli creds`). Until Bright Data
credentials exist it honestly shows **"live capture — pending Bright Data
credentials"** (driven by the probe's real exit code) and **never fabricates a
live result**. It arms automatically the moment `BRIGHTDATA_*` credentials are
set.

## Environment variables

| Var | Purpose | Default |
|---|---|---|
| `AMBER_PACKET_DIR` | packet dir to render + verify (absolute or relative to `code/`) | `samples/floor_demo_packet` |
| `AMBER_PYTHON` | explicit Python interpreter with the `amber` package | auto-detect (repo `.venv`, then `py`/`python3`) |
| `AMBER_TRUSTED_PUBKEY` | trusted signer pubkey(s) the signature is pinned to | the committed demo signer |

## Security note (deps)

`next` is pinned to `14.2.35` (latest 14.2.x patch). The remaining npm-audit
advisories on the 14.x line all require Next 16 (a major breaking change) and
apply only to internet-exposed deployments using middleware, the Image
Optimizer, CSP nonces, i18n, or WebSocket upgrades — **none of which this local,
offline demo uses**. `postcss` is patched to `8.5.15`. All deps are MIT-licensed.
