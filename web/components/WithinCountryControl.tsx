"use client";

import type { PacketView, PerCaptureView, WithinCountryView } from "@/lib/packet";
import { PanelHead } from "@/components/SplitFrame";

const FLAGS: Record<string, string> = { DE: "🇩🇪", BE: "🇧🇪", FR: "🇫🇷", NL: "🇳🇱" };

function countryName(c: string): string {
  return { DE: "Germany", BE: "Belgium", FR: "France", NL: "Netherlands" }[c] ?? c;
}

/** One residential-exit card: the exit IP, its signed net price, agreement dot. */
function ExitCard({ pc, dearer }: { pc: PerCaptureView; dearer: boolean }) {
  return (
    <div
      className={`min-w-0 rounded-xl border p-3.5 transition-colors ${
        dearer ? "border-amber/30 bg-amber/[0.05]" : "border-verified/25 bg-verified/[0.04]"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-[11px] uppercase tracking-wide text-white/45">
          {pc.captureId}
        </span>
        <span className="inline-flex shrink-0 items-center gap-1 rounded bg-verified/15 px-1.5 py-0.5 text-[10px] font-semibold text-verified">
          <span className="h-1.5 w-1.5 rounded-full bg-verified" aria-hidden />
          agree
        </span>
      </div>
      <div className="mt-2.5">
        <div className="text-[10px] uppercase tracking-wide text-white/40">net of tax</div>
        <div
          className={`text-2xl font-black tabular-nums ${dearer ? "text-amber" : "text-verified"}`}
        >
          EUR {pc.priceNet}
        </div>
      </div>
      <div className="mt-2.5 flex items-center justify-between gap-2 text-[11px]">
        <span className="truncate font-mono text-white/45">exit {pc.exitIp}</span>
        <span className="shrink-0 text-white/35">HTTP {pc.httpStatus ?? "n/a"}</span>
      </div>
    </div>
  );
}

/** One country block: header summary plus its residential-exit cards. */
function CountryBlock({
  summary,
  captures,
  dearer,
}: {
  summary: WithinCountryView;
  captures: PerCaptureView[];
  dearer: boolean;
}) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="text-2xl leading-none">{FLAGS[summary.country] ?? "🌐"}</span>
          <div className="min-w-0">
            <div className="truncate text-sm font-bold text-white/90">
              {countryName(summary.country)}
            </div>
            <div className="text-[11px] text-white/40">{summary.nExits} residential exits</div>
          </div>
        </div>
        <div className="shrink-0 text-right">
          <div className="text-[10px] uppercase tracking-wide text-white/40">intra spread</div>
          <div
            className={`text-lg font-black tabular-nums ${
              summary.intraSpread === "0.00" ? "text-verified" : "text-amber"
            }`}
          >
            EUR {summary.intraSpread}
          </div>
        </div>
      </div>
      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-3">
        {captures.map((pc) => (
          <ExitCard key={pc.captureId} pc={pc} dearer={dearer} />
        ))}
      </div>
    </div>
  );
}

/**
 * THE WITHIN-COUNTRY CONTROL (supporting data panel): correlation turned into a
 * controlled experiment. Every in-country residential exit agrees to the cent;
 * the only variable changed across the cross-country delta is the country. This
 * rules out the "it's just exit-IP noise" explanation.
 */
export function WithinCountryControl({ view }: { view: PacketView }) {
  const byCountry = new Map<string, PerCaptureView[]>();
  for (const pc of view.perCapture) {
    const list = byCountry.get(pc.country) ?? [];
    list.push(pc);
    byCountry.set(pc.country, list);
  }
  const dearer = view.moreExpensiveCountry;

  return (
    <div className="panel-card flex flex-col p-4 sm:p-5">
      <PanelHead
        eyebrow="The within-country control"
        title="Multiple residential exits per country, all in agreement"
        sub="Many residential IPs per country, all dispatched the same second."
      />

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        {view.withinCountry.map((c) => (
          <CountryBlock
            key={c.country}
            summary={c}
            captures={byCountry.get(c.country) ?? []}
            dearer={c.country === dearer}
          />
        ))}
      </div>

      {view.allIntraCountryAgree !== null && (
        <div className="mt-4 flex items-start gap-2 rounded-lg border border-verified/25 bg-verified/[0.05] px-4 py-2.5 text-[12px] leading-relaxed text-white/65">
          <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-verified" aria-hidden />
          {view.allIntraCountryAgree
            ? "All in-country exits agree to the cent (spread EUR 0.00), so the only thing we changed was the country: a controlled experiment, not exit-IP noise."
            : "Some in-country exits disagree, flagged honestly; this is not a clean controlled delta."}
        </div>
      )}
    </div>
  );
}
