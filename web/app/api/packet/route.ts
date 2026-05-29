import { NextResponse } from "next/server";

import {
  loadPacketView,
  readWorkingFacts,
  resetWorkingPacket,
  tamperFacts,
  writeWorkingFacts,
} from "@/lib/packet";
import { packetDir } from "@/lib/paths";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * GET /api/packet
 *
 * Returns the render view-model of the committed source packet (what the
 * split-frame shows) PLUS the current raw facts.json of the editable working
 * copy (what the tamper-proof editor edits). Also reports whether the packet is
 * a labelled fixture or a real capture, and the active packet directory.
 */
export async function GET() {
  try {
    const view = loadPacketView();
    let workingFacts: string;
    try {
      workingFacts = readWorkingFacts();
    } catch {
      // First load before any export: seed the working copy from source.
      resetWorkingPacket();
      workingFacts = readWorkingFacts();
    }
    return NextResponse.json({ view, workingFacts, sourceDir: packetDir() });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : String(err) },
      { status: 500 },
    );
  }
}

/**
 * POST /api/packet
 *
 * Operator actions on the editable working copy:
 *   { action: "export" }                       -> reset working copy from source
 *   { action: "tamper", find, replace }        -> single unambiguous string edit
 *   { action: "writeFacts", contents }         -> overwrite working facts.json
 *   { action: "revert" }                       -> reset working copy from source
 *
 * None of these compute a verdict — they only mutate the bytes the REAL
 * verifier (POST /api/verify) then re-checks.
 */
export async function POST(request: Request) {
  try {
    const body = await request.json();
    const action = body?.action;

    switch (action) {
      case "export":
      case "revert": {
        const work = resetWorkingPacket();
        return NextResponse.json({ ok: true, workingPacket: work, workingFacts: readWorkingFacts() });
      }
      case "tamper": {
        if (typeof body.find !== "string" || typeof body.replace !== "string") {
          return NextResponse.json({ error: "tamper requires string 'find' and 'replace'" }, { status: 400 });
        }
        tamperFacts(body.find, body.replace);
        return NextResponse.json({ ok: true, workingFacts: readWorkingFacts() });
      }
      case "writeFacts": {
        if (typeof body.contents !== "string") {
          return NextResponse.json({ error: "writeFacts requires string 'contents'" }, { status: 400 });
        }
        writeWorkingFacts(body.contents);
        return NextResponse.json({ ok: true, workingFacts: readWorkingFacts() });
      }
      default:
        return NextResponse.json({ error: `unknown action: ${String(action)}` }, { status: 400 });
    }
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : String(err) },
      { status: 500 },
    );
  }
}
