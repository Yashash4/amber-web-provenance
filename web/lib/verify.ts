import { spawn } from "node:child_process";

import { DEMO_SIGNER_PUBKEY, pythonInterpreter, REPO_ROOT } from "./paths";
import type { VerifyResult } from "./verify-types";

// Re-export the Node-free result type so existing `import { VerifyResult } from
// "@/lib/verify"` call sites keep working. The shape lives in `verify-types` so
// client components can import it without pulling this Node-only spawner into
// the browser bundle.
export type { VerifyResult } from "./verify-types";

/**
 * Parse the verifier's plain-text report into structured checks.
 *
 * The report lines look like (ANSI stripped):
 *   "  [OK  ] de-01: body sha256 ok (..)"
 *   "  [FAIL] facts.json: content of 'facts.json' changed since sealing: .."
 * The trailing verdict is "[OK] VERIFIED ..." or "[X] CHAIN OF CUSTODY BROKEN".
 */
function parseChecks(stdout: string): {
  checks: VerifyResult["checks"];
  brokenNode: string | null;
} {
  const checks: VerifyResult["checks"] = [];
  let brokenNode: string | null = null;
  for (const line of stdout.split(/\r?\n/)) {
    const m = line.match(/^\s*\[(OK\s*|FAIL)\]\s+([^:]+):\s*(.*)$/);
    if (m) {
      const ok = m[1].trim() === "OK";
      checks.push({ node: m[2].trim(), ok, detail: m[3].trim() });
    }
    const broken = line.match(/^\s*broken at:\s*(.+)$/);
    if (broken) brokenNode = broken[1].trim();
  }
  return { checks, brokenNode };
}

/**
 * Run the REAL python `verify_packet` over `packetDir` and return its verdict.
 *
 * Invocation: `<python> -m amber.cli <packetDir> --pubkey <trusted>` from the
 * repo root (so `amber` is importable), with `NO_COLOR=1` so stdout is clean
 * text we can parse. `AMBER_FORCE_COLOR` is intentionally not set.
 *
 * The verdict is derived solely from the process exit code:
 *   exit 0       -> "VERIFIED"  (GREEN)
 *   exit non-0   -> "BROKEN"    (RED)
 * There is no fallback that fabricates a verdict; a spawn failure rejects.
 */
export function runVerifier(packetDir: string): Promise<VerifyResult> {
  const python = pythonInterpreter();
  const trusted = (process.env.AMBER_TRUSTED_PUBKEY?.trim() || DEMO_SIGNER_PUBKEY)
    .split(/[\s,]+/)
    .filter(Boolean);

  const args = ["-m", "amber.cli", packetDir];
  for (const key of trusted) {
    args.push("--pubkey", key);
  }

  const command = `${python} ${args.join(" ")}`;

  return new Promise<VerifyResult>((resolvePromise, reject) => {
    const child = spawn(python, args, {
      cwd: REPO_ROOT,
      env: { ...process.env, NO_COLOR: "1" },
      windowsHide: true,
    });

    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (d) => (stdout += d.toString()));
    child.stderr.on("data", (d) => (stderr += d.toString()));

    child.on("error", (err) => {
      reject(
        new Error(
          `failed to launch the verifier (${command}): ${err.message}. ` +
            `Set AMBER_PYTHON to a Python interpreter that has the 'amber' package installed.`,
        ),
      );
    });

    child.on("close", (code) => {
      const exitCode = code ?? -1;
      const rawOutput = stdout + (stderr ? `\n[stderr]\n${stderr}` : "");
      const { checks, brokenNode } = parseChecks(stdout);
      resolvePromise({
        // VERDICT = pure function of the real exit code. Never hardcoded.
        verdict: exitCode === 0 ? "VERIFIED" : "BROKEN",
        exitCode,
        checks,
        brokenNode,
        rawOutput,
        command,
        trustedPubkeys: trusted,
      });
    });
  });
}
