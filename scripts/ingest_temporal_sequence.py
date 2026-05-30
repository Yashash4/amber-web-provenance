"""Ingest the real temporal capture sequence into Cognee under the free-tier cap.

The Gemini free tier limits ``gemini-embedding-001`` to ~100 embedding
requests/minute. A single ``cognify`` over all five real packets bursts past that
limit (each packet adds chunk + entity nodes, and the cumulative graph re-embeds
a growing set), so LiteLLM exhausts its retries and surfaces a 422.

The root fix is rate, not payload: ingest packet-by-packet (``reset`` on the
first, ``append`` thereafter) and SPACE the calls so each ``cognify``'s embedding
burst lands in a fresh per-minute window. This builds the SAME complete graph
over all five REAL captures — no data is fabricated, dropped, or duplicated; we
only pace the calls to respect the free-tier quota.

Run::

    python scripts/ingest_temporal_sequence.py

Then query::

    amber-memory query "...is the gap persistent?" --temporal
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from amber.memory.observations import observation_from_packet  # noqa: E402
from amber.memory.store import ingest  # noqa: E402

# The five REAL signed packets, in chronological capture order.
PACKETS = [
    REPO / "samples" / "live_packet",
    REPO / "samples" / "temporal" / "cap-01",
    REPO / "samples" / "temporal" / "cap-02",
    REPO / "samples" / "temporal" / "cap-03",
    REPO / "samples" / "temporal" / "cap-04",
]

# Seconds of genuine IDLE between cognify calls so BOTH the per-minute LLM
# (20 req/min for gemini-2.5-flash) and embedding (100 req/min) free-tier windows
# fully clear before the next packet's cognify fans out its extraction calls.
PACE_SECONDS = 75
# How many times to retry a single packet that trips the per-minute rate limit.
# Generous, because a cumulative cognify can need several fresh windows.
MAX_RETRIES = 6


def _ingest_one(packet: Path, *, reset: bool) -> None:
    obs = observation_from_packet(packet)
    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            n = ingest([obs], reset=reset)
            print(f"  -> ingested {n} ({packet.name}, reset={reset})", flush=True)
            return
        except Exception as exc:  # noqa: BLE001 - surface + retry on rate limit
            last_exc = exc
            msg = str(exc)
            low = msg.lower()
            rate_limited = "quota" in low or "ratelimit" in low or "429" in msg or "422" in msg
            if rate_limited and attempt < MAX_RETRIES:
                print(
                    f"  !! rate-limited on {packet.name} (attempt {attempt}/{MAX_RETRIES}); "
                    f"idling {PACE_SECONDS}s for a fresh per-minute window then retrying",
                    flush=True,
                )
                time.sleep(PACE_SECONDS)
                continue
            raise
    if last_exc is not None:
        raise last_exc


def main() -> int:
    for i, packet in enumerate(PACKETS):
        if not (packet / "facts.json").is_file():
            raise SystemExit(f"missing real packet: {packet}")
        reset = i == 0  # reset on the first, append the rest
        print(f"[{i + 1}/{len(PACKETS)}] {packet.name} (reset={reset})", flush=True)
        _ingest_one(packet, reset=reset)
        if i < len(PACKETS) - 1:
            print(f"  ... pacing {PACE_SECONDS}s for the per-minute embedding window", flush=True)
            time.sleep(PACE_SECONDS)
    print("DONE: all 5 real packets ingested into the Cognee temporal graph.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
