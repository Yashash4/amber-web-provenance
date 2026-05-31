"use client";

import type { PacketView, PerCaptureView } from "@/lib/packet";
import { urlForCountry } from "@/lib/url";

const FLAGS: Record<string, string> = { DE: "🇩🇪", BE: "🇧🇪", FR: "🇫🇷", NL: "🇳🇱" };

function countryName(c: string): string {
  return { DE: "Germany", BE: "Belgium", FR: "France", NL: "Netherlands" }[c] ?? c;
}

const DASH = "·";

/**
 * One country half of the comparison panel: the flag, the struck gross price,
 * the big net-of-tax price, and the VAT rate badge. The dearer side is tinted
 * amber (the signed gap lives there); the cheaper side stays neutral.
 *
 * NOTE on the alignment fix: this half is a grid/flex child that must be allowed
 * to SHRINK. Flex/grid children default to `min-width: auto`, which is the
 * MIN-CONTENT width, so the big price and the long product URL would force the
 * column wider than its track and blow the row past the panel (the Belgium half
 * got clipped by the panel's `overflow-hidden`). `min-w-0` here (and on the URL
 * anchor) lets the column shrink to its grid track so both halves stay equal
 * width with no horizontal overflow.
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
      className={`min-w-0 rounded-xl border p-5 ${
        dearer
          ? "border-amber/40 bg-gradient-to-b from-amber/10 to-transparent"
          : "border-white/10 bg-white/[0.02]"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="text-3xl leading-none">{FLAGS[country] ?? "🌐"}</span>
          <div className="min-w-0">
            <div className="truncate text-sm font-bold text-white/90">{countryName(country)}</div>
            <div className="text-[11px] text-white/40">{country}</div>
          </div>
        </div>
        <span
          className={`shrink-0 rounded-md px-2 py-1 text-[11px] font-semibold ${
            dearer ? "bg-amber/15 text-amber" : "bg-white/5 text-white/55"
          }`}
        >
          VAT {(Number(vatRate) * 100).toFixed(0)}%
        </span>
      </div>

      <div className="mt-5">
        <div className="text-[11px] text-white/40 line-through">gross {gross} EUR incl. VAT</div>
        <div className="mt-1 flex min-w-0 items-baseline gap-1.5">
          <span className="text-[13px] text-white/50">EUR</span>
          <span
            className={`text-3xl font-black leading-none tracking-tight tabular-nums sm:text-4xl xl:text-5xl ${
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
          className="mt-4 block min-w-0 max-w-full truncate text-[11px] text-white/35 underline decoration-dotted underline-offset-2 hover:text-amber"
          title={url}
        >
          {url}
        </a>
      ) : null}
    </div>
  );
}

/**
 * THE CATCH (supporting data panel): the dearer country vs the cheaper country
 * for the same SKU, side by side, with the signed net-of-tax gap badge centered
 * in the seam. Rendered FROM the signed packet. The center badge states the
 * SIGNED FACT only: never "violation," never an invented threshold number.
 * Framed as a brand monitoring its OWN SKUs.
 *
 * Alignment: the comparison is a 3-track CSS grid
 * `grid-cols-[1fr_auto_1fr]` at lg, so the two country halves are exactly equal
 * width (each gets a `1fr` track) and the gap badge sits in the centered `auto`
 * track in the seam. Below lg it stacks to a single column (the badge centered
 * between the halves). Combined with `min-w-0` on the halves this guarantees no
 * horizontal overflow at any width.
 */
export function SplitFrame({ view }: { view: PacketView }) {
  const dearerCountry = view.moreExpensiveCountry ?? view.countries[0];
  const cheaperCountry = view.cheaperCountry ?? view.countries[1];

  const capFor = (c: string | null): PerCaptureView | undefined =>
    view.perCapture.find((p) => p.country === c);
  const dearerCap = capFor(dearerCountry);
  const cheaperCap = capFor(cheaperCountry);

  return (
    <div className="panel-card glow-amber flex flex-col overflow-hidden p-4 sm:p-5">
      <PanelHead
        eyebrow="The catch · same SKU, two markets"
        title={view.skuLabel}
        sub={
          <>
            GTIN {view.canonicalGtin ?? "n/a"} ({view.gtinConfidence ?? "n/a"}) {DASH} dispatched
            same-second {DASH} a brand monitoring its OWN SKUs
          </>
        }
      />

      {/* The comparison grid: 1fr | auto | 1fr at lg, stacked below. */}
      <div className="mt-4 grid grid-cols-1 items-center gap-4 lg:grid-cols-[1fr_auto_1fr]">
        {dearerCap && dearerCountry ? (
          <CountryHalf
            country={dearerCountry}
            gross={dearerCap.priceGross}
            net={view.moreExpensiveNet ?? dearerCap.priceNet}
            vatRate={dearerCap.vatRate}
            url={urlForCountry(view.url, dearerCountry)}
            dearer
          />
        ) : (
          <div />
        )}

        {/* Center gap badge: lives in the centered `auto` track. */}
        <div className="z-10 mx-auto flex flex-col items-center">
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
        ) : (
          <div />
        )}
      </div>

      {/* The signed-fact statement strip. */}
      <div className="mt-5 rounded-lg border border-amber/30 bg-amber/[0.06] px-4 py-3">
        <div className="flex items-center gap-2 text-sm font-extrabold tracking-wide text-amber">
          <span className="h-2 w-2 shrink-0 rounded-full bg-amber" aria-hidden />
          PRICE DELTA DETECTED {DASH} signed, net-of-tax, chain of custody intact
        </div>
        <p className="mt-1.5 text-[12px] leading-relaxed text-white/55">
          The signed packet records this fact only. A human draws any legal conclusion. Geo is{" "}
          <span className="text-white/75">EXIT_ONLY</span> (the country is the proxy exit, not a GPS
          witness); captures were dispatched the same instant, not witnessed the same instant.
        </p>
      </div>

      <VatInversionLine view={view} />
    </div>
  );
}

/**
 * The VAT-inversion line: answers the "the gap is just VAT" objection. When the
 * dearer-net country is also the LOWER-VAT country, the gap cannot be a tax
 * artifact (stripping the higher tax would make it cheaper, not dearer). Derived
 * from the packet's own per-capture VAT rates; only shown when the inversion
 * actually holds.
 */
export function VatInversionLine({ view }: { view: PacketView }) {
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

/**
 * A compact panel heading used inside the dashboard cards: eyebrow label, title,
 * optional sub-line. (Sits at the top of a card, not as a full-width slide.)
 */
export function PanelHead({
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
      <h2 className="text-sm font-bold leading-snug text-white/90">{title}</h2>
      {sub ? <div className="text-[11px] leading-snug text-white/40">{sub}</div> : null}
    </header>
  );
}
