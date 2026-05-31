import { NextResponse } from "next/server";

import { loadPacketView, readWorkingFacts } from "@/lib/packet";

/**
 * GET /api/packet
 *
 * Returns the render view-model of the demo packet plus the facts.json text the
 * tamper-proof editor edits. The deployed demo is self-contained: it serves the
 * REAL packet values bundled at build time (no request-time filesystem, no
 * Python). The UI renders from the same data directly; this endpoint is kept for
 * any external caller and never touches the filesystem.
 */
export async function GET() {
  const view = loadPacketView();
  const workingFacts = readWorkingFacts();
  return NextResponse.json({ view, workingFacts, sourceDir: view.packetDir });
}

/**
 * POST /api/packet
 *
 * The operator edit/export/revert actions ran against an on-disk working copy in
 * the full-stack build. The deployed demo holds the working copy in client state
 * (the tamper-proof component), so there is no server-side mutation to perform.
 * This stub acknowledges the action and returns the sealed facts text; no
 * filesystem writes occur.
 */
export async function POST() {
  const workingFacts = readWorkingFacts();
  return NextResponse.json({ ok: true, workingFacts });
}
