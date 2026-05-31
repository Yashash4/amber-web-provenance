"use client";

import type { PacketView } from "@/lib/packet";
import { SectionHead } from "@/components/SplitFrame";

/** Group a plain integer with thin thousands separators (locale-independent). */
function groupThousands(n: number): string {
  return n.toLocaleString("en-US");
}

/**
 * THE BUSINESS NUMBER: the signed EUR/unit delta multiplied by a BUYER-SUPPLIED
 * annual volume, equals a EUR/yr recoverable-margin figure. The volume is
 * labeled an ASSUMPTION on screen (never observed); the per-unit delta is the
 * signed measurement. This is the one money card that turns a forensic curiosity
 * into a CRO-legible outcome: Amber signs the per-unit delta, the brand supplies
 * the volume.
 */
export function BusinessNumber({ view }: { view: PacketView }) {
  const bi = view.businessImpact;
  if (!bi) return null;
  const eur = Number(bi.recoverableMarginEurPerYear);
  const pretty = Number.isFinite(eur) ? groupThousands(eur) : bi.recoverableMarginEurPerYear;

  return (
    <section className="space-y-3">
      <SectionHead
        eyebrow="The business number"
        title="Recoverable margin per year"
        sub="The signed per-unit delta, scaled by the brand's own diverted-volume estimate."
      />

      <div className="panel-amber p-5 sm:p-6">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-center">
          {/* The equation. */}
          <div className="flex flex-1 flex-wrap items-center gap-x-3 gap-y-2 text-white/80">
            <Token value={`EUR ${bi.netDeltaPerUnit}`} label="signed delta / unit" accent />
            <span className="text-2xl font-light text-white/40">x</span>
            <Token
              value={groupThousands(bi.annualDivertedUnits)}
              label="units / yr (assumption)"
            />
            <span className="text-2xl font-light text-white/40">=</span>
          </div>

          {/* The headline figure. */}
          <div className="rounded-xl border border-amber/40 bg-[#0a0a0c]/60 px-6 py-4 text-center lg:text-right">
            <div className="eyebrow text-amber/70">recoverable margin / year</div>
            <div className="mt-1 text-4xl font-black tabular-nums text-amber sm:text-5xl">
              EUR {pretty}
            </div>
          </div>
        </div>

        <div className="mt-4 flex items-start gap-2 rounded-lg border border-white/10 bg-black/30 px-4 py-2.5 text-[11px] text-white/50">
          <span className="mt-0.5 shrink-0 rounded bg-amber/15 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-amber/90">
            buyer-supplied assumption
          </span>
          <span>
            {groupThousands(bi.annualDivertedUnits)} units / yr is a {bi.volumeBasis}, not an Amber
            measurement. Amber signs the per-unit delta; the brand supplies the volume.
          </span>
        </div>
      </div>
    </section>
  );
}

function Token({
  value,
  label,
  accent,
}: {
  value: string;
  label: string;
  accent?: boolean;
}) {
  return (
    <div
      className={`rounded-lg border px-3.5 py-2 text-center ${
        accent ? "border-amber/40 bg-amber/10" : "border-white/12 bg-white/[0.03]"
      }`}
    >
      <div
        className={`text-xl font-black tabular-nums ${accent ? "text-amber" : "text-white/85"}`}
      >
        {value}
      </div>
      <div className="text-[10px] uppercase tracking-wide text-white/40">{label}</div>
    </div>
  );
}
