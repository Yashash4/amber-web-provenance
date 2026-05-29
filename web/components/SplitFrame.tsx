"use client";

import type { PacketView, PerCaptureView } from "@/lib/packet";

const FLAGS: Record<string, string> = { DE: "🇩🇪", BE: "🇧🇪", FR: "🇫🇷", NL: "🇳🇱" };

function countryName(c: string): string {
  return { DE: "Germany", BE: "Belgium", FR: "France", NL: "Netherlands" }[c] ?? c;
}

/**
 * The honest simultaneity phrase for the banner, derived from the packet flags.
 * NEVER claims "same second" / "witnessed same second" when the witnessed
 * responses span more than a second (residential fetches each take seconds, so a
 * witnessed-same-second batch is physically impossible). We word it as DISPATCH:
 *
 *  - dispatched within the same second → "dispatched the same second across N exits"
 *  - witnessed responses also within a second → can additionally say "witnessed
 *    within one second" (rare, but honest when true)
 *  - neither known → no simultaneity clause at all (never overclaim).
 */
function simultaneityClause(view: PacketView, nExits: number): string | null {
  if (view.dispatchedSameSecond === true) {
    return `dispatched the same second across ${nExits} residential exit${
      nExits === 1 ? "" : "s"
    }`;
  }
  if (view.sameSecondBatch) {
    // Witnessed responses landed within one second (only honest when actually true).
    return "responses witnessed within one second";
  }
  return null;
}

/** The short header sub-line label for batch timing — dispatch-worded, honest. */
function batchTimingLabel(view: PacketView): string {
  if (view.dispatchedSameSecond === true) return "dispatched same-second batch";
  if (view.dispatchedSameSecond === false)
    return "dispatch spread > 1s (honestly flagged)";
  if (view.sameSecondBatch) return "responses within one second";
  return "multi-second batch (honestly flagged)";
}

/** One residential session card (one capture / one exit IP). */
function SessionCard({ pc, primary }: { pc: PerCaptureView; primary: boolean }) {
  return (
    <div
      className={`rounded-md border px-3 py-2 ${
        primary ? "border-amber/40 bg-panel" : "border-white/10 bg-black/30"
      }`}
    >
      <div className="flex items-center justify-between text-xs text-white/50">
        <span>{pc.captureId}</span>
        <span>exit {pc.exitIp}</span>
      </div>
      <div className="mt-1 flex items-baseline justify-between">
        <div>
          <div className="text-[11px] uppercase tracking-wide text-white/40">gross</div>
          <div className="text-lg text-white/80">
            {pc.priceGross} {pc.currency}
          </div>
        </div>
        <div className="text-right">
          <div className="text-[11px] uppercase tracking-wide text-amber/70">net of tax</div>
          <div className="text-xl font-bold text-amber">
            {pc.priceNet} {pc.currency}
          </div>
        </div>
      </div>
      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-white/50">
        <span>VAT {(Number(pc.vatRate) * 100).toFixed(0)}%</span>
        <span>{pc.contentLanguage ?? "—"}</span>
        <span>HTTP {pc.httpStatus ?? "—"}</span>
        <span className="text-white/40">geo: {pc.geoAgreement}</span>
        <span className="text-white/70">{pc.state}</span>
      </div>
    </div>
  );
}

/** One country column = all of that country's residential sessions. */
function CountryColumn({ country, captures }: { country: string; captures: PerCaptureView[] }) {
  const flag = FLAGS[country] ?? "🌐";
  return (
    <div className="flex-1">
      <div className="mb-2 flex items-center gap-2">
        <span className="text-2xl">{flag}</span>
        <div>
          <div className="text-sm font-bold">{countryName(country)}</div>
          <div className="text-[11px] text-white/40">
            {captures.length} residential exit{captures.length === 1 ? "" : "s"}
          </div>
        </div>
      </div>
      <div className="flex flex-col gap-2">
        {captures.map((pc, i) => (
          <SessionCard key={pc.captureId} pc={pc} primary={i === 0} />
        ))}
      </div>
    </div>
  );
}

