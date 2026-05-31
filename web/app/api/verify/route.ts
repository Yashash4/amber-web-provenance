import { NextResponse } from "next/server";

import { VERIFY_GREEN } from "@/app/data/packet";

/**
 * POST /api/verify
 *
 * In the full-stack build this route shelled out to the real Python
 * `verify_packet` over the editable working copy. The deployed, self-contained
 * demo has no Python and no on-disk working copy: the tamper-proof runs entirely
 * client-side from the REAL recorded verifier verdicts bundled in
 * `app/data/packet.ts`, so this endpoint is not used by the UI.
 *
 * It is kept as a thin, dependency-free stub (no child_process, no filesystem)
 * that returns the recorded GREEN verdict for the sealed packet, so any direct
 * caller gets the real sealed-packet result rather than a server-side exception.
 */
export async function POST() {
  return NextResponse.json(VERIFY_GREEN);
}
