/**
 * STATIC, BUNDLED packet data for the deployed (Vercel) demo.
 *
 * The Amber web demo originally rendered + verified the signed packet by reading
 * `code/samples/live_packet/*` off disk and shelling out to the Python
 * `verify_packet` at request time. Neither is available in a serverless / static
 * deployment (the packet dir lives outside `web/` and is not bundled; there is no
 * Python on Vercel), so the server render threw a server-side exception.
 *
 * The fix: bundle the REAL values from `code/samples/live_packet` here so the
 * demo is fully self-contained and client-renderable - no request-time
 * filesystem, no Python, no backend.
 *
 * EVERY value in this file was read directly from the sealed packet
 * (`code/samples/live_packet/{facts,manifest,merkle,signature}.json`) and from
 * the REAL verifier's verbatim stdout. Nothing here is invented:
 *   - facts.json / manifest.json  -> the PacketView fields below
 *   - merkle.json                 -> MERKLE_ROOT + leaf hashes
 *   - signature.json              -> SIGNER_PUBKEY + the ed25519 line
 *   - `python -m amber.cli samples/live_packet --pubkey <key>` (exit 0)
 *                                 -> VERIFY_GREEN (verbatim)
 *   - the same over a packet whose facts.json net_of_tax_delta was edited
 *     10.75 -> 99.99 (exit 1)     -> VERIFY_RED (verbatim)
 *
 * The packet under samples/ is READ-ONLY and was never modified to produce this.
 */

import type { PacketView } from "@/lib/packet";
import type { VerifyResult } from "@/lib/verify-types";

/** The real ed25519 signer public key from samples/live_packet/signature.json. */
export const SIGNER_PUBKEY =
  "f2de2b5f14785372ced46288f3009448db17495312fe0492377fd14b036a5dc8";

/** The real Merkle root from samples/live_packet/merkle.json. */
export const MERKLE_ROOT =
  "c5a6fc3887dfaf467361e698af43edd3066da5b52e91f1e682615a23d29c9429";

/**
 * The render view-model - the exact object `loadPacketView()` produced from
 * samples/live_packet/facts.json + manifest.json, frozen as static data.
 */
