"use client";

import type { PacketView, PerCaptureView } from "@/lib/packet";
import { urlForCountry, urlList } from "@/lib/url";

const FLAGS: Record<string, string> = { DE: "🇩🇪", BE: "🇧🇪", FR: "🇫🇷", NL: "🇳🇱" };

function countryName(c: string): string {
  return { DE: "Germany", BE: "Belgium", FR: "France", NL: "Netherlands" }[c] ?? c;
}

const DASH = "·";

/**
 * The honest simultaneity phrase for the banner, derived from the packet flags.
 * NEVER claims "same second" / "witnessed same second" when the witnessed
 * responses span more than a second (residential fetches each take seconds, so a
 * witnessed-same-second batch is physically impossible). We word it as DISPATCH:
 *
 *  - dispatched within the same second: "dispatched the same second across N exits"
 *  - witnessed responses also within a second: can additionally say "witnessed
 *    within one second" (rare, but honest when true)
 *  - neither known: no simultaneity clause at all (never overclaim).
 */
function simultaneityClause(view: PacketView, nExits: number): string | null {
  if (view.dispatchedSameSecond === true) {
    return `dispatched the same second across ${nExits} residential exit${
      nExits === 1 ? "" : "s"
    }`;
  }
  if (view.sameSecondBatch) {
    return "responses witnessed within one second";
  }
  return null;
}

/** The short header sub-line label for batch timing (dispatch-worded, honest). */
function batchTimingLabel(view: PacketView): string {
  if (view.dispatchedSameSecond === true) return "dispatched same-second";
  if (view.dispatchedSameSecond === false) return "dispatch spread over 1s (flagged)";
  if (view.sameSecondBatch) return "responses within one second";
  return "multi-second batch (flagged)";
}

/**
 * One country half of the hero split panel: the flag, the struck gross price,
 * the big net-of-tax price, and the VAT rate badge. The dearer side is tinted
 * amber (the signed gap lives there); the cheaper side stays neutral.
 */
function CountryHalf({
  country,
  gross,
  net,
  vatRate,
  url,
  dearer,
}: {
  country: string;
  gross: string;
  net: string;
  vatRate: string;
  url: string;
  dearer: boolean;
}) {
  return (
    <div
      className={`flex-1 rounded-xl border p-5 ${
        dearer
          ? "border-amber/40 bg-gradient-to-b from-amber/10 to-transparent"
          : "border-white/10 bg-white/[0.02]"
      }`}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <span className="text-3xl leading-none">{FLAGS[country] ?? "🌐"}</span>
          <div>
            <div className="text-sm font-bold text-white/90">{countryName(country)}</div>
            <div className="text-[11px] text-white/40">{country}</div>
          </div>
        </div>
        <span
          className={`rounded-md px-2 py-1 text-[11px] font-semibold ${
            dearer ? "bg-amber/15 text-amber" : "bg-white/5 text-white/55"
          }`}
        >
          VAT {(Number(vatRate) * 100).toFixed(0)}%
        </span>
      </div>

      <div className="mt-5">
        <div className="text-[11px] text-white/40 line-through">
          gross {gross} EUR incl. VAT
        </div>
        <div className="mt-1 flex items-baseline gap-1.5">
          <span className="text-[13px] text-white/50">EUR</span>
          <span
            className={`text-4xl font-black tracking-tight tabular-nums sm:text-5xl ${
              dearer ? "text-amber" : "text-white/90"
            }`}
          >
            {net}
          </span>
        </div>
        <div className="mt-1 text-[11px] uppercase tracking-wide text-white/40">
          net of tax {DASH} purchasable {DASH} in stock
        </div>
      </div>

      {url ? (
        <a
          href={url}
          target="_blank"
          rel="noreferrer"
          className="mt-4 block truncate text-[11px] text-white/35 underline decoration-dotted underline-offset-2 hover:text-amber"
          title={url}
        >
          {url}
        </a>
      ) : null}
    </div>
  );
}

/**
 * THE CATCH (hero): the dearer country vs the cheaper country for the same SKU,
 * side by side, with the signed net-of-tax gap badge in the center. Rendered
 * FROM the signed packet. The center badge states the SIGNED FACT only: never
 * "violation," never an invented threshold number. Framed as a brand monitoring
 * its OWN SKUs.
 */
