"use client";

import { useEffect, useState } from "react";

interface VerifyResult {
  verdict: "VERIFIED" | "BROKEN";
  exitCode: number;
  checks: { node: string; ok: boolean; detail: string }[];
  brokenNode: string | null;
  rawOutput: string;
  command: string;
  error?: string;
}

type Step = "idle" | "exported" | "tampered" | "reverted";

/**
 * ★ THE TAMPER PROOF (the climax).
 *
 * The operator: exports the packet -> edits a number in facts.json -> runs the
 * REAL verifier (POST /api/verify -> python -m amber.cli) -> sees RED -> reverts
 * -> runs the REAL verifier -> sees GREEN.
 *
 * The RED/GREEN is `result.verdict`, which the server derives ONLY from the
 * python verifier's process EXIT CODE (0 = VERIFIED, non-zero = BROKEN). It is
 * never hardcoded in this component — the verdict, the broken-node name, and the
 * verbatim verifier output all come from the real instrument over the wire.
 */
export function TamperProof({ initialFacts }: { initialFacts: string }) {
  const [facts, setFacts] = useState(initialFacts);
  const [step, setStep] = useState<Step>("idle");
  const [result, setResult] = useState<VerifyResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [busyLabel, setBusyLabel] = useState("");

  // Keep the editor in sync if the source facts change (e.g. a real packet
  // swap-in via AMBER_PACKET_DIR followed by a reload).
  useEffect(() => {
    setFacts(initialFacts);
  }, [initialFacts]);

  async function packetAction(action: string, extra: Record<string, unknown> = {}) {
    const res = await fetch("/api/packet", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ action, ...extra }),
      cache: "no-store",
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error ?? "packet action failed");
    if (typeof data.workingFacts === "string") setFacts(data.workingFacts);
    return data;
  }

  async function verify() {
    const res = await fetch("/api/verify", { method: "POST", cache: "no-store" });
    const data = (await res.json()) as VerifyResult;
    setResult(data);
    return data;
  }

  async function doExport() {
    setBusy(true);
    setBusyLabel("exporting + verifying clean packet…");
    try {
      await packetAction("export");
      await verify();
      setStep("exported");
    } catch (e) {
      alert(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function saveAndVerify() {
    setBusy(true);
    setBusyLabel("writing edited facts.json + running real verify_packet…");
    try {
      await packetAction("writeFacts", { contents: facts });
      await verify();
      setStep("tampered");
    } catch (e) {
      alert(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function doRevert() {
    setBusy(true);
    setBusyLabel("reverting to sealed bytes + re-verifying…");
    try {
      await packetAction("revert");
      await verify();
      setStep("reverted");
    } catch (e) {
      alert(String(e));
    } finally {
      setBusy(false);
    }
  }

  /** Quick one-click demo edit: bump the first net price by a euro. */
  async function quickTamper() {
    setBusy(true);
    setBusyLabel("editing a price in facts.json + running real verify_packet…");
    try {
      // Use a string the operator can see in the editor; tamper enforces it
      // appears exactly once for an unambiguous edit.
      const target = '"net_of_tax_delta":"';
      if (facts.includes(target)) {
        // Replace the net delta value with an obviously-edited number.
        const m = facts.match(/"net_of_tax_delta":"([^"]*)"/);
        if (m) {
          const find = `"net_of_tax_delta":"${m[1]}"`;
          const replace = `"net_of_tax_delta":"99.99"`;
          await packetAction("tamper", { find, replace });
        }
      } else {
        await packetAction("writeFacts", { contents: facts });
      }
      await verify();
      setStep("tampered");
    } catch (e) {
      alert(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="space-y-4">
      <header className="space-y-1">
        <div className="text-xs uppercase tracking-widest text-amber/70">
          ★ The tamper proof (the climax)
        </div>
        <p className="text-xs text-white/50">
          Edit any number in the exported packet → the RED/GREEN below is the REAL{" "}
          <code className="text-amber">verify_packet</code> exit code, not a hardcoded UI state.
        </p>
      </header>

      <VerdictBanner result={result} busy={busy} busyLabel={busyLabel} />

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Editor */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs uppercase tracking-wide text-white/40">
              working copy · facts.json (a Merkle leaf)
            </span>
            <span className="text-[11px] text-white/30">
              edit a price → save → the chain breaks
            </span>
          </div>
          <textarea
            value={facts}
            onChange={(e) => setFacts(e.target.value)}
            spellCheck={false}
            className="h-64 w-full resize-none rounded-md border border-white/15 bg-black/50 p-3 text-[11px] leading-snug text-white/80 outline-none focus:border-amber/50"
          />
          <div className="flex flex-wrap gap-2">
            <button
              onClick={doExport}
              disabled={busy}
              className="rounded bg-amber px-3 py-1.5 text-xs font-bold text-black hover:bg-amber-deep hover:text-white disabled:opacity-50"
            >
              1. Export packet (verify clean)
            </button>
            <button
              onClick={quickTamper}
              disabled={busy || step === "idle"}
              className="rounded border border-broken/60 bg-broken/15 px-3 py-1.5 text-xs font-bold text-broken hover:bg-broken/25 disabled:opacity-40"
            >
              2. Edit a price (quick)
            </button>
            <button
              onClick={saveAndVerify}
              disabled={busy || step === "idle"}
              className="rounded border border-white/25 bg-white/5 px-3 py-1.5 text-xs hover:bg-white/10 disabled:opacity-40"
            >
              Save my edits + verify
            </button>
            <button
              onClick={doRevert}
              disabled={busy || step === "idle"}
              className="rounded border border-verified/60 bg-verified/15 px-3 py-1.5 text-xs font-bold text-verified hover:bg-verified/25 disabled:opacity-40"
            >
              3. Revert (verify GREEN)
            </button>
          </div>
        </div>

        {/* Real verifier output */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs uppercase tracking-wide text-white/40">
              real verifier output (verbatim)
            </span>
            {result && (
              <span className="text-[11px] text-white/30">exit code {result.exitCode}</span>
            )}
          </div>
          {result?.command && (
            <div className="rounded bg-black/60 px-2 py-1 text-[11px] text-amber/70">
              $ {result.command}
            </div>
          )}
          <pre className="h-64 w-full overflow-auto rounded-md border border-white/15 bg-black/60 p-3 text-[11px] leading-snug text-white/70">
            {result ? result.rawOutput : "Run step 1 to verify the exported packet."}
          </pre>
          {result?.checks?.length ? (
            <div className="space-y-0.5">
              {result.checks.map((c, i) => (
                <div key={i} className="flex items-start gap-2 text-[11px]">
                  <span className={c.ok ? "text-verified" : "text-broken"}>
                    {c.ok ? "OK  " : "FAIL"}
                  </span>
                  <span className="text-white/60">
                    <span className="text-white/80">{c.node}</span>: {c.detail}
                  </span>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}

function VerdictBanner({
  result,
  busy,
  busyLabel,
}: {
  result: VerifyResult | null;
  busy: boolean;
  busyLabel: string;
}) {
  if (busy) {
    return (
      <div className="rounded-md border border-white/20 bg-white/5 px-4 py-4 text-center text-sm text-white/60">
        {busyLabel}
      </div>
    );
  }
  if (!result) {
    return (
      <div className="rounded-md border border-white/15 bg-black/30 px-4 py-4 text-center text-sm text-white/40">
        No verdict yet — export the packet to run the real verifier.
      </div>
    );
  }
  if (result.error) {
    return (
      <div className="rounded-md border-2 border-broken bg-broken/15 px-4 py-4 text-center">
        <div className="text-lg font-extrabold text-broken">VERIFIER ERROR</div>
        <div className="mt-1 text-xs text-white/60">{result.error}</div>
      </div>
    );
  }
  const verified = result.verdict === "VERIFIED";
  return (
    <div
      className={`rounded-md border-2 px-4 py-5 text-center ${
        verified
          ? "animate-verified border-verified bg-verified/15"
          : "animate-broken border-broken bg-broken/15"
      }`}
    >
      <div
        className={`text-2xl font-black tracking-wide ${
          verified ? "text-verified" : "text-broken"
        }`}
      >
        {verified ? "✓ VERIFIED" : "✗ CHAIN OF CUSTODY BROKEN"}
      </div>
      <div className="mt-1 text-xs text-white/60">
        {verified
          ? "Every capture hash, the Merkle root, and the ed25519 signature re-check under the trusted signer key."
          : `Broken at: ${result.brokenNode ?? "(unknown)"} — the edit changed a Merkle leaf, so the signed root no longer matches.`}
      </div>
      <div className="mt-2 text-[11px] uppercase tracking-widest text-white/30">
        verdict = real verify_packet exit code ({result.exitCode})
      </div>
    </div>
  );
}
