import { normalizeUrl, type PacketUrl } from "./url";

// Re-export the URL types/helpers from the Node-free module so existing imports
// from "@/lib/packet" keep working. Client components should import the value
// helpers from "@/lib/url" directly.
export type { PacketUrl } from "./url";
export { isUrlMap, urlForCountry, urlList } from "./url";

// Keep `normalizeUrl` referenced so its (pure, Node-free) helper module stays in
// the dependency graph for any future packet-shape work; it is a no-op here.
void normalizeUrl;

/**
 * The Amber web demo is deployed as a self-contained, client-renderable app
 * (Vercel / static). At request time there is no repo filesystem (the signed
 * packet lives outside `web/` and is not bundled) and no Python `verify_packet`
 * to shell out to. So this module no longer reads `samples/live_packet/*` off
 * disk - it serves the REAL packet values bundled at build time in
 * `app/data/packet.ts`, which were read verbatim from the sealed packet.
 *
 * The packet under `samples/` remains the source of truth and is never modified;
 * `app/data/packet.ts` is a faithful, frozen copy of its rendered view-model and
 * of the real verifier's recorded GREEN/RED output.
 */

export interface PerCaptureView {
  captureId: string;
  country: string;
  exitIp: string;
  requestedAt: string;
  priceGross: string;
  priceNet: string;
  currency: string;
  vatRate: string;
  vatSource: string;
  gtin: string | null;
  availability: string | null;
  state: string;
  geoAgreement: string;
  contentLanguage: string | null;
  httpStatus: number | null;
}

export interface BusinessImpactView {
  /** Deterministic €/yr margin-leak figure (signed Layer-1 fact). */
  recoverableMarginEurPerYear: string;
  /** The signed, MEASURED net-of-tax per-unit delta. */
  netDeltaPerUnit: string;
  /** The BUYER-SUPPLIED annual-volume ASSUMPTION (never observed). */
  annualDivertedUnits: number;
  isAssumption: boolean;
  volumeBasis: string;
  dearerCountry: string | null;
  cheaperCountry: string | null;
  currency: string;
}

export interface WithinCountryView {
  country: string;
  agreement: string;
  intraSpread: string;
  nExits: number;
  netMin: string;
  netMax: string;
  netPrices: string[];
}

export interface PacketView {
  /** Where the packet lives (relative to code/ when possible). */
  packetDir: string;
  isFixture: boolean;
  fixtureNote: string | null;
  skuLabel: string;
  /**
   * The product URL exactly as the packet carries it: a single string (fixture)
   * OR a `{ country: url }` map (real per-country capture). Render with
   * `urlForCountry(url, country)` / `urlList(url)` - never directly in JSX.
   */
  url: PacketUrl;
  countries: string[];
  sameSecondBatch: boolean;
  /** All N captures DISPATCHED (launched) within the same second (the honest
   * simultaneity claim - witnessed-same-second is impossible with residential
   * proxies). null when the packet predates dispatch stamping. */
  dispatchedSameSecond: boolean | null;
  dispatchedAtValues: string[];
  requestedAtValues: string[];
  canonicalGtin: string | null;
  gtinConfidence: string | null;
  primaryFinding: string | null;
  grossDelta: string | null;
  netDelta: string | null;
  cheaperCountry: string | null;
  moreExpensiveCountry: string | null;
  cheaperNet: string | null;
  moreExpensiveNet: string | null;
  accessDenial: unknown;
  allIntraCountryAgree: boolean | null;
  perCountryStates: Record<string, string[]>;
  withinCountry: WithinCountryView[];
  perCapture: PerCaptureView[];
  /** The deterministic, signed dollarization (null when there's no delta). */
  businessImpact: BusinessImpactView | null;
}

// The bundled static view-model + the verbatim working-copy facts text. Imported
// lazily-via-static-import so the type definitions above are available to the
// data module without a circular type-only hazard.
import { PACKET_VIEW, FACTS_JSON_PRETTY } from "@/app/data/packet";

/** Return the render view-model for the demo packet (bundled static data). */
export function loadPacketView(): PacketView {
  return PACKET_VIEW;
}

/**
 * Return the facts.json text shown in the tamper-proof editor's working copy.
 * In the self-contained deployment this is the bundled, verbatim packet view
 * text; there is no on-disk working copy to read.
 */
export function readWorkingFacts(): string {
  return FACTS_JSON_PRETTY;
}

/**
 * No-op reset retained for API-route compatibility. The deployed demo holds the
 * working copy in client state, not on disk, so there is nothing to reset
 * server-side; the editor reverts by re-reading the bundled facts text.
 */
export function resetWorkingPacket(): string {
  return PACKET_VIEW.packetDir;
}