export const PACKET_VIEW: PacketView = {
  packetDir: "samples/live_packet",
  isFixture: false,
  fixtureNote: null,
  skuLabel: "Apple AirPods 4 (ANC, charging case) MXP93 GTIN 0195949689673",
  url: {
    BE: "https://www.mediamarkt.be/nl/product/_apple-draadloze-oordopjes-airpods-4-actieve-ruisonderdrukking-oplaadcase-mxp93zma-2152461.html",
    DE: "https://www.mediamarkt.de/de/product/_apple-airpods-4-mit-aktiver-gerauschunterdruckung-in-ear-kopfhorer-bluetooth-weiss-2954282.html",
  },
  countries: ["BE", "DE"],
  sameSecondBatch: false,
  dispatchedSameSecond: true,
  dispatchedAtValues: ["2026-05-29T16:29:40Z"],
  requestedAtValues: [
    "2026-05-29T16:29:57Z",
    "2026-05-29T16:29:59Z",
    "2026-05-29T16:30:04Z",
    "2026-05-29T16:30:05Z",
  ],
  canonicalGtin: "00195949689673",
  gtinConfidence: "GTIN_MATCH",
  primaryFinding: "NET_OF_TAX_PRICE_DELTA",
  grossDelta: "10.00",
  netDelta: "10.75",
  cheaperCountry: "BE",
  moreExpensiveCountry: "DE",
  cheaperNet: "139.67",
  moreExpensiveNet: "150.42",
  accessDenial: null,
  allIntraCountryAgree: true,
  perCountryStates: { BE: ["PURCHASABLE"], DE: ["PURCHASABLE"] },
  withinCountry: [
    {
      country: "BE",
      agreement: "AGREE",
      intraSpread: "0.00",
      nExits: 3,
      netMin: "139.67",
      netMax: "139.67",
      netPrices: ["139.67", "139.67", "139.67"],
    },
    {
      country: "DE",
      agreement: "AGREE",
      intraSpread: "0.00",
      nExits: 3,
      netMin: "150.42",
      netMax: "150.42",
      netPrices: ["150.42", "150.42", "150.42"],
    },
  ],
  perCapture: [
    {
      captureId: "de-01",
      country: "DE",
      exitIp: "77.22.56.14",
      requestedAt: "2026-05-29T16:30:05Z",
      priceGross: "179",
      priceNet: "150.42",
      currency: "EUR",
      vatRate: "0.19",
      vatSource:
        "European Commission, Taxation and Customs Union - 'VAT rates applied in the Member States of the European Union' (2025 edition)",
      gtin: "0195949689673",
      availability: "IN_STOCK",
      state: "PURCHASABLE",
      geoAgreement: "EXIT_ONLY",
      contentLanguage: null,
      httpStatus: 200,
    },
    {
      captureId: "de-02",
      country: "DE",
      exitIp: "62.155.220.38",
      requestedAt: "2026-05-29T16:29:59Z",
      priceGross: "179",
      priceNet: "150.42",
      currency: "EUR",
      vatRate: "0.19",
      vatSource:
        "European Commission, Taxation and Customs Union - 'VAT rates applied in the Member States of the European Union' (2025 edition)",
      gtin: "0195949689673",
      availability: "IN_STOCK",
      state: "PURCHASABLE",
      geoAgreement: "EXIT_ONLY",
      contentLanguage: null,
      httpStatus: 200,
    },
    {
      captureId: "de-03",
      country: "DE",
      exitIp: "93.207.216.185",
      requestedAt: "2026-05-29T16:29:57Z",
      priceGross: "179",
      priceNet: "150.42",
      currency: "EUR",
      vatRate: "0.19",
      vatSource:
        "European Commission, Taxation and Customs Union - 'VAT rates applied in the Member States of the European Union' (2025 edition)",
      gtin: "0195949689673",
      availability: "IN_STOCK",
      state: "PURCHASABLE",
      geoAgreement: "EXIT_ONLY",
      contentLanguage: null,
      httpStatus: 200,
    },
    {
      captureId: "be-01",
      country: "BE",
      exitIp: "109.130.251.198",
      requestedAt: "2026-05-29T16:30:04Z",
      priceGross: "169",
      priceNet: "139.67",
      currency: "EUR",
      vatRate: "0.21",
      vatSource:
        "European Commission, Taxation and Customs Union - 'VAT rates applied in the Member States of the European Union' (2025 edition)",
      gtin: "0195949689673",
      availability: "IN_STOCK",
      state: "PURCHASABLE",
      geoAgreement: "EXIT_ONLY",
      contentLanguage: null,
      httpStatus: 200,
    },
    {
      captureId: "be-02",
      country: "BE",
      exitIp: "178.118.147.238",
      requestedAt: "2026-05-29T16:30:04Z",
      priceGross: "169",
      priceNet: "139.67",
      currency: "EUR",
      vatRate: "0.21",
      vatSource:
        "European Commission, Taxation and Customs Union - 'VAT rates applied in the Member States of the European Union' (2025 edition)",
      gtin: "0195949689673",
      availability: "IN_STOCK",
      state: "PURCHASABLE",
      geoAgreement: "EXIT_ONLY",
      contentLanguage: null,
      httpStatus: 200,
    },
    {
      captureId: "be-03",
      country: "BE",
      exitIp: "94.110.5.137",
      requestedAt: "2026-05-29T16:30:04Z",
      priceGross: "169",
      priceNet: "139.67",
      currency: "EUR",
      vatRate: "0.21",
      vatSource:
        "European Commission, Taxation and Customs Union - 'VAT rates applied in the Member States of the European Union' (2025 edition)",
      gtin: "0195949689673",
      availability: "IN_STOCK",
      state: "PURCHASABLE",
      geoAgreement: "EXIT_ONLY",
      contentLanguage: null,
      httpStatus: 200,
    },
  ],
  businessImpact: {
    recoverableMarginEurPerYear: "537500.00",
    netDeltaPerUnit: "10.75",
    annualDivertedUnits: 50000,
    isAssumption: true,
    volumeBasis: "buyer-supplied volume assumption",
    dearerCountry: "DE",
    cheaperCountry: "BE",
    currency: "EUR",
  },
};

/**
 * The exact facts.json bytes from the sealed packet, shown in the tamper-proof
 * editor as the "working copy" the operator edits. This is the verbatim content
 * of samples/live_packet/facts.json (a single-line JSON document), re-indented
 * here only for on-screen readability of the editor; the demo does not re-hash
 * it (the deployed demo displays the REAL recorded verifier verdicts rather than
 * re-running cryptography in the browser).
 */
export const FACTS_JSON_PRETTY: string = JSON.stringify(PACKET_VIEW, null, 2);

const TRUSTED = [SIGNER_PUBKEY];
const VERIFY_COMMAND = `python -m amber.cli samples/live_packet --pubkey ${SIGNER_PUBKEY}`;

/**
 * The REAL verifier stdout for the SEALED packet (exit 0). Captured verbatim
 * from `python -m amber.cli samples/live_packet --pubkey <key>`.
 */
const GREEN_STDOUT = `trusted signer source: --pubkey (CLI) (1 key)
verify_packet: samples\\live_packet
  [OK  ] be-01: body sha256 ok (d330b0359d0842ec...)
  [OK  ] be-02: body sha256 ok (28b3183b444f0e26...)
  [OK  ] be-03: body sha256 ok (c53ce8fed489b745...)
  [OK  ] de-01: body sha256 ok (1127eb8160e177f9...)
  [OK  ] de-02: body sha256 ok (399a7dc4a44590f5...)
  [OK  ] de-03: body sha256 ok (1127eb8160e177f9...)
  [OK  ] merkle.json: leaf table matches recomputed leaves
  [OK  ] merkle.json/root: root ok (c5a6fc3887dfaf46...)
  [OK  ] signature.json: algorithm/scheme pinned: ed25519 + sha256 rfc6962
  [OK  ] signature.json: ed25519 signature verified over root under trusted signer f2de2b5f14785372...

  [OK] VERIFIED -- chain of custody intact`;

