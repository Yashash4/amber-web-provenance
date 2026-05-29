import { existsSync } from "node:fs";
import { join, resolve } from "node:path";

/**
 * Repo-rooted path resolution for the Amber demo server.
 *
 * The Next.js app lives at `code/web/`; the Python core (`amber/`), the signed
 * packets (`samples/`), and the trusted-signer allowlist all live one level up
 * at `code/`. Everything the demo touches is resolved relative to that repo
 * root so the demo runs from a fresh clone with no absolute paths baked in.
 */

/** `code/` — the parent of `code/web/`. */
export const REPO_ROOT = resolve(process.cwd(), "..");

/** `code/web/` — the Next.js project root (process.cwd() at runtime). */
export const WEB_ROOT = process.cwd();

/**
 * The directory of the packet the demo renders + verifies. Override with
 * `AMBER_PACKET_DIR` (absolute, or relative to `code/`) to swap in the REAL
 * Bright Data DE/BE capture once credentials exist — the UI reads whatever
 * packet dir it is pointed at, so the swap is a single env var.
 *
 * Default: the committed CONSTRUCTED FIXTURE `samples/floor_demo_packet`. It is
 * labelled a fixture everywhere in the UI; it is NOT presented as a real catch.
 */
export function packetDir(): string {
  const override = process.env.AMBER_PACKET_DIR?.trim();
  if (override) {
    return resolve(REPO_ROOT, override);
  }
  return join(REPO_ROOT, "samples", "floor_demo_packet");
}

/**
 * The directory the tamper-proof writes its EDITABLE working copy into. The
 * committed packet under `samples/` is never mutated; the operator edits this
 * copy and reverts it. Lives under the OS temp-style `.amber-demo/` inside the
 * web project so a `git status` of the packet stays clean during a demo.
 */
export function workingPacketDir(): string {
  return join(WEB_ROOT, ".amber-demo", "working_packet");
}

/**
 * Locate a Python interpreter that has the `amber` package importable.
 *
 * Precedence:
 *   1. `AMBER_PYTHON` env (explicit override — an absolute interpreter path).
 *   2. The repo virtualenv at `code/.venv/Scripts/python.exe` (Windows) or
 *      `code/.venv/bin/python` (POSIX) — this is where Components 1/2 installed
 *      the `amber` package, so it is the reliable default.
 *   3. `py` (the Windows launcher) / `python3` / `python` on PATH.
 *
 * Returns the interpreter to spawn. The caller invokes `<py> -m amber.cli ...`.
 */
export function pythonInterpreter(): string {
  const override = process.env.AMBER_PYTHON?.trim();
  if (override) return override;

  const venvWin = join(REPO_ROOT, ".venv", "Scripts", "python.exe");
  const venvPosix = join(REPO_ROOT, ".venv", "bin", "python");
  if (existsSync(venvWin)) return venvWin;
  if (existsSync(venvPosix)) return venvPosix;

  // Fall back to a launcher on PATH. `py` exists on most Windows installs and
  // resolves the active interpreter; `python3`/`python` cover POSIX.
  if (process.platform === "win32") return "py";
  return "python3";
}

/** The trusted demo signer public key (committed; pins the signature). */
export const DEMO_SIGNER_PUBKEY =
  "f2de2b5f14785372ced46288f3009448db17495312fe0492377fd14b036a5dc8";
