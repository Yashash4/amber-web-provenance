"use client";

import type { PacketView } from "@/lib/packet";

/**
 * The honesty label. When the rendered packet is a constructed FIXTURE (not a
 * real Bright Data capture), this banner says so loudly — fixture numbers are
 * never presented as a real catch. When a real captured packet is swapped in
 * (via AMBER_PACKET_DIR), the banner flips to a sourced-capture label.
 */
export function FixtureBanner({ view }: { view: PacketView }) {
  if (view.isFixture) {
    return (
      <div className="rounded-md border border-amber/50 bg-amber/10 px-4 py-3 text-sm">
        <span className="font-bold text-amber">SAMPLE / FIXTURE DATA</span>
        <span className="ml-2 text-amber/90">
          This packet is a constructed fixture for UI development — NOT a Bright Data capture.
          {view.fixtureNote ? ` ${view.fixtureNote}` : ""} The real DE/BE capture replaces it
          (pending Bright Data credentials); the UI renders whatever packet directory it is
          pointed at via <code className="text-amber">AMBER_PACKET_DIR</code>.
        </span>
      </div>
    );
  }
  return (
    <div className="rounded-md border border-verified/40 bg-verified/10 px-4 py-3 text-sm">
      <span className="font-bold text-verified">REAL CAPTURED PACKET</span>
      <span className="ml-2 text-verified/90">
        Rendered from a sealed, signed Bright Data capture at{" "}
        <code className="text-verified">{view.packetDir}</code>. Re-verify it yourself offline
        with <code className="text-verified">verify_packet</code>.
      </span>
    </div>
  );
}
