import {
  copyFileSync,
  cpSync,
  existsSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { join } from "node:path";

import { packetDir, workingPacketDir } from "./paths";

/**
 * A capture body file carries a `_note` marker when it is a constructed demo
 * fixture rather than a real Bright Data capture. We detect it so the UI can
 * label the rendered packet honestly (fixture vs real). Detection is on the
 * actual bytes — never assumed.
 */
function detectFixture(srcDir: string): { isFixture: boolean; note: string | null } {
  const capturesDir = join(srcDir, "captures");
  if (!existsSync(capturesDir)) return { isFixture: false, note: null };
  try {
    const facts = readJson(join(srcDir, "facts.json"));
    // The fixture also tags its sku_label with "(DEMO FIXTURE)".
    const skuLabel: unknown = facts?.sku_label;
    if (typeof skuLabel === "string" && /fixture/i.test(skuLabel)) {
      // Pull the explicit _note from a capture body for the exact wording.
      const note = firstCaptureNote(srcDir);
      return { isFixture: true, note };
    }
  } catch {
    // fall through to body-scan
  }
  const note = firstCaptureNote(srcDir);
  if (note) return { isFixture: true, note };
  return { isFixture: false, note: null };
}

function firstCaptureNote(srcDir: string): string | null {
  const capturesDir = join(srcDir, "captures");
  if (!existsSync(capturesDir)) return null;
  // Read the manifest to find a capture body filename deterministically.
  try {
    const manifest = readJson(join(srcDir, "manifest.json"));
    const first = manifest?.captures?.[0]?.capture_id;
    if (typeof first === "string") {
      const body = readFileSync(join(capturesDir, `${first}.body`), "utf-8");
      const parsed = JSON.parse(body);
      if (typeof parsed?._note === "string") return parsed._note;
    }
  } catch {
    return null;
  }
  return null;
}

function readJson(path: string): any {
  return JSON.parse(readFileSync(path, "utf-8"));
}

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
  url: string;
  countries: string[];
  sameSecondBatch: boolean;
  /** All N captures DISPATCHED (launched) within the same second (the honest
   * simultaneity claim — witnessed-same-second is impossible with residential
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

/** Build the render view-model from a packet's facts.json + manifest.json. */
export function loadPacketView(srcDir: string = packetDir()): PacketView {
  const facts = readJson(join(srcDir, "facts.json"));
  const manifest = readJson(join(srcDir, "manifest.json"));
  const { isFixture, note } = detectFixture(srcDir);

  const manifestByCid = new Map<string, any>();
  for (const c of manifest.captures ?? []) {
    manifestByCid.set(c.capture_id, c);
  }

  const perCapture: PerCaptureView[] = (facts.per_capture ?? []).map((pc: any) => {
    const m = manifestByCid.get(pc.capture_id) ?? {};
    return {
      captureId: pc.capture_id,
      country: pc.requested_country,
      exitIp: pc.exit_ip,
      requestedAt: m.requested_at ?? "",
      priceGross: pc.price_gross,
      priceNet: pc.price_net,
      currency: pc.extracted?.currency ?? "",
      vatRate: pc.vat_rate?.rate ?? "",
      vatSource: pc.vat_rate?.source ?? "",
      gtin: pc.extracted?.gtin ?? null,
      availability: pc.extracted?.availability ?? null,
      state: pc.state?.state ?? "",
      geoAgreement: pc.geo_attribution?.agreement ?? "",
      contentLanguage:
        pc.geo_attribution?.source_2_response_geo_signals?.headers?.["content-language"] ?? null,
      httpStatus: typeof m.http_status === "number" ? m.http_status : null,
    };
  });

  const cmp = facts.cross_country_comparison ?? {};
  const netDelta = cmp.net_delta ?? {};
  const wcc = facts.within_country_control ?? {};
  const bi = facts.business_impact ?? null;

  const withinCountry: WithinCountryView[] = (wcc.per_country ?? []).map((c: any) => ({
    country: c.country,
    agreement: c.agreement,
    intraSpread: c.intra_country_spread,
    nExits: c.n_purchasable_exits,
    netMin: c.net_min,
    netMax: c.net_max,
    netPrices: c.net_prices ?? [],
  }));

  return {
    packetDir: srcDir,
    isFixture,
    fixtureNote: note,
    skuLabel: facts.sku_label ?? "(unlabelled)",
    url: facts.url ?? "",
    countries: facts.countries ?? [],
    sameSecondBatch: Boolean(facts.same_second_batch),
    dispatchedSameSecond:
      typeof facts.dispatched_same_second === "boolean" ? facts.dispatched_same_second : null,
    dispatchedAtValues: facts.dispatched_at_values ?? [],
    requestedAtValues: facts.requested_at_values ?? [],
    canonicalGtin: facts.sku_identity?.canonical_gtin ?? null,
    gtinConfidence: facts.sku_identity?.confidence ?? null,
    primaryFinding: cmp.primary_finding ?? null,
    grossDelta: netDelta.gross_delta ?? null,
    netDelta: netDelta.net_of_tax_delta ?? null,
    cheaperCountry: netDelta.cheaper_country ?? null,
    moreExpensiveCountry: netDelta.more_expensive_country ?? null,
    cheaperNet: netDelta.cheaper_net ?? null,
    moreExpensiveNet: netDelta.more_expensive_net ?? null,
    accessDenial: cmp.access_denial ?? null,
    allIntraCountryAgree:
      typeof wcc.all_intra_country_agree === "boolean" ? wcc.all_intra_country_agree : null,
    perCountryStates: cmp.per_country_states ?? {},
    withinCountry,
    perCapture,
    businessImpact: bi
      ? {
          recoverableMarginEurPerYear: bi.recoverable_margin_eur_per_year,
          netDeltaPerUnit: bi.net_of_tax_delta_per_unit,
          annualDivertedUnits: bi.annual_diverted_units,
          isAssumption: Boolean(bi.annual_diverted_units_is_assumption),
          volumeBasis: bi.volume_basis ?? "buyer-supplied volume assumption",
          dearerCountry: bi.dearer_country ?? null,
          cheaperCountry: bi.cheaper_country ?? null,
          currency: bi.currency ?? "EUR",
        }
      : null,
  };
}

/**
 * Reset the editable working copy of the packet from the committed source.
 *
 * The committed packet under `samples/` is NEVER mutated. The tamper-proof
 * operates on this private working copy: edit a number -> verify (RED) ->
 * revert (= reset) -> verify (GREEN). Returns the working dir path.
 */
export function resetWorkingPacket(srcDir: string = packetDir()): string {
  const work = workingPacketDir();
  if (existsSync(work)) rmSync(work, { recursive: true, force: true });
  mkdirSync(work, { recursive: true });
  cpSync(srcDir, work, { recursive: true });
  return work;
}

/** Read the raw facts.json text from the working copy (for the editor). */
export function readWorkingFacts(): string {
  const work = workingPacketDir();
  ensureWorking();
  return readFileSync(join(work, "facts.json"), "utf-8");
}

/** Overwrite the working copy's facts.json with operator-edited bytes. */
export function writeWorkingFacts(contents: string): void {
  const work = workingPacketDir();
  ensureWorking();
  writeFileSync(join(work, "facts.json"), contents, "utf-8");
}

/**
 * Apply a single-number edit to facts.json by string replacement on the raw
 * bytes (the operator's "edit a price" gesture). `find` must occur exactly
 * once; otherwise we refuse rather than silently editing the wrong field.
 */
export function tamperFacts(find: string, replace: string): void {
  const work = workingPacketDir();
  ensureWorking();
  const path = join(work, "facts.json");
  const current = readFileSync(path, "utf-8");
  const count = current.split(find).length - 1;
  if (count !== 1) {
    throw new Error(
      `refusing to edit: the string ${JSON.stringify(find)} occurs ${count} time(s) ` +
        `in facts.json (need exactly 1 for an unambiguous edit).`,
    );
  }
  writeFileSync(path, current.replace(find, replace), "utf-8");
}

function ensureWorking(): void {
  const work = workingPacketDir();
  if (!existsSync(join(work, "facts.json"))) {
    resetWorkingPacket();
  }
}

/** Copy a single packet control file (used in tests/diagnostics). */
export function copyControlFile(name: string, from: string, to: string): void {
  copyFileSync(join(from, name), join(to, name));
}