/**
 * The split-frame catch: the hero pair of countries side by side, rendered
 * FROM the signed packet. The banner states the SIGNED FACT only — never
 * "violation," never an invented threshold number. Framed as a brand
 * monitoring its OWN SKUs.
 */
export function SplitFrame({ view }: { view: PacketView }) {
  const byCountry = new Map<string, PerCaptureView[]>();
  for (const pc of view.perCapture) {
    const list = byCountry.get(pc.country) ?? [];
    list.push(pc);
    byCountry.set(pc.country, list);
  }
  const countries = view.countries.length ? view.countries : Array.from(byCountry.keys());

  return (
    <section className="space-y-3">
      <header className="space-y-1">
        <div className="text-xs uppercase tracking-widest text-amber/70">
          Split-frame catch — a brand monitoring its OWN SKUs
        </div>
        <h2 className="text-lg font-bold">{view.skuLabel}</h2>
        <div className="text-[11px] text-white/40">
          {view.url} · GTIN {view.canonicalGtin ?? "—"} ({view.gtinConfidence ?? "—"}) ·{" "}
          {batchTimingLabel(view)} · requested_at {view.requestedAtValues.join(", ")}
        </div>
      </header>

      <SignedFactBanner view={view} />

      <div className="flex flex-col gap-4 md:flex-row">
        {countries.map((c) => (
          <CountryColumn key={c} country={c} captures={byCountry.get(c) ?? []} />
        ))}
      </div>
    </section>
  );
}

/**
 * The banner. States the SIGNED FACT only. The wording is exactly the locked
 * phrasing from docs/40-SUBMISSION.md + 24-GROUNDING.md: no "violation," no
 * invented threshold number. It reflects the packet's primary finding —
 * a net-of-tax price delta OR an access/payment denial.
 */
function SignedFactBanner({ view }: { view: PacketView }) {
  const isDenial = Boolean(view.accessDenial);
  const clause = simultaneityClause(view, view.perCapture.length);
  if (isDenial) {
    return (
      <div className="rounded-md border-2 border-amber bg-amber/15 px-4 py-3">
        <div className="text-sm font-extrabold tracking-wide text-amber">
          ACCESS / PAYMENT DENIAL DETECTED — signed
          {clause ? `, ${clause}` : ""}, chain of custody
        </div>
        <div className="mt-1 text-xs text-white/60">
          A residential session was refused access/checkout that another country was granted
          {clause ? `, ${clause},` : ""} on the same SKU. The signed packet records the fact; a
          human draws any legal conclusion.
        </div>
      </div>
    );
  }
  return (
    <div className="rounded-md border-2 border-amber bg-amber/15 px-4 py-3">
      <div className="text-sm font-extrabold tracking-wide text-amber">
        PRICE DELTA DETECTED — signed, net-of-tax
        {clause ? `, ${clause}` : ""}, chain of custody
      </div>
      <div className="mt-2 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
        <Stat label="gross delta" value={`${view.grossDelta ?? "—"} EUR`} muted />
        <Stat label="net-of-tax delta" value={`${view.netDelta ?? "—"} EUR`} />
        <Stat
          label="cheaper (net)"
          value={`${view.cheaperCountry ?? "—"} ${view.cheaperNet ?? ""}`}
        />
        <Stat
          label="more expensive (net)"
          value={`${view.moreExpensiveCountry ?? "—"} ${view.moreExpensiveNet ?? ""}`}
        />
      </div>
      <div className="mt-2 text-xs text-white/60">
        Same gross price both countries; the delta is purely net-of-tax. The signed packet records
        this fact only — a human draws any legal conclusion.
      </div>
    </div>
  );
}

function Stat({ label, value, muted }: { label: string; value: string; muted?: boolean }) {
  return (
    <div className="rounded bg-black/30 px-2 py-1">
      <div className="text-[10px] uppercase tracking-wide text-white/40">{label}</div>
      <div className={muted ? "text-white/60" : "font-bold text-amber"}>{value}</div>
    </div>
  );
}
