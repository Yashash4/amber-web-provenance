"use client";

import { useState } from "react";

interface LiveState {
  ready: boolean;
  mode: string | null;
  message: string;
  command: string;
  rawOutput?: string;
  error?: string;
}

/**
 * The ONE live-capture cell. It probes Component 2's REAL credential state and
 * honestly reports "pending Bright Data credentials" until they exist — it never
 * fabricates a live result. It arms automatically once creds are present.
 */
export function LiveCell() {
  const [state, setState] = useState<LiveState | null>(null);
  const [loading, setLoading] = useState(false);
  const [checked, setChecked] = useState(false);

  async function probe() {
    setLoading(true);
    try {
      const res = await fetch("/api/live", { cache: "no-store" });
      setState(await res.json());
    } catch (err) {
      setState({
        ready: false,
        mode: null,
        message: "could not reach the live-capture probe",
        command: "",
        error: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setLoading(false);
      setChecked(true);
    }
  }

  const ready = state?.ready ?? false;

  return (
    <section className="space-y-3">
      <header className="flex items-center justify-between">
        <div>
          <div className="text-xs uppercase tracking-widest text-amber/70">
            Live capture cell (the ONE live cell)
          </div>
          <p className="text-xs text-white/50">
            Everything above is the committed OFFLINE golden run. This single cell is the only
            live element — and it never fakes a result.
          </p>
        </div>
        <button
          onClick={probe}
          disabled={loading}
          className="rounded border border-white/20 bg-white/5 px-3 py-1.5 text-xs hover:bg-white/10 disabled:opacity-50"
        >
          {loading ? "probing…" : "Probe live capability"}
        </button>
      </header>

      <div
        className={`rounded-md border px-4 py-3 ${
          !checked
            ? "border-white/15 bg-black/30"
            : ready
              ? "border-verified/40 bg-verified/10"
              : "border-amber/50 bg-amber/10"
        }`}
      >
        {!checked ? (
          <div className="text-sm text-white/50">
            Not probed yet. Click “Probe live capability” to ask Component 2 (the REAL{" "}
            <code className="text-amber">amber-capture creds</code> command) whether Bright Data
            credentials are present.
          </div>
        ) : (
          <>
            <div className="flex items-center gap-2">
              <span
                className={`h-2.5 w-2.5 rounded-full ${
                  ready ? "bg-verified" : "bg-amber"
                }`}
              />
              <span
                className={`text-sm font-bold ${ready ? "text-verified" : "text-amber"}`}
              >
                {ready
                  ? `LIVE CAPTURE ARMED (mode: ${state?.mode})`
                  : "LIVE CAPTURE — PENDING BRIGHT DATA CREDENTIALS"}
              </span>
            </div>
            <p className="mt-2 text-xs text-white/60">{state?.message}</p>
            {state?.error && (
              <p className="mt-2 text-xs text-broken">probe error: {state.error}</p>
            )}
            {state?.command && (
              <pre className="mt-2 overflow-x-auto rounded bg-black/50 px-2 py-1 text-[11px] text-white/40">
                $ {state.command}
                {state.rawOutput ? `\n${state.rawOutput}` : ""}
              </pre>
            )}
          </>
        )}
      </div>
    </section>
  );
}
