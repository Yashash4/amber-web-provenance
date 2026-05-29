import { FixtureBanner } from "@/components/FixtureBanner";
import { LiveCell } from "@/components/LiveCell";
import { SplitFrame } from "@/components/SplitFrame";
import { TamperProof } from "@/components/TamperProof";
import { WithinCountryControl } from "@/components/WithinCountryControl";
import { loadPacketView, readWorkingFacts, resetWorkingPacket } from "@/lib/packet";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export default function Home() {
  // Render the committed packet view server-side. Seed the editable working
  // copy so the tamper-proof editor starts from the sealed bytes.
  const view = loadPacketView();
  let initialFacts: string;
  try {
    initialFacts = readWorkingFacts();
  } catch {
    resetWorkingPacket();
    initialFacts = readWorkingFacts();
  }

  return (
    <main className="instrument-grid min-h-screen px-4 py-8 sm:px-8">
      <div className="mx-auto max-w-5xl space-y-8">
        <header className="space-y-2 border-b border-white/10 pb-5">
          <div className="flex items-center gap-3">
            <span className="text-3xl">🟠</span>
            <div>
              <h1 className="text-2xl font-black tracking-tight text-amber">AMBER</h1>
              <p className="text-xs text-white/50">
                The forensic instrument that catches a store charging two countries different
                conditions for the same product in the same second — and prints a tamper-proof,
                independently re-verifiable evidence packet.
              </p>
            </div>
          </div>
        </header>

        <FixtureBanner view={view} />

        <SplitFrame view={view} />

        <hr className="border-white/10" />

        <WithinCountryControl view={view} />

        <hr className="border-white/10" />

        <TamperProof initialFacts={initialFacts} />

        <hr className="border-white/10" />

        <LiveCell />

        <footer className="border-t border-white/10 pt-5 text-[11px] text-white/30">
          Offline golden run · the RED/GREEN verdict is the real{" "}
          <code className="text-white/50">python -m amber.cli</code> exit code · point the UI at any
          packet directory with <code className="text-white/50">AMBER_PACKET_DIR</code>.
        </footer>
      </div>
    </main>
  );
}
