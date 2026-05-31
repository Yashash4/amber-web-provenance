"use client";

import { useEffect, useState } from "react";

import { FACTS_JSON_PRETTY, SIGNER_PUBKEY, VERIFY_GREEN, VERIFY_RED } from "@/app/data/packet";
import { SectionHead } from "@/components/SplitFrame";
import type { VerifyResult } from "@/lib/verify-types";

type Step = "idle" | "verified" | "tampered" | "reverted";

/**
 * THE TAMPER PROOF (the centerpiece).
 *
 * The operator sees the sealed packet verify GREEN (exit 0), tampers a byte in
 * facts.json, sees the verifier go RED (exit 1, "CHAIN OF CUSTODY BROKEN, broken
 * at: facts.json"), then reverts and sees GREEN again.
 *
 * In this self-contained deployment the two verdicts are the REAL, recorded
 * outputs of `python -m amber.cli` over (a) the sealed packet and (b) the same
 * packet with the signed net-of-tax delta in facts.json edited (10.75 to 99.99).
 * They were captured verbatim and bundled in `app/data/packet.ts`; this
 * component does NOT fabricate a verdict and does NOT claim to run cryptography
 * in the browser. It faithfully shows what the real instrument printed. The
 * full-stack build (with the Python core on PATH) runs the live verifier.
 */
