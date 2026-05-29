"use client";

import type { PacketView } from "@/lib/packet";

const FLAGS: Record<string, string> = { DE: "🇩🇪", BE: "🇧🇪", FR: "🇫🇷", NL: "🇳🇱" };

/**
 * The within-country control — correlation turned into a controlled experiment.
 * Every in-country residential exit agrees to the cent; the only variable
 * changed across the cross-country delta is the country. This rules out the
 * defence's best innocent explanation on camera.
 */
export function WithinCountryControl({ view }: { view: PacketView }) {
  return (
    <section className="space-y-3">
      <header className="space-y-1">
        <div className="text-xs uppercase tracking-widest text-amber/70">
          The within-country control
        </div>
        <p className="text-xs text-white/50">
          Multiple residential IPs per country, same second. Intra-country prices agree; the
          only thing changed across the cross-country delta is the country.
        </p>
      </header>

      <div className="grid gap-3 sm:grid-cols-2">
        {view.withinCountry.map((c) => {
          const agree = c.agreement === "AGREE";
          return (
            <div
              key={c.country}
              className={`rounded-md border px-3 py-2 ${
                agree ? "border-verified/40 bg-verified/5" : "border-amber/40 bg-amber/5"
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-2 text-sm font-bold">
                  <span className="text-xl">{FLAGS[c.country] ?? "🌐"}</span>
                  {c.country}
                </span>
                <span
                  className={`rounded px-2 py-0.5 text-[11px] font-bold ${
                    agree ? "bg-verified/20 text-verified" : "bg-amber/20 text-amber"
                  }`}
                >
                  {c.agreement}
                </span>
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {c.netPrices.map((p, i) => (
                  <span
                    key={i}
                    className="rounded bg-black/40 px-2 py-0.5 text-xs text-white/80"
                  >
                    {p}
                  </span>
                ))}
              </div>
              <div className="mt-2 text-[11px] text-white/40">
                {c.nExits} exits · intra-country spread {c.intraSpread} · net {c.netMin}–{c.netMax}
              </div>
            </div>
          );
        })}
      </div>

      {view.allIntraCountryAgree !== null && (
        <div className="text-xs text-white/50">
          {view.allIntraCountryAgree
            ? "All in-country exits agree to the cent — the cross-country delta is the only thing that moved."
            : "Some in-country exits disagree — flagged honestly; this is not a clean controlled delta."}
        </div>
      )}
    </section>
  );
}
