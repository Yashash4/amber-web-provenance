import { MERKLE_ROOT, SIGNER_PUBKEY } from "@/app/data/packet";

const REPO_URL = "https://github.com/Yashash4/amber-web-provenance";
const PR_URL = "https://github.com/Yashash4/amber-web-provenance/pull/141";

/** Truncate a long hex digest to a head + ellipsis for the chips. */
function shortHex(hex: string, head = 16): string {
  return hex.length > head ? `${hex.slice(0, head)}...` : hex;
}

/**
 * SIGNED PROVENANCE footer: the cryptographic scheme, the Merkle root, the
 * signer public key, the offline-verify guarantee, and the repo + PR links.
 */
export function ProvenanceFooter() {
  return (
    <footer className="panel-card mt-2 p-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <span
              className="h-3 w-3 rounded-full bg-amber"
              style={{ boxShadow: "0 0 12px 1px rgba(245,158,11,0.7)" }}
              aria-hidden
            />
            <span className="text-sm font-bold tracking-wide text-white/90">
              Signed provenance
            </span>
          </div>

          <dl className="grid grid-cols-1 gap-x-8 gap-y-2 sm:grid-cols-2">
            <Field label="scheme" value="ed25519 + sha256 RFC 6962 Merkle" />
            <Field label="merkle root" value={shortHex(MERKLE_ROOT)} mono />
            <Field label="signer" value={shortHex(SIGNER_PUBKEY)} mono />
            <Field label="verification" value="verify offline, no Amber server" />
          </dl>
        </div>

        <div className="flex shrink-0 flex-wrap gap-2">
          <a
            href={REPO_URL}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 rounded-md border border-white/15 bg-white/5 px-3 py-1.5 text-xs font-semibold text-white/80 transition-colors hover:border-amber/40 hover:text-amber"
          >
            Yashash4/amber-web-provenance
          </a>
          <a
            href={PR_URL}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 rounded-md border border-advisory/40 bg-advisory/10 px-3 py-1.5 text-xs font-semibold text-advisory transition-colors hover:bg-advisory/20"
          >
            PR #141
          </a>
        </div>
      </div>

      <div className="mt-4 border-t border-white/8 pt-3 text-[11px] text-white/35">
        Offline golden run. The RED/GREEN verdict is the real{" "}
        <code className="text-white/55">python -m amber.cli</code> exit code. Re-verify any packet
        directory yourself; nothing here trusts an Amber server.
      </div>
    </footer>
  );
}

function Field({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-baseline gap-2">
      <dt className="w-24 shrink-0 text-[10px] uppercase tracking-wide text-white/40">{label}</dt>
      <dd className={`text-[12px] text-white/75 ${mono ? "break-all font-mono text-amber/80" : ""}`}>
        {value}
      </dd>
    </div>
  );
}