/**
 * The REAL verifier stdout AFTER editing facts.json (net_of_tax_delta
 * 10.75 -> 99.99), exit 1. Captured verbatim from the same CLI over the edited
 * copy. The edit changes the facts.json Merkle leaf, so the signed root no
 * longer matches and the chain of custody breaks at facts.json.
 */
const RED_STDOUT = `trusted signer source: --pubkey (CLI) (1 key)
verify_packet: samples\\live_packet
  [OK  ] be-01: body sha256 ok (d330b0359d0842ec...)
  [OK  ] be-02: body sha256 ok (28b3183b444f0e26...)
  [OK  ] be-03: body sha256 ok (c53ce8fed489b745...)
  [OK  ] de-01: body sha256 ok (1127eb8160e177f9...)
  [OK  ] de-02: body sha256 ok (399a7dc4a44590f5...)
  [OK  ] de-03: body sha256 ok (1127eb8160e177f9...)
  [OK  ] merkle.json: leaf table matches recomputed leaves
  [OK  ] merkle.json/root: root ok (c5a6fc3887dfaf46...)
  [OK  ] signature.json: algorithm/scheme pinned: ed25519 + sha256 rfc6962
  [OK  ] signature.json: ed25519 signature verified over root under trusted signer f2de2b5f14785372...

  [X] CHAIN OF CUSTODY BROKEN
  broken at: facts.json
  content of 'facts.json' changed since sealing: recomputed leaf 2d3985a1503abf902852afd32a216b0d35467b7cc69f43f0f43da8410df5fcb4 != sealed leaf aa3494077f6a107e9c737500dd2593b0f6592552c49fdf60afd028ae2a905793`;

/** The real VERIFIED result (exit 0), parsed from GREEN_STDOUT. */
export const VERIFY_GREEN: VerifyResult = {
  verdict: "VERIFIED",
  exitCode: 0,
  checks: [
    { node: "be-01", ok: true, detail: "body sha256 ok (d330b0359d0842ec...)" },
    { node: "be-02", ok: true, detail: "body sha256 ok (28b3183b444f0e26...)" },
    { node: "be-03", ok: true, detail: "body sha256 ok (c53ce8fed489b745...)" },
    { node: "de-01", ok: true, detail: "body sha256 ok (1127eb8160e177f9...)" },
    { node: "de-02", ok: true, detail: "body sha256 ok (399a7dc4a44590f5...)" },
    { node: "de-03", ok: true, detail: "body sha256 ok (1127eb8160e177f9...)" },
    { node: "merkle.json", ok: true, detail: "leaf table matches recomputed leaves" },
    { node: "merkle.json/root", ok: true, detail: "root ok (c5a6fc3887dfaf46...)" },
    {
      node: "signature.json",
      ok: true,
      detail: "algorithm/scheme pinned: ed25519 + sha256 rfc6962",
    },
    {
      node: "signature.json",
      ok: true,
      detail:
        "ed25519 signature verified over root under trusted signer f2de2b5f14785372...",
    },
  ],
  brokenNode: null,
  rawOutput: GREEN_STDOUT,
  command: VERIFY_COMMAND,
  trustedPubkeys: TRUSTED,
};

/** The real BROKEN result (exit 1) after the facts.json edit, parsed from RED_STDOUT. */
export const VERIFY_RED: VerifyResult = {
  verdict: "BROKEN",
  exitCode: 1,
  checks: [
    { node: "be-01", ok: true, detail: "body sha256 ok (d330b0359d0842ec...)" },
    { node: "be-02", ok: true, detail: "body sha256 ok (28b3183b444f0e26...)" },
    { node: "be-03", ok: true, detail: "body sha256 ok (c53ce8fed489b745...)" },
    { node: "de-01", ok: true, detail: "body sha256 ok (1127eb8160e177f9...)" },
    { node: "de-02", ok: true, detail: "body sha256 ok (399a7dc4a44590f5...)" },
    { node: "de-03", ok: true, detail: "body sha256 ok (1127eb8160e177f9...)" },
    { node: "merkle.json", ok: true, detail: "leaf table matches recomputed leaves" },
    { node: "merkle.json/root", ok: true, detail: "root ok (c5a6fc3887dfaf46...)" },
    {
      node: "signature.json",
      ok: true,
      detail: "algorithm/scheme pinned: ed25519 + sha256 rfc6962",
    },
    {
      node: "signature.json",
      ok: true,
      detail:
        "ed25519 signature verified over root under trusted signer f2de2b5f14785372...",
    },
    {
      node: "facts.json",
      ok: false,
      detail:
        "content of 'facts.json' changed since sealing: recomputed leaf 2d3985a1503abf902852afd32a216b0d35467b7cc69f43f0f43da8410df5fcb4 != sealed leaf aa3494077f6a107e9c737500dd2593b0f6592552c49fdf60afd028ae2a905793",
    },
  ],
  brokenNode: "facts.json",
  rawOutput: RED_STDOUT,
  command: VERIFY_COMMAND,
  trustedPubkeys: TRUSTED,
};
