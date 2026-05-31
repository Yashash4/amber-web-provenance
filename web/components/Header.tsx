/**
 * The dashboard header bar: the AMBER wordmark with the amber dot, the product
 * one-liner, a "Built on Bright Data" pill, and the live "verify_packet GREEN"
 * status chip. This is the top frame of the evidence console.
 */
export function Header() {
  return (
    <header className="sticky top-0 z-20 border-b border-white/10 bg-[#07070a]/85 backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-5 gap-y-3 px-4 py-3 sm:px-6 lg:px-8">
        <div className="flex items-center gap-3">
          <span
            className="h-3.5 w-3.5 rounded-full bg-amber"
            style={{ boxShadow: "0 0 14px 2px rgba(245,158,11,0.8)" }}
            aria-hidden
          />
          <span className="text-xl font-black tracking-[0.18em] text-amber">AMBER</span>
        </div>

        <p className="order-last w-full text-[12px] leading-snug text-white/55 sm:order-none sm:w-auto sm:flex-1 sm:border-l sm:border-white/10 sm:pl-5">
          Catch gray-market diversion. Recover the margin.
        </p>

        <div className="flex items-center gap-2.5">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-white/15 bg-white/5 px-3 py-1 text-[11px] font-semibold text-white/75">
            <span className="h-1.5 w-1.5 rounded-full bg-advisory" aria-hidden />
            Built on Bright Data
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-verified/45 bg-verified/10 px-3 py-1 text-[11px] font-bold text-verified">
            <span className="chip-dot h-1.5 w-1.5 rounded-full bg-verified" aria-hidden />
            verify_packet GREEN
          </span>
        </div>
      </div>
    </header>
  );
}
