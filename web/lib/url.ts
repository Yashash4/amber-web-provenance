/**
 * Pure, Node-free helpers for the packet's product URL.
 *
 * These live in their own module (no `node:fs` / `node:path` imports) so the
 * client `SplitFrame` component can import them without dragging the Node-only
 * packet loader into the browser bundle.
 *
 * The packet's `url` field comes in TWO shapes and the UI must handle both:
 *   - a single string  — the labelled fixture's one canonical product page.
 *   - a `{ country: url }` map — a real per-country Bright Data capture, where
 *     each market is fetched from its own storefront URL
 *     (e.g. `{ "DE": "...mediamarkt.de...", "BE": "...mediamarkt.be..." }`).
 * The map object is NEVER rendered directly as a React child.
 */
export type PacketUrl = string | Record<string, string>;

/**
 * Coerce a packet's raw `url` field into the {@link PacketUrl} shape WITHOUT
 * inventing data. A string passes through; a `{ country: url }` object is kept
 * as a string-valued map (non-string members coerced to string defensively);
 * anything else (null/undefined/number/array) becomes "". We never fabricate.
 */
export function normalizeUrl(raw: unknown): PacketUrl {
  if (typeof raw === "string") return raw;
  if (raw && typeof raw === "object" && !Array.isArray(raw)) {
    const out: Record<string, string> = {};
    for (const [k, v] of Object.entries(raw as Record<string, unknown>)) {
      out[k] = typeof v === "string" ? v : String(v);
    }
    return out;
  }
  return "";
}

/** True when the packet's url is a per-country `{ country: url }` map. */
export function isUrlMap(url: PacketUrl): url is Record<string, string> {
  return typeof url === "object";
}

/**
 * The URL to show for a single country. For a per-country map, returns that
 * country's URL (or "" if absent). For a single string, returns the string —
 * a fixture's one canonical URL applies to every column.
 */
export function urlForCountry(url: PacketUrl, country: string): string {
  if (typeof url === "string") return url;
  return url[country] ?? "";
}

/**
 * Flatten the url into the list of distinct, non-empty URLs it carries — for a
 * header summary line. A single string → one entry; a per-country map → its
 * distinct values (deduped, so identical per-country URLs collapse to one).
 */
export function urlList(url: PacketUrl): string[] {
  const values = typeof url === "string" ? [url] : Object.values(url);
  return Array.from(new Set(values.filter((u) => u.length > 0)));
}