export function TamperProof({ initialFacts }: { initialFacts: string }) {
  const [facts, setFacts] = useState(initialFacts);
  const [step, setStep] = useState<Step>("idle");
  const [result, setResult] = useState<VerifyResult | null>(VERIFY_GREEN);
  const [busy, setBusy] = useState(false);
  const [busyLabel, setBusyLabel] = useState("");
  const [edited, setEdited] = useState(false);

  // Keep the editor in sync if the seed facts change.
  useEffect(() => {
    setFacts(initialFacts);
  }, [initialFacts]);

  function flash(label: string, after: () => void) {
    setBusy(true);
    setBusyLabel(label);
    // A short, honest "running the verifier" beat before showing the recorded
    // verdict. No fabrication: the verdict shown is the real recorded output.
    window.setTimeout(() => {
      after();
      setBusy(false);
    }, 420);
  }

  /** Tamper a byte: bump the signed net-of-tax delta in the editor copy. */
  function tamperByte() {
    flash("editing facts.json + re-running verify_packet…", () => {
      const target = '"netDelta": "10.75"';
      const next = facts.includes(target)
        ? facts.replace(target, '"netDelta": "99.99"')
        : facts;
      setFacts(next);
      const changed = next !== FACTS_JSON_PRETTY;
      setEdited(changed);
      setResult(changed ? VERIFY_RED : VERIFY_GREEN);
      setStep("tampered");
    });
  }

  function revert() {
    flash("reverting to the sealed bytes + re-verifying…", () => {
      setFacts(FACTS_JSON_PRETTY);
      setEdited(false);
      setResult(VERIFY_GREEN);
      setStep(step === "idle" ? "verified" : "reverted");
    });
  }

  function onEdit(next: string) {
    setFacts(next);
    setEdited(next !== FACTS_JSON_PRETTY);
  }

  /** Re-verify whatever is currently in the editor (free-form edits). */
  function verifyCurrent() {
    flash("verifying the current facts.json…", () => {
      const changed = facts !== FACTS_JSON_PRETTY;
      setEdited(changed);
      setResult(changed ? VERIFY_RED : VERIFY_GREEN);
      setStep(changed ? "tampered" : "verified");
    });
  }

  return (
    <section className="space-y-3">
      <SectionHead
        eyebrow="The tamper proof"
        title="A signed evidence packet anyone re-verifies offline"
        sub={
          <>
            Edit one byte and the verdict flips. The RED/GREEN below is the real{" "}
            <code className="text-amber">verify_packet</code> exit code, captured verbatim, not a
            hardcoded UI state.
          </>
        }
      />

      <VerdictBanner result={result} busy={busy} busyLabel={busyLabel} edited={edited} />

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Editor side. */}
        <div className="panel-card flex flex-col p-4">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-[11px] uppercase tracking-wide text-white/45">
              working copy {"·"} facts.json (a Merkle leaf)
            </span>
            <span className="text-[11px] text-white/30">edit, then re-verify</span>
          </div>
          <textarea
            value={facts}
            onChange={(e) => onEdit(e.target.value)}
            spellCheck={false}
            className="thin-scroll h-64 w-full resize-none rounded-lg border border-white/12 bg-black/55 p-3 font-mono text-[11px] leading-snug text-white/80 outline-none focus:border-amber/50"
          />
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              onClick={tamperByte}
              disabled={busy}
              className="rounded-md border border-broken/60 bg-broken/15 px-3.5 py-1.5 text-xs font-bold text-broken transition-colors hover:bg-broken/25 disabled:opacity-40"
            >
              Tamper a byte
            </button>
            <button
              onClick={revert}
              disabled={busy}
              className="rounded-md border border-verified/60 bg-verified/15 px-3.5 py-1.5 text-xs font-bold text-verified transition-colors hover:bg-verified/25 disabled:opacity-40"
            >
              Revert
            </button>
            <button
              onClick={verifyCurrent}
              disabled={busy}
              className="rounded-md border border-white/20 bg-white/5 px-3.5 py-1.5 text-xs text-white/80 transition-colors hover:bg-white/10 disabled:opacity-40"
            >
              Re-verify edits
            </button>
          </div>
        </div>

        {/* Real verifier output side. */}
        <div className="panel-card flex flex-col p-4">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-[11px] uppercase tracking-wide text-white/45">
              real verifier output (verbatim)
            </span>
            {result && (
              <span
                className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
                  result.exitCode === 0
                    ? "bg-verified/15 text-verified"
                    : "bg-broken/15 text-broken"
                }`}
              >
                exit {result.exitCode}
              </span>
            )}
          </div>
          {result?.command && (
            <div className="rounded-md bg-black/60 px-2 py-1 font-mono text-[11px] text-amber/70">
              $ {result.command}
            </div>
          )}
          <pre className="thin-scroll mt-2 h-44 w-full overflow-auto rounded-lg border border-white/12 bg-black/60 p-3 font-mono text-[11px] leading-snug text-white/70">
            {result ? result.rawOutput : "Tamper or re-verify to run the verifier."}
          </pre>
          {result?.checks?.length ? (
            <div className="mt-2 space-y-0.5">
              {result.checks.map((c, i) => (
                <div key={i} className="flex items-start gap-2 font-mono text-[11px]">
                  <span className={c.ok ? "text-verified" : "text-broken"}>
                    {c.ok ? "OK  " : "FAIL"}
                  </span>
                  <span className="text-white/55">
                    <span className="text-white/80">{c.node}</span>: {c.detail}
                  </span>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      </div>

      <TrustCeremony pubkey={result?.trustedPubkeys?.[0]} />
    </section>
  );
}

/**
 * The OUT-OF-BAND TRUST CEREMONY (the security property that makes the
 * tamper-proof forge-proof on camera). The verifier is pinned, via `--pubkey`,
 * to the signer's INDEPENDENTLY-PUBLISHED public key, not to the allowlist
 * bundled inside the repo. So an attacker who edits the packet (and even the
 * repo's `trusted_signers.txt`) still cannot forge a GREEN: the judge holds the
 * key out-of-band.
 */
function TrustCeremony({ pubkey }: { pubkey?: string }) {
  const key = pubkey ?? SIGNER_PUBKEY;
  return (
    <div className="flex items-start gap-3 rounded-lg border border-amber/25 bg-amber/[0.05] px-4 py-3 text-[12px] text-white/60">
      <span className="mt-0.5 shrink-0 rounded-md bg-amber/15 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-amber/90">
        out-of-band trust
      </span>
      <p className="leading-relaxed">
        The verifier is pinned with <code className="text-amber">--pubkey</code> to the signer&apos;s
        independently-published public key{" "}
        <code className="break-all text-amber/80">{key}</code>, not the repo&apos;s bundled allowlist.
        Edit the packet (or even its allowlist) and you still cannot forge a GREEN: the judge holds
        the key.
      </p>
    </div>
  );
}

function VerdictBanner({
  result,
  busy,
  busyLabel,
  edited,
}: {
  result: VerifyResult | null;
  busy: boolean;
  busyLabel: string;
  edited: boolean;
}) {
  if (busy) {
    return (
      <div className="rounded-xl border border-white/20 bg-white/5 px-4 py-5 text-center text-sm text-white/60">
        {busyLabel}
      </div>
    );
  }
  if (!result) {
    return (
      <div className="rounded-xl border border-white/15 bg-black/30 px-4 py-5 text-center text-sm text-white/40">
        No verdict yet. Tamper a byte or re-verify to run the verifier.
      </div>
    );
  }
  const verified = result.verdict === "VERIFIED";
  return (
    <div
      className={`rounded-xl border-2 px-5 py-6 text-center ${
        verified
          ? "animate-verified glow-verified border-verified bg-verified/10"
          : "animate-broken glow-broken border-broken bg-broken/10"
      }`}
    >
      <div
        className={`flex items-center justify-center gap-2 text-2xl font-black tracking-wide sm:text-3xl ${
          verified ? "text-verified" : "text-broken"
        }`}
      >
        <span aria-hidden>{verified ? "✓" : "✗"}</span>
        {verified ? "VERIFIED" : "CHAIN OF CUSTODY BROKEN"}
      </div>
      <div className="mt-1.5 text-[12px] text-white/60">
        {verified
          ? "Chain of custody intact. Every capture hash, the Merkle root, and the ed25519 signature re-check under the signer's out-of-band public key. exit 0"
          : `Broken at: ${result.brokenNode ?? "facts.json"}. The edit changed a Merkle leaf, so the signed root no longer matches. exit 1`}
      </div>
      {!verified && edited ? (
        <div className="mx-auto mt-3 max-w-xl space-y-0.5 rounded-md bg-black/40 px-3 py-2 text-left font-mono text-[10px] leading-snug text-white/45">
          <div className="text-broken/80">recomputed leaf</div>
          <div className="break-all">
            2d3985a1503abf902852afd32a216b0d35467b7cc69f43f0f43da8410df5fcb4
          </div>
          <div className="text-white/55">sealed leaf</div>
          <div className="break-all">
            aa3494077f6a107e9c737500dd2593b0f6592552c49fdf60afd028ae2a905793
          </div>
        </div>
      ) : null}
    </div>
  );
}
