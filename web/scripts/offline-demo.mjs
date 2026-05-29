#!/usr/bin/env node
/**
 * Amber Component 3 — the OFFLINE GOLDEN RUN, one command, no server, no network.
 *
 *   cd code/web && npm run demo
 *
 * It drives the FULL tamper-proof cycle against the committed golden packet,
 * end to end, through the REAL python `verify_packet`:
 *
 *   1. export   — copy the committed packet to a private working copy
 *   2. verify   — REAL verify_packet  -> expect GREEN (exit 0)
 *   3. tamper   — edit a number in the working copy's facts.json
 *   4. verify   — REAL verify_packet  -> expect RED   (exit 1)
 *   5. revert   — restore the sealed bytes
 *   6. verify   — REAL verify_packet  -> expect GREEN (exit 0)
 *
 * The GREEN/RED at every step is the python process EXIT CODE — never hardcoded.
 * The script asserts the cycle (GREEN, RED, GREEN) and exits non-zero if the
 * real verifier ever disagrees, so this doubles as GATE-3 self-verification.
 *
 * This is the same machinery the UI uses (lib/verify.ts + lib/packet.ts);
 * kept dependency-free (pure Node built-ins) so it runs from a fresh clone.
 */
import { spawnSync } from "node:child_process";
import {
  cpSync,
  existsSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const WEB_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const REPO_ROOT = resolve(WEB_ROOT, "..");

/**
 * Packet default precedence (mirrors web/lib/paths.ts):
 *   1. AMBER_PACKET_DIR (explicit override)
 *   2. samples/live_packet  — the REAL BD DE/BE residential catch, when present
 *   3. samples/floor_demo_packet — the committed labelled fixture fallback
 */
function defaultPacketDir() {
  const livePacket = join(REPO_ROOT, "samples", "live_packet");
  if (existsSync(join(livePacket, "facts.json"))) return livePacket;
  return join(REPO_ROOT, "samples", "floor_demo_packet");
}

const PACKET_DIR = process.env.AMBER_PACKET_DIR
  ? resolve(REPO_ROOT, process.env.AMBER_PACKET_DIR)
  : defaultPacketDir();
const WORK_DIR = join(WEB_ROOT, ".amber-demo", "offline_working_packet");
const TRUSTED_PUBKEY =
  process.env.AMBER_TRUSTED_PUBKEY?.trim() ||
  "f2de2b5f14785372ced46288f3009448db17495312fe0492377fd14b036a5dc8";

const GREEN = "\x1b[1;32m";
const RED = "\x1b[1;31m";
const DIM = "\x1b[2m";
const RESET = "\x1b[0m";

function pythonInterpreter() {
  if (process.env.AMBER_PYTHON?.trim()) return process.env.AMBER_PYTHON.trim();
  const venvWin = join(REPO_ROOT, ".venv", "Scripts", "python.exe");
  const venvPosix = join(REPO_ROOT, ".venv", "bin", "python");
  if (existsSync(venvWin)) return venvWin;
  if (existsSync(venvPosix)) return venvPosix;
  return process.platform === "win32" ? "py" : "python3";
}

const PY = pythonInterpreter();

/** Run the REAL verifier; return { code, out }. The verdict IS the exit code. */
function verify() {
  const args = ["-m", "amber.cli", WORK_DIR, "--pubkey", TRUSTED_PUBKEY];
  const r = spawnSync(PY, args, {
    cwd: REPO_ROOT,
    env: { ...process.env, NO_COLOR: "1" },
    encoding: "utf-8",
  });
  if (r.error) {
    console.error(
      `${RED}failed to launch the verifier (${PY} ${args.join(" ")}): ${r.error.message}${RESET}\n` +
        `Set AMBER_PYTHON to a Python with the 'amber' package installed (e.g. code/.venv).`,
    );
    process.exit(2);
  }
  return { code: r.status, out: (r.stdout || "") + (r.stderr || "") };
}

function banner(label, code) {
  const ok = code === 0;
  const color = ok ? GREEN : RED;
  const verdict = ok ? "GREEN — VERIFIED" : "RED — CHAIN OF CUSTODY BROKEN";
  console.log(`${color}  [${label}] ${verdict}  (real exit code ${code})${RESET}`);
}

function step(n, text) {
  console.log(`\n${DIM}── step ${n}: ${text}${RESET}`);
}

function fail(msg) {
  console.error(`\n${RED}GATE 3 FAILED: ${msg}${RESET}`);
  process.exit(1);
}

console.log(`${GREEN}Amber — offline golden run (Component 3)${RESET}`);
console.log(`${DIM}interpreter : ${PY}${RESET}`);
console.log(`${DIM}packet      : ${PACKET_DIR}${PACKET_DIR.includes("floor_demo_packet") ? "  (LABELLED FIXTURE — not a real BD capture)" : ""}${RESET}`);
console.log(`${DIM}working copy: ${WORK_DIR}${RESET}`);
console.log(`${DIM}trusted key : ${TRUSTED_PUBKEY.slice(0, 16)}…${RESET}`);

if (!existsSync(join(PACKET_DIR, "facts.json"))) {
  fail(`packet not found at ${PACKET_DIR} (no facts.json).`);
}

// 1. export (copy committed packet -> private working copy; source is untouched)
step(1, "export packet (working copy from committed source — source never mutated)");
if (existsSync(WORK_DIR)) rmSync(WORK_DIR, { recursive: true, force: true });
mkdirSync(WORK_DIR, { recursive: true });
cpSync(PACKET_DIR, WORK_DIR, { recursive: true });

// 2. verify clean -> expect GREEN
step(2, "run REAL verify_packet on the clean packet");
let r = verify();
console.log(r.out.trimEnd());
banner("CLEAN", r.code);
if (r.code !== 0) fail("clean packet did not verify GREEN (exit 0).");

// 3. tamper: edit a number in facts.json (a Merkle leaf)
step(3, "edit a price in facts.json (the operator's tamper)");
const factsPath = join(WORK_DIR, "facts.json");
const before = readFileSync(factsPath, "utf-8");
const m = before.match(/"net_of_tax_delta":"([^"]*)"/);
let after;
if (m) {
  after = before.replace(`"net_of_tax_delta":"${m[1]}"`, `"net_of_tax_delta":"99.99"`);
  console.log(`${DIM}  net_of_tax_delta: ${m[1]} -> 99.99${RESET}`);
} else {
  // Fallback: flip the first decimal price-looking token.
  const pm = before.match(/(\d+\.\d{2})/);
  if (!pm) fail("could not find a number to edit in facts.json.");
  after = before.replace(pm[1], "999.99");
  console.log(`${DIM}  ${pm[1]} -> 999.99${RESET}`);
}
if (after === before) fail("the edit did not change facts.json.");
writeFileSync(factsPath, after, "utf-8");

// 4. verify tampered -> expect RED
step(4, "run REAL verify_packet on the tampered packet");
r = verify();
console.log(r.out.trimEnd());
banner("TAMPERED", r.code);
if (r.code === 0) fail("tampered packet still verified GREEN — the tamper-proof is broken!");

// 5. revert
step(5, "revert to the sealed bytes (restore working copy from source)");
rmSync(WORK_DIR, { recursive: true, force: true });
mkdirSync(WORK_DIR, { recursive: true });
cpSync(PACKET_DIR, WORK_DIR, { recursive: true });

// 6. verify reverted -> expect GREEN
step(6, "run REAL verify_packet on the reverted packet");
r = verify();
console.log(r.out.trimEnd());
banner("REVERTED", r.code);
if (r.code !== 0) fail("reverted packet did not verify GREEN (exit 0).");

console.log(
  `\n${GREEN}GATE 3 PASS: GREEN -> RED -> GREEN, every verdict driven by the REAL verify_packet exit code.${RESET}`,
);
console.log(`${DIM}Interactive UI with the same machinery: npm run dev  (http://localhost:3000)${RESET}`);
process.exit(0);
