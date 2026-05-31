import { BusinessNumber } from "@/components/BusinessNumber";
import { Header } from "@/components/Header";
import { MetricStrip } from "@/components/MetricStrip";
import { ProvenanceFooter } from "@/components/ProvenanceFooter";
import { SplitFrame } from "@/components/SplitFrame";
import { TamperProof } from "@/components/TamperProof";
import { WithinCountryControl } from "@/components/WithinCountryControl";
import { loadPacketView, readWorkingFacts } from "@/lib/packet";

/**
 * The Amber evidence console: a dense, dark SaaS dashboard a judge EXPLORES, not
 * a vertical slide deck. Render order, top to bottom:
 *
 *   1. Header bar (wordmark, one-liner, status chips).
 *   2. Metric strip: the headline facts as a scannable tile bar.
 *   3. The verifier console (centerpiece): break the signed packet RED, fix it
 *      GREEN, all from the REAL recorded verify_packet output.
 *   4. Supporting data panels in a grid: the same-SKU two-market comparison and
 *      the buyer-volume business number side by side, then the within-country
 *      control full width.
 *   5. The compact signed-provenance footer.
 *
 * Everything renders from the bundled static packet view (no request-time fs, no
 * Python, no server fetch); this page prerenders to fully static output.
 */
export default function Home() {
  const view = loadPacketView();
  const initialFacts = readWorkingFacts();

  return (
    <main className="dash-bg min-h-screen pb-12">
      <Header />
      <div className="mx-auto max-w-6xl space-y-5 px-4 py-6 sm:px-6 lg:px-8">
        {/* 2. Dashboard metric strip. */}
        <MetricStrip view={view} />

        {/* 3. Centerpiece: the interactive verifier console. */}
        <TamperProof initialFacts={initialFacts} />

        {/* 4. Supporting data panels. */}
        <div className="grid gap-5 xl:grid-cols-[1.6fr_1fr]">
          <SplitFrame view={view} />
          <BusinessNumber view={view} />
        </div>
        <WithinCountryControl view={view} />

        {/* 5. Provenance footer. */}
        <ProvenanceFooter />
      </div>
    </main>
  );
}
