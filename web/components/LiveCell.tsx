"use client";

import { useState } from "react";

import { SectionHead } from "@/components/SplitFrame";

/**
 * The ONE live-capture cell. In this self-contained deployment there is no
 * Bright Data credential and no Python backend to probe, so the cell reports the
 * honest pending state and never fabricates a live result. In the full-stack
 * build (Python core + BRIGHTDATA_* credentials present) this cell arms and the
 * operator runs the live DE/BE capture; here it states that everything above is
 * the committed offline golden run.
 */
export function LiveCell() {
  const [checked, setChecked] = useState(false);

  return (
    <section className="space-y-3">
      <SectionHead
        eyebrow="Live capture cell"
        title="The single live element, which never fakes a result"
        sub="Everything above is the committed offline golden run."
      />

      <div
        className={`panel-card flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between ${
          checked ? "border-amber/40" : ""
        }`}
      >
        <div className="flex-1">
          {!checked ? (
            <div className="text-sm text-white/55">
              Click to see whether this deployment has Bright Data credentials wired in.
            </div>
          ) : (
            <>
              <div className="flex items-center gap-2">
                <span className="chip-dot h-2.5 w-2.5 rounded-full bg-amber" aria-hidden />
                <span className="text-sm font-bold text-amber">
                  LIVE CAPTURE {"·"} PENDING BRIGHT DATA CREDENTIALS
                </span>
              </div>
              <p className="mt-2 text-[12px] text-white/60">
                This hosted demo plays the committed offline golden packet (the real signed DE/BE
                AirPods 4 capture above). The live DE/BE capture runs in the full-stack build with
                the Python core on PATH and <code className="text-amber">BRIGHTDATA_*</code>{" "}
                credentials set; it never fabricates a live result here.
              </p>
              <pre className="mt-2 overflow-x-auto rounded-md bg-black/55 px-2 py-1 font-mono text-[11px] text-white/40">
                $ python -m amber.capture_cli capture &lt;url&gt;
              </pre>
            </>
          )}
        </div>
        <button
          onClick={() => setChecked(true)}
          className="shrink-0 rounded-md border border-white/20 bg-white/5 px-4 py-2 text-xs font-semibold text-white/80 transition-colors hover:bg-white/10"
        >
          Check live capability
        </button>
      </div>
    </section>
  );
}
