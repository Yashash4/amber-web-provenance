"""ONE guarded live smoke test against the real TriggerWare API.

Skipped by default so the suite never makes live calls. Enable with::

    AMBER_WORKFLOW_LIVE=1 pytest tests/test_workflow_live_smoke.py -q

It hits the real API to confirm end-to-end wiring: key resolution -> create a
trigger from the real signed packet -> poll it -> confirm it fired on the
€10.75 delta -> render the alert -> DELETE the trigger (cleanup). It uses a
unique, time-stamped trigger name so a leftover from a crashed run never
collides, and always attempts to delete what it created.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from amber.workflow.client import APIKeyMissing, TriggerWareClient, load_api_key
from amber.workflow.event import EventThreshold
from amber.workflow.workflow import alert_from_event, arm_from_packet

LIVE = os.environ.get("AMBER_WORKFLOW_LIVE") == "1"

pytestmark = pytest.mark.skipif(
    not LIVE,
    reason="live TriggerWare smoke test; set AMBER_WORKFLOW_LIVE=1 to run",
)

REPO = Path(__file__).resolve().parent.parent
LIVE_PACKET = REPO / "samples" / "live_packet"


def test_live_arm_poll_fire_alert_cleanup():
    try:
        load_api_key()
    except APIKeyMissing:
        pytest.skip("no TriggerWare key resolvable")
    if not LIVE_PACKET.exists():
        pytest.skip("live_packet sample missing")

    prefix = f"amber_smoke_{int(time.time())}"
    client = TriggerWareClient()
    armed = None
    try:
        armed = arm_from_packet(
            LIVE_PACKET,
            client,
            threshold=EventThreshold.from_eur("1.00"),
            schedule_s=300,
            name_prefix=prefix,
        )
        assert armed.created is True
        assert "WHERE net_of_tax_delta_eur > 1.00" in armed.trigger.query
        delta = client.poll_trigger(armed.trigger.name)
        assert delta.fired, "trigger did not fire on the real €10.75 delta"
        alert = alert_from_event(armed.event)
        assert "violation" not in alert.render_text().lower()
        assert alert.detail["net_of_tax_delta_eur"] == "10.75"
    finally:
        if armed is not None:
            client.delete_trigger(armed.trigger.name)
        client.close()
