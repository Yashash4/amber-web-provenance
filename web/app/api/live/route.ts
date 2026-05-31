import { NextResponse } from "next/server";

/**
 * GET /api/live
 *
 * The ONE live-capture cell's credential probe. In the full-stack build this
 * shelled out to Component 2's real credential check
 * (`python -m amber.capture_cli creds`). The deployed, self-contained demo has
 * no Python and no Bright Data credentials, so it honestly reports the pending
 * state - it never fabricates a live capture result. The UI's LiveCell renders
 * this pending state client-side; this stub mirrors it for any direct caller and
 * does no child_process spawn or filesystem access.
 */
export async function GET() {
  return NextResponse.json({
    ready: false,
    mode: null,
    exitCode: 1,
    message:
      "live capture - pending Bright Data credentials. This hosted demo plays the committed offline golden packet. The live DE/BE capture runs in the full-stack build with the Python core on PATH and BRIGHTDATA_* credentials set; it never fabricates a live result.",
    command: "python -m amber.capture_cli creds",
  });
}
