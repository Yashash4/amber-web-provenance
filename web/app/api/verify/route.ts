import { NextResponse } from "next/server";

import { workingPacketDir } from "@/lib/paths";
import { runVerifier } from "@/lib/verify";

// This route shells out to the Python core and reads repo files: it must run on
// the Node.js runtime and must never be cached/prerendered.
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * POST /api/verify
 *
 * Runs the REAL `python -m amber.cli <working_packet> --pubkey <trusted>` over
 * the editable WORKING COPY of the packet and returns its verdict. The RED/GREEN
 * the UI shows is `result.verdict`, which is a pure function of the verifier's
 * process EXIT CODE (0 -> VERIFIED, non-zero -> BROKEN). Nothing here fabricates
 * a verdict — that is THE TAMPER PROOF.
 */
export async function POST() {
  try {
    const result = await runVerifier(workingPacketDir());
    return NextResponse.json(result);
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : String(err) },
      { status: 500 },
    );
  }
}