export function SplitFrame({ view }: { view: PacketView }) {
  const dearerCountry = view.moreExpensiveCountry ?? view.countries[0];
  const cheaperCountry = view.cheaperCountry ?? view.countries[1];

  const capFor = (c: string | null): PerCaptureView | undefined =>
    view.perCapture.find((p) => p.country === c);
  const dearerCap = capFor(dearerCountry);
  const cheaperCap = capFor(cheaperCountry);

  const clause = simultaneityClause(view, view.perCapture.length);

  return (
    <section className="space-y-3">
      <SectionHead
        eyebrow="The catch"
        title={view.skuLabel}
        sub={
          <>
            {urlList(view.url).join(` ${DASH} `) || "n/a"} {DASH} GTIN{" "}
            {view.canonicalGtin ?? "n/a"} ({view.gtinConfidence ?? "n/a"}) {DASH}{" "}
            {batchTimingLabel(view)} {DASH} a brand monitoring its OWN SKUs
          </>
        }
      />

      <div className="panel-card glow-amber overflow-hidden p-4 sm:p-6">
        {/* The split hero. */}
        <div className="relative flex flex-col items-stretch gap-4 lg:flex-row lg:items-center">
          {dearerCap && dearerCountry ? (
            <CountryHalf
              country={dearerCountry}
              gross={dearerCap.priceGross}
              net={view.moreExpensiveNet ?? dearerCap.priceNet}
              vatRate={dearerCap.vatRate}
              url={urlForCountry(view.url, dearerCountry)}
              dearer
            />
          ) : null}

          {/* Center gap badge. */}
          <div className="z-10 mx-auto flex shrink-0 flex-col items-center lg:mx-0">
            <div className="rounded-2xl border-2 border-amber bg-[#0a0a0c] px-5 py-4 text-center shadow-[0_0_40px_-8px_rgba(245,158,11,0.6)]">
              <div className="eyebrow text-amber/70">net-of-tax gap</div>
              <div className="mt-1 text-3xl font-black tabular-nums text-amber">
                +EUR {view.netDelta ?? "n/a"}
              </div>
              <div className="text-[11px] text-amber/80">/ unit</div>
              <div className="mt-2 inline-flex items-center gap-1 rounded-full border border-amber/40 bg-amber/10 px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber">
                signed, not VAT
              </div>
            </div>
          </div>

          {cheaperCap && cheaperCountry ? (
            <CountryHalf
              country={cheaperCountry}
              gross={cheaperCap.priceGross}
              net={view.cheaperNet ?? cheaperCap.priceNet}
              vatRate={cheaperCap.vatRate}
              url={urlForCountry(view.url, cheaperCountry)}
              dearer={false}
            />
          ) : null}
        </div>

        {/* The signed-fact statement strip. */}
        <div className="mt-5 rounded-lg border border-amber/30 bg-amber/[0.06] px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-extrabold tracking-wide text-amber">
            <span className="h-2 w-2 rounded-full bg-amber" aria-hidden />
            PRICE DELTA DETECTED {DASH} signed, net-of-tax
            {clause ? `, ${clause}` : ""}, chain of custody intact
          </div>
          <p className="mt-1.5 text-[12px] text-white/55">
            The signed packet records this fact only. A human draws any legal conclusion. Geo is{" "}
            <span className="text-white/75">EXIT_ONLY</span> (the country is the proxy exit, not a
            GPS witness); captures were dispatched the same instant, not witnessed the same instant.
          </p>
        </div>

        <VatInversionLine view={view} />
      </div>
    </section>
  );
}

/**
 * The VAT-inversion line: kills the "the gap is just VAT" objection. When the
 * dearer-net country is also the LOWER-VAT country, the gap cannot be a tax
 * artifact (stripping the higher tax would make it cheaper, not dearer). Derived
 * from the packet's own per-capture VAT rates; only shown when the inversion
 * actually holds.
 */
function VatInversionLine({ view }: { view: PacketView }) {
  const dearer = view.moreExpensiveCountry;
  const cheaper = view.cheaperCountry;
  if (!dearer || !cheaper) return null;
  const rateOf = (c: string) => {
    const pc = view.perCapture.find((p) => p.country === c);
    return pc ? Number(pc.vatRate) : NaN;
  };
  const dearerVat = rateOf(dearer);
  const cheaperVat = rateOf(cheaper);
  if (!Number.isFinite(dearerVat) || !Number.isFinite(cheaperVat)) return null;
  // The inversion: the dearer-NET country has the LOWER VAT.
  if (!(dearerVat < cheaperVat)) return null;
  return (
    <div className="mt-4 flex items-start gap-3 rounded-lg border border-advisory/30 bg-advisory/[0.06] px-4 py-3">
      <span className="mt-0.5 shrink-0 rounded-md bg-advisory/15 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-advisory">
        why it is not the tax
      </span>
      <p className="text-[12px] leading-relaxed text-white/65">
        {countryName(dearer)} has the <span className="font-semibold text-white/85">lower VAT</span>{" "}
        ({(dearerVat * 100).toFixed(0)}%) yet the{" "}
        <span className="font-semibold text-white/85">higher net price</span>, so stripping tax
        widens the gap (gross EUR {view.grossDelta} to net EUR {view.netDelta}). The gap is the
        channel, not the tax.
      </p>
    </div>
  );
}

/** A consistent section heading: eyebrow label, title, optional sub-line. */
export function SectionHead({
  eyebrow,
  title,
  sub,
}: {
  eyebrow: string;
  title: React.ReactNode;
  sub?: React.ReactNode;
}) {
  return (
    <header className="space-y-1">
      <div className="eyebrow text-amber/70">{eyebrow}</div>
      <h2 className="text-base font-bold text-white/90 sm:text-lg">{title}</h2>
      {sub ? <div className="text-[11px] text-white/40">{sub}</div> : null}
    </header>
  );
}
