import { spawn } from "node:child_process";

import { NextResponse } from "next/server";

import { pythonInterpreter, REPO_ROOT } from "@/lib/paths";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * GET /api/live
 *
 * The ONE live-capture cell. It calls Component 2's REAL credential probe
 * (`python -m amber.capture_cli creds`) which reports — without ever printing a
 * secret — whether Bright Data credentials are present.
 *
 *   creds present  (exit 0) -> { ready: true,  ... }   the live cell can fire
 *   creds absent   (exit 1) -> { ready: false, ... }   "pending Bright Data
 *                                                        credentials" (honest)
 *
 * This route NEVER fabricates a live capture result. Until creds exist it
 * truthfully reports the pending state; the moment creds are set it flips to
 * ready and the operator can run the live `amber-capture capture` step.
 */
export async function GET() {
  const python = pythonInterpreter();
  const args = ["-m", "amber.capture_cli", "creds"];

  return new Promise<NextResponse>((resolvePromise) => {
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
      resolvePromise(
        NextResponse.json(
          {
            ready: false,
            error: `could not probe credentials (${python} ${args.join(" ")}): ${err.message}`,
          },
          { status: 500 },
        ),
      );
    });

    child.on("close", (code) => {
      let state: { present?: boolean; mode?: string | null } = {};
      try {
        state = JSON.parse(stdout);
      } catch {
        state = {};
      }
      // Readiness is the REAL exit code of the credential probe (0 = present).
      const ready = code === 0 && state.present === true;
      resolvePromise(
        NextResponse.json({
          ready,
          mode: state.mode ?? null,
          exitCode: code ?? -1,
          message: ready
            ? `Bright Data credentials detected (mode: ${state.mode}). The live DE/BE capture is armed — run \`python -m amber.capture_cli capture <url>\` to seal a real packet.`
            : "live capture — pending Bright Data credentials. The demo is playing the committed offline golden packet. This cell arms automatically once BRIGHTDATA_* credentials are set; it never fabricates a live result.",
          rawOutput: stdout + (stderr ? `\n[stderr]\n${stderr}` : ""),
          command: `${python} ${args.join(" ")}`,
        }),
      );
    });
  });
}
