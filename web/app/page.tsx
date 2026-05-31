import { BusinessNumber } from "@/components/BusinessNumber";
import { Header } from "@/components/Header";
import { LiveCell } from "@/components/LiveCell";
import { ProvenanceFooter } from "@/components/ProvenanceFooter";
import { SplitFrame } from "@/components/SplitFrame";
import { TamperProof } from "@/components/TamperProof";
import { WithinCountryControl } from "@/components/WithinCountryControl";
import { loadPacketView, readWorkingFacts } from "@/lib/packet";

export default function Home() {
  // Render the committed packet view from the bundled static data (no
  // request-time filesystem, no Python). Seed the tamper-proof editor's working
  // copy with the same sealed packet bytes.
  const view = loadPacketView();
  const initialFacts = readWorkingFacts();

  return (
    <main className="dash-bg min-h-screen">
      <Header />
      <div className="mx-auto max-w-6xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
        <SplitFrame view={view} />
        <BusinessNumber view={view} />
        <WithinCountryControl view={view} />
        <TamperProof initialFacts={initialFacts} />
        <LiveCell />
        <ProvenanceFooter />
      </div>
    </main>
  );
}
