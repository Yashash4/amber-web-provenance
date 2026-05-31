/**
 * Node-free types for the verifier result.
 *
 * These live apart from `lib/verify.ts` (which imports `node:child_process` to
 * spawn the real Python verifier) so client components and the static bundled
 * packet data can import the SHAPE without dragging the Node-only spawner into
 * the browser bundle.
 */

/**
 * The result of running the REAL `verify_packet` over a packet directory.
 *
 * `verdict` is "VERIFIED" iff the python verifier exited 0, "BROKEN" iff it
 * exited non-zero. It is NEVER computed in TypeScript - it is a pure function
 * of the verifier's process exit code.
 */
export interface VerifyResult {
  verdict: "VERIFIED" | "BROKEN";
  exitCode: number;
  /** The verifier's per-node audit lines, parsed from its real stdout. */
  checks: { node: string; ok: boolean; detail: string }[];
  /** The node where the chain of custody broke (null when VERIFIED). */
  brokenNode: string | null;
  /** Full raw stdout/stderr from the real verifier - shown verbatim in the UI. */
  rawOutput: string;
  /** The exact argv that was spawned - surfaced so it is auditable it is real. */
  command: string;
  /**
   * The trusted signer public key(s) the signature was PINNED to, supplied
   * out-of-band via `--pubkey` (NOT read from inside the packet).
   */
  trustedPubkeys: string[];
}
