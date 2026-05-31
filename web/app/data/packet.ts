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
 * The verbatim sealed facts.json bytes from samples/live_packet/facts.json (a
 * single-line JSON document). This is the EXACT document that hashed to the
 * sealed Merkle leaf
 * aa3494077f6a107e9c737500dd2593b0f6592552c49fdf60afd028ae2a905793 - the leaf
 * the tamper-proof editor lets the operator break. The ONLY transcription is the
 * EC VAT-source citation's em-dash (U+2014), rendered here as an ASCII hyphen for
 * display consistency (matching how PACKET_VIEW.vatSource already transcribes
 * that same citation); every other character is byte-for-byte the sealed
 * content, so `JSON.parse(RAW_FACTS_JSON)` round-trips the real record.
 */
const RAW_FACTS_JSON = "{\"business_impact\":{\"annual_diverted_units\":50000,\"annual_diverted_units_is_assumption\":true,\"cheaper_country\":\"BE\",\"computation\":\"net_of_tax_delta_per_unit * annual_diverted_units\",\"currency\":\"EUR\",\"dearer_country\":\"DE\",\"disclaimer\":\"annual_diverted_units is a BUYER-SUPPLIED ASSUMPTION, not an Amber measurement; the recoverable-margin figure is the signed net-of-tax per-unit delta multiplied by that assumed volume. Amber measures and signs the per-unit delta; the volume is the operator's input.\",\"metric\":\"recoverable_margin_per_year\",\"net_of_tax_delta_per_unit\":\"10.75\",\"recoverable_margin_eur_per_year\":\"537500.00\",\"schema\":\"amber/business_impact@1\",\"volume_basis\":\"buyer-supplied volume assumption\"},\"capture_count\":6,\"category\":\"standard\",\"countries\":[\"BE\",\"DE\"],\"cross_country_comparison\":{\"access_denial\":null,\"net_delta\":{\"cheaper_country\":\"BE\",\"cheaper_net\":\"139.67\",\"delta_is_nonzero\":true,\"gross_delta\":\"10.00\",\"more_expensive_country\":\"DE\",\"more_expensive_net\":\"150.42\",\"net_of_tax_delta\":\"10.75\"},\"per_country_states\":{\"BE\":[\"PURCHASABLE\"],\"DE\":[\"PURCHASABLE\"]},\"primary_finding\":\"NET_OF_TAX_PRICE_DELTA\"},\"dispatched_at_values\":[\"2026-05-29T16:29:40Z\"],\"dispatched_same_second\":true,\"per_capture\":[{\"capture_id\":\"de-01\",\"exit_ip\":\"77.22.56.14\",\"extracted\":{\"availability\":\"IN_STOCK\",\"currency\":\"EUR\",\"gtin\":\"0195949689673\",\"name\":\"APPLE AirPods 4 mit Aktiver Geräuschunterdrückung, In-ear Kopfhörer Bluetooth Weiß\",\"price\":\"179\",\"raw_signals\":{},\"source\":\"json-ld\"},\"geo_attribution\":{\"agreement\":\"EXIT_ONLY\",\"notes\":[],\"requested_country\":\"DE\",\"source_1_network_exit\":{\"exit_ip\":\"77.22.56.14\",\"proxy_reported_country\":\"DE\",\"rir_country\":\"DE\",\"rir_registry\":\"ripencc\"},\"source_2_response_geo_signals\":{\"currency_consistent_countries\":[\"AT\",\"BE\",\"DE\",\"ES\",\"FI\",\"FR\",\"GR\",\"IE\",\"IT\",\"LU\",\"NL\",\"PT\"],\"currency_observed\":\"EUR\",\"headers\":{\"set-cookie\":\"optid=b6de94df-424a-49f1-b3d2-9936750a9cd7; Domain=.mediamarkt.de; Path=/, __cf_bm=yfnfnfcoReeVaaDdVUM6kmR0d.po1iOWVV2sBwT5z.Q-1780072203.1612778-1.0.1.1-y4u7sl3Wj_94vyG6Uf1NDcSbVBiIL02SJ0m6V0OjC7bzik0uC6VEG0Yz091W7NS4mjj7hGOVVq5QxXIcXOO0kyKqufXrmeqygPsq0Sexd.sbV_XP1bROxgcMGArZo4qmBHxCIb6Hy7Qlfq_Wgw1xWg; HttpOnly; SameSite=None; Secure; Path=/; Domain=mediamarkt.de; Expires=Fri, 29 May 2026 17:00:03 GMT, _cfuvid=CFCNC7Kba6gjhxwLRgn_EQXrHrcAEQh.dbPTCiiJ7W4-1780072203.1612778-1.0.1.1-b2CMIuUFGBDPzMJCXKb2DNUVotQaij_KaNG6IdHK31k; HttpOnly; SameSite=None; Secure; Path=/; Domain=mediamarkt.de\",\"vary\":\"Accept-Encoding\"}}},\"price_gross\":\"179\",\"price_net\":\"150.42\",\"requested_country\":\"DE\",\"session_id\":\"amber-de-1-1780072180580\",\"state\":{\"geo_block_signals\":[],\"rationale\":\"price served (179 EUR); availability=IN_STOCK\",\"soft_block\":{\"is_soft_blocked\":false,\"signals\":[]},\"state\":\"PURCHASABLE\"},\"vat_rate\":{\"as_of\":\"2025-01-01\",\"category\":\"standard\",\"country\":\"DE\",\"rate\":\"0.19\",\"source\":\"European Commission, Taxation and Customs Union - 'VAT rates applied in the Member States of the European Union' (2025 edition)\"}},{\"capture_id\":\"de-02\",\"exit_ip\":\"62.155.220.38\",\"extracted\":{\"availability\":\"IN_STOCK\",\"currency\":\"EUR\",\"gtin\":\"0195949689673\",\"name\":\"APPLE AirPods 4 mit Aktiver Geräuschunterdrückung, In-ear Kopfhörer Bluetooth Weiß\",\"price\":\"179\",\"raw_signals\":{},\"source\":\"json-ld\"},\"geo_attribution\":{\"agreement\":\"EXIT_ONLY\",\"notes\":[],\"requested_country\":\"DE\",\"source_1_network_exit\":{\"exit_ip\":\"62.155.220.38\",\"proxy_reported_country\":\"DE\",\"rir_country\":\"DE\",\"rir_registry\":\"ripencc\"},\"source_2_response_geo_signals\":{\"currency_consistent_countries\":[\"AT\",\"BE\",\"DE\",\"ES\",\"FI\",\"FR\",\"GR\",\"IE\",\"IT\",\"LU\",\"NL\",\"PT\"],\"currency_observed\":\"EUR\",\"headers\":{\"set-cookie\":\"optid=8e1cf53b-059f-42bc-8a46-5438e5209524; Domain=.mediamarkt.de; Path=/, __cf_bm=9ItDnVwat2Ys5o3D_umliYzFdPxnV9_4msnSyAWg_.o-1780072195.5027997-1.0.1.1-Q6Er..T93Xm1GNEGG7Y72JcPr2eq.PahkFPH3mhemz0TkqV4qwv.f81TU_D2tq9TLXMZ63MM8pBfYRknkP2riaSFurYWkkOlvA3ebe5UPSo78T1sl2EkXCBhnG0j9DJ319jO1Y_J9.GkqEPhhNKtkA; HttpOnly; SameSite=None; Secure; Path=/; Domain=mediamarkt.de; Expires=Fri, 29 May 2026 16:59:56 GMT, _cfuvid=B3QtIfGRGXt1.jccr8RbZgSL9d7J4zt1NFjUxkVmv.g-1780072195.5027997-1.0.1.1-b4i_9Tql20vLNcEqfUHwXZ1CpY9NBrAjh6fToRscQLc; HttpOnly; SameSite=None; Secure; Path=/; Domain=mediamarkt.de\",\"vary\":\"Accept-Encoding\"}}},\"price_gross\":\"179\",\"price_net\":\"150.42\",\"requested_country\":\"DE\",\"session_id\":\"amber-de-2-1780072180580\",\"state\":{\"geo_block_signals\":[],\"rationale\":\"price served (179 EUR); availability=IN_STOCK\",\"soft_block\":{\"is_soft_blocked\":false,\"signals\":[]},\"state\":\"PURCHASABLE\"},\"vat_rate\":{\"as_of\":\"2025-01-01\",\"category\":\"standard\",\"country\":\"DE\",\"rate\":\"0.19\",\"source\":\"European Commission, Taxation and Customs Union - 'VAT rates applied in the Member States of the European Union' (2025 edition)\"}},{\"capture_id\":\"de-03\",\"exit_ip\":\"93.207.216.185\",\"extracted\":{\"availability\":\"IN_STOCK\",\"currency\":\"EUR\",\"gtin\":\"0195949689673\",\"name\":\"APPLE AirPods 4 mit Aktiver Geräuschunterdrückung, In-ear Kopfhörer Bluetooth Weiß\",\"price\":\"179\",\"raw_signals\":{},\"source\":\"json-ld\"},\"geo_attribution\":{\"agreement\":\"EXIT_ONLY\",\"notes\":[],\"requested_country\":\"DE\",\"source_1_network_exit\":{\"exit_ip\":\"93.207.216.185\",\"proxy_reported_country\":\"DE\",\"rir_country\":\"DE\",\"rir_registry\":\"ripencc\"},\"source_2_response_geo_signals\":{\"currency_consistent_countries\":[\"AT\",\"BE\",\"DE\",\"ES\",\"FI\",\"FR\",\"GR\",\"IE\",\"IT\",\"LU\",\"NL\",\"PT\"],\"currency_observed\":\"EUR\",\"headers\":{\"set-cookie\":\"optid=cc60c8ed-bb39-4a55-aae5-a5cc8442d599; Domain=.mediamarkt.de; Path=/, __cf_bm=HFIM8HrREUhLyGfhPFdCkt2OpCdcnp3TNSS_2INnyJI-1780072195.3656805-1.0.1.1-6FITM4w5lWa9iOT3itpeJ5cRmy4YGYsX03_b36AccoItb0o.uMt2i.ICWgHBcMZ8WXSihPCYP.OS.eD2KfRK6Za57DYaMqDM7u7OK4bjc9j.X7fO_tMokUdQvcyzWqCDs19hOAOtbAs4DAYR._imxw; HttpOnly; SameSite=None; Secure; Path=/; Domain=mediamarkt.de; Expires=Fri, 29 May 2026 16:59:55 GMT, _cfuvid=xzTC6z8_f3IO4P.jjx8smUfxGnns4_TvorInv93tmEE-1780072195.3656805-1.0.1.1-U_zLbmFQaGqcKnQcg80uHEeQ_upbgrG5lNEgShJMMLA; HttpOnly; SameSite=None; Secure; Path=/; Domain=mediamarkt.de\",\"vary\":\"Accept-Encoding\"}}},\"price_gross\":\"179\",\"price_net\":\"150.42\",\"requested_country\":\"DE\",\"session_id\":\"amber-de-3-1780072180580\",\"state\":{\"geo_block_signals\":[],\"rationale\":\"price served (179 EUR); availability=IN_STOCK\",\"soft_block\":{\"is_soft_blocked\":false,\"signals\":[]},\"state\":\"PURCHASABLE\"},\"vat_rate\":{\"as_of\":\"2025-01-01\",\"category\":\"standard\",\"country\":\"DE\",\"rate\":\"0.19\",\"source\":\"European Commission, Taxation and Customs Union - 'VAT rates applied in the Member States of the European Union' (2025 edition)\"}},{\"capture_id\":\"be-01\",\"exit_ip\":\"109.130.251.198\",\"extracted\":{\"availability\":\"IN_STOCK\",\"currency\":\"EUR\",\"gtin\":\"0195949689673\",\"name\":\"APPLE AirPods 4 Actieve ruisonderdrukking + Oplaadcase MXP93ZM/A In-ear Draadloze oordopjes met Noise cancelling Wit\",\"price\":\"169\",\"raw_signals\":{},\"source\":\"json-ld\"},\"geo_attribution\":{\"agreement\":\"EXIT_ONLY\",\"notes\":[],\"requested_country\":\"BE\",\"source_1_network_exit\":{\"exit_ip\":\"109.130.251.198\",\"proxy_reported_country\":\"BE\",\"rir_country\":\"BE\",\"rir_registry\":\"ripencc\"},\"source_2_response_geo_signals\":{\"currency_consistent_countries\":[\"AT\",\"BE\",\"DE\",\"ES\",\"FI\",\"FR\",\"GR\",\"IE\",\"IT\",\"LU\",\"NL\",\"PT\"],\"currency_observed\":\"EUR\",\"headers\":{\"set-cookie\":\"__cf_bm=1saeq9kThHodGYhxRzpR5YEDjrN3NPapkQUXPpjsgi0-1780072202-1.0.1.1-46Ijd.XCH13CIkO1HjAXaYWZfFdbs6IsHl4tFs2_QzO1gNr75gXiPEHpM6aJgmmnzuiSsjNUWHYwwGB74GuLKIY85UwBxbtAWXyHpBJzIlg; path=/; expires=Fri, 29-May-26 17:00:02 GMT; domain=.mediamarkt.be; HttpOnly; Secure; SameSite=None, _cfuvid=iSVaYqGusTrXYeLN8UKlgw9bLw0SODwGN3UvVZAyYSM-1780072202912-0.0.1.1-604800000; path=/; domain=.mediamarkt.be; HttpOnly; Secure; SameSite=None\",\"vary\":\"Accept-Encoding\"}}},\"price_gross\":\"169\",\"price_net\":\"139.67\",\"requested_country\":\"BE\",\"session_id\":\"amber-be-1-1780072180580\",\"state\":{\"geo_block_signals\":[],\"rationale\":\"price served (169 EUR); availability=IN_STOCK\",\"soft_block\":{\"is_soft_blocked\":false,\"signals\":[]},\"state\":\"PURCHASABLE\"},\"vat_rate\":{\"as_of\":\"2025-01-01\",\"category\":\"standard\",\"country\":\"BE\",\"rate\":\"0.21\",\"source\":\"European Commission, Taxation and Customs Union - 'VAT rates applied in the Member States of the European Union' (2025 edition)\"}},{\"capture_id\":\"be-02\",\"exit_ip\":\"178.118.147.238\",\"extracted\":{\"availability\":\"IN_STOCK\",\"currency\":\"EUR\",\"gtin\":\"0195949689673\",\"name\":\"APPLE AirPods 4 Actieve ruisonderdrukking + Oplaadcase MXP93ZM/A In-ear Draadloze oordopjes met Noise cancelling Wit\",\"price\":\"169\",\"raw_signals\":{},\"source\":\"json-ld\"},\"geo_attribution\":{\"agreement\":\"EXIT_ONLY\",\"notes\":[],\"requested_country\":\"BE\",\"source_1_network_exit\":{\"exit_ip\":\"178.118.147.238\",\"proxy_reported_country\":\"BE\",\"rir_country\":\"BE\",\"rir_registry\":\"ripencc\"},\"source_2_response_geo_signals\":{\"currency_consistent_countries\":[\"AT\",\"BE\",\"DE\",\"ES\",\"FI\",\"FR\",\"GR\",\"IE\",\"IT\",\"LU\",\"NL\",\"PT\"],\"currency_observed\":\"EUR\",\"headers\":{\"set-cookie\":\"__cf_bm=oqpTw.OZL0eCVwExNk3lPJpayigf9d.qGxojKiINfMU-1780072202-1.0.1.1-QhwTLRTBS42HvZpZ.mKQQM7jOxB34dHGl7wFeQw5Zhx2_8m_USrJOSlnyRhgrObYKbqvCh5BEXLToGrNAbLhgLW0jx4ol2ubyBI4sna1hZg; path=/; expires=Fri, 29-May-26 17:00:02 GMT; domain=.mediamarkt.be; HttpOnly; Secure; SameSite=None, _cfuvid=SE8E6HCxXyPVKRIQv4Dcmgc8sDCK0Syo0ZeJ_H9NmL8-1780072202915-0.0.1.1-604800000; path=/; domain=.mediamarkt.be; HttpOnly; Secure; SameSite=None\",\"vary\":\"Accept-Encoding\"}}},\"price_gross\":\"169\",\"price_net\":\"139.67\",\"requested_country\":\"BE\",\"session_id\":\"amber-be-2-1780072180580\",\"state\":{\"geo_block_signals\":[],\"rationale\":\"price served (169 EUR); availability=IN_STOCK\",\"soft_block\":{\"is_soft_blocked\":false,\"signals\":[]},\"state\":\"PURCHASABLE\"},\"vat_rate\":{\"as_of\":\"2025-01-01\",\"category\":\"standard\",\"country\":\"BE\",\"rate\":\"0.21\",\"source\":\"European Commission, Taxation and Customs Union - 'VAT rates applied in the Member States of the European Union' (2025 edition)\"}},{\"capture_id\":\"be-03\",\"exit_ip\":\"94.110.5.137\",\"extracted\":{\"availability\":\"IN_STOCK\",\"currency\":\"EUR\",\"gtin\":\"0195949689673\",\"name\":\"APPLE AirPods 4 Actieve ruisonderdrukking + Oplaadcase MXP93ZM/A In-ear Draadloze oordopjes met Noise cancelling Wit\",\"price\":\"169\",\"raw_signals\":{},\"source\":\"json-ld\"},\"geo_attribution\":{\"agreement\":\"EXIT_ONLY\",\"notes\":[],\"requested_country\":\"BE\",\"source_1_network_exit\":{\"exit_ip\":\"94.110.5.137\",\"proxy_reported_country\":\"BE\",\"rir_country\":\"BE\",\"rir_registry\":\"ripencc\"},\"source_2_response_geo_signals\":{\"currency_consistent_countries\":[\"AT\",\"BE\",\"DE\",\"ES\",\"FI\",\"FR\",\"GR\",\"IE\",\"IT\",\"LU\",\"NL\",\"PT\"],\"currency_observed\":\"EUR\",\"headers\":{\"set-cookie\":\"__cf_bm=wEQzN7LE_FQCuWMt8vlHJZvQl.8Z7RLQ_mWIW8JvB8I-1780072202-1.0.1.1-e.a6wgfY94S1mbzmdLLzrbWmySEAtnpyjn_zQ6Z6ZesCIQXg6RZbgYfJ1JdjdgxkczJFxy2OXJzN5uK.P.Pm7HVjk17cd_u2gOltSpUyHWo; path=/; expires=Fri, 29-May-26 17:00:02 GMT; domain=.mediamarkt.be; HttpOnly; Secure; SameSite=None, _cfuvid=KbUtdnVJJBhI4XayXSuQBxuMsXq7r74WHdVqPJBlX80-1780072202924-0.0.1.1-604800000; path=/; domain=.mediamarkt.be; HttpOnly; Secure; SameSite=None\",\"vary\":\"Accept-Encoding\"}}},\"price_gross\":\"169\",\"price_net\":\"139.67\",\"requested_country\":\"BE\",\"session_id\":\"amber-be-3-1780072180580\",\"state\":{\"geo_block_signals\":[],\"rationale\":\"price served (169 EUR); availability=IN_STOCK\",\"soft_block\":{\"is_soft_blocked\":false,\"signals\":[]},\"state\":\"PURCHASABLE\"},\"vat_rate\":{\"as_of\":\"2025-01-01\",\"category\":\"standard\",\"country\":\"BE\",\"rate\":\"0.21\",\"source\":\"European Commission, Taxation and Customs Union - 'VAT rates applied in the Member States of the European Union' (2025 edition)\"}}],\"requested_at_values\":[\"2026-05-29T16:29:57Z\",\"2026-05-29T16:29:59Z\",\"2026-05-29T16:30:04Z\",\"2026-05-29T16:30:05Z\"],\"same_second_batch\":false,\"schema\":\"amber/facts@2\",\"sku_identity\":{\"canonical_gtin\":\"00195949689673\",\"confidence\":\"GTIN_MATCH\",\"per_capture\":[{\"bundle_descriptor\":null,\"capture_id\":\"de-01\",\"gtin_normalized\":\"00195949689673\",\"gtin_raw\":\"0195949689673\",\"gtin_valid\":true},{\"bundle_descriptor\":null,\"capture_id\":\"de-02\",\"gtin_normalized\":\"00195949689673\",\"gtin_raw\":\"0195949689673\",\"gtin_valid\":true},{\"bundle_descriptor\":null,\"capture_id\":\"de-03\",\"gtin_normalized\":\"00195949689673\",\"gtin_raw\":\"0195949689673\",\"gtin_valid\":true},{\"bundle_descriptor\":null,\"capture_id\":\"be-01\",\"gtin_normalized\":\"00195949689673\",\"gtin_raw\":\"0195949689673\",\"gtin_valid\":true},{\"bundle_descriptor\":null,\"capture_id\":\"be-02\",\"gtin_normalized\":\"00195949689673\",\"gtin_raw\":\"0195949689673\",\"gtin_valid\":true},{\"bundle_descriptor\":null,\"capture_id\":\"be-03\",\"gtin_normalized\":\"00195949689673\",\"gtin_raw\":\"0195949689673\",\"gtin_valid\":true}],\"rationale\":\"identical valid GTIN 00195949689673 across all 6 captures; bundle/warranty consistent\"},\"sku_label\":\"Apple AirPods 4 (ANC, charging case) MXP93 GTIN 0195949689673\",\"url\":{\"BE\":\"https://www.mediamarkt.be/nl/product/_apple-draadloze-oordopjes-airpods-4-actieve-ruisonderdrukking-oplaadcase-mxp93zma-2152461.html\",\"DE\":\"https://www.mediamarkt.de/de/product/_apple-airpods-4-mit-aktiver-gerauschunterdruckung-in-ear-kopfhorer-bluetooth-weiss-2954282.html\"},\"vat_table_note\":\"Net-of-tax computed with the committed sourced VAT table (amber/capture/vat.py); each per-capture fact carries the rate + source it was computed with. net = gross / (1 + rate).\",\"within_country_control\":{\"all_intra_country_agree\":true,\"per_country\":[{\"agreement\":\"AGREE\",\"country\":\"BE\",\"intra_country_spread\":\"0.00\",\"n_purchasable_exits\":3,\"net_max\":\"139.67\",\"net_min\":\"139.67\",\"net_prices\":[\"139.67\",\"139.67\",\"139.67\"],\"session_ids\":[\"amber-be-1-1780072180580\",\"amber-be-2-1780072180580\",\"amber-be-3-1780072180580\"]},{\"agreement\":\"AGREE\",\"country\":\"DE\",\"intra_country_spread\":\"0.00\",\"n_purchasable_exits\":3,\"net_max\":\"150.42\",\"net_min\":\"150.42\",\"net_prices\":[\"150.42\",\"150.42\",\"150.42\"],\"session_ids\":[\"amber-de-1-1780072180580\",\"amber-de-2-1780072180580\",\"amber-de-3-1780072180580\"]}]}}";

/**
 * The sealed facts.json re-indented for on-screen readability of the tamper-proof
 * editor. It is the verbatim RAW_FACTS_JSON (the exact sealed bytes, with the EC
 * VAT-source citation's em-dash rendered as a hyphen for display consistency)
 * parsed and re-stringified with two-space indentation; the demo does not re-hash
 * it in the browser (the deployed demo displays the REAL recorded verifier
 * verdicts rather than re-running cryptography client-side).
 */
export const FACTS_JSON_PRETTY: string = JSON.stringify(JSON.parse(RAW_FACTS_JSON), null, 2);

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
