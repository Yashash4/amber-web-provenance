"""Tests for the arm/poll/alert orchestration + the LAYER BOUNDARY guarantee."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from amber.workflow.client import Trigger, TriggerDelta
from amber.workflow.event import EventThreshold, NoEventError
from amber.workflow.workflow import (
    Alert,
    alert_from_event,
    arm_and_verify,
    arm_from_packet,
    run_query_api,
    trigger_name_for,
)
from tests.test_workflow_event import _net_delta_facts

REPO = Path(__file__).resolve().parent.parent
LIVE_PACKET = REPO / "samples" / "live_packet"


class _FakeClient:
    """A fake TriggerWareClient capturing arm/poll/query interactions."""

    def __init__(self, *, existing: list[Trigger] | None = None, query_rows=None,
                 poll_delta: TriggerDelta | None = None):
        self._existing = existing or []
        self.created: list[dict] = []
        self.updated: list[dict] = []
        self.polled: list[str] = []
        self._query_rows = query_rows if query_rows is not None else [[1]]
        self._poll_delta = poll_delta

    def list_triggers(self):
        return list(self._existing)

    def create_trigger(self, name, query, *, schedule, delivery=None):
        self.created.append({"name": name, "query": query, "schedule": schedule})
        return Trigger(name=name, query=query, schedule=schedule, status="enabled")

    def update_trigger(self, name, *, query=None, schedule=None, status=None):
        self.updated.append({"name": name, "query": query, "schedule": schedule})
        return Trigger(
            name=name,
            query=query or "",
            schedule=schedule or 0,
            status=status or "enabled",
        )

    def poll_trigger(self, name):
        self.polled.append(name)
        if self._poll_delta is not None:
            return self._poll_delta
        # default: fire with one added row
        return TriggerDelta(added=[self._query_rows[0]], deleted=[])

    class _QR:
        def __init__(self, rows):
            self.rows = rows
            self.signature = ["net_of_tax_delta_eur"]

        def as_records(self):
            return [{"net_of_tax_delta_eur": r[0]} for r in self.rows]

    def query(self, sql, *, language=None):
        return self._QR(self._query_rows)

    def close(self):
        pass


def _packet(tmp_path: Path, facts: dict) -> Path:
    pdir = tmp_path / "amber_packet"
    pdir.mkdir()
    (pdir / "facts.json").write_text(json.dumps(facts), encoding="utf-8")
    return pdir


def test_trigger_name_is_deterministic_and_safe():
    n = trigger_name_for("Apple AirPods 4 (ANC) GTIN 0195949689673")
    assert n.startswith("amber_")
    assert all(c.islower() or c.isdigit() or c == "_" for c in n)
    # idempotent
    assert n == trigger_name_for("Apple AirPods 4 (ANC) GTIN 0195949689673")


def test_arm_creates_a_trigger(tmp_path: Path):
    pdir = _packet(tmp_path, _net_delta_facts("10.75"))
    client = _FakeClient()
    armed = arm_from_packet(pdir, client, threshold=EventThreshold.from_eur("1.00"))
    assert armed.created is True
    assert len(client.created) == 1
    assert "WHERE net_of_tax_delta_eur > 1.00" in client.created[0]["query"]


def test_arm_updates_an_existing_trigger(tmp_path: Path):
    pdir = _packet(tmp_path, _net_delta_facts("10.75"))
    name = trigger_name_for(_net_delta_facts()["sku_label"])
    client = _FakeClient(existing=[Trigger(name=name, query="old", schedule=60)])
    armed = arm_from_packet(pdir, client)
    assert armed.created is False
    assert len(client.updated) == 1


def test_arm_raises_no_event_below_threshold(tmp_path: Path):
    pdir = _packet(tmp_path, _net_delta_facts("0.50"))
    client = _FakeClient()
    with pytest.raises(NoEventError):
        arm_from_packet(pdir, client, threshold=EventThreshold.from_eur("1.00"))
    assert client.created == []  # never armed a non-event


def test_arm_and_verify_fires_and_alerts(tmp_path: Path):
    pdir = _packet(tmp_path, _net_delta_facts("10.75"))
    client = _FakeClient(query_rows=[["10.75"]])
    armed, delta, alert = arm_and_verify(pdir, client, threshold=EventThreshold.from_eur("1.00"))
    assert delta.fired is True
    assert isinstance(alert, Alert)
    assert "PRICE DELTA DETECTED" in alert.fact_banner
    assert "violation" not in alert.render_text().lower()


def test_arm_and_verify_no_fire_when_delta_empty(tmp_path: Path):
    pdir = _packet(tmp_path, _net_delta_facts("10.75"))
    client = _FakeClient(poll_delta=TriggerDelta(added=[], deleted=[]))
    _, delta, alert = arm_and_verify(pdir, client)
    assert delta.fired is False
    assert alert is None


def test_run_query_api_returns_records(tmp_path: Path):
    pdir = _packet(tmp_path, _net_delta_facts("10.75"))
    client = _FakeClient(query_rows=[["10.75"]])
    records = run_query_api(pdir, client)
    assert records == [{"net_of_tax_delta_eur": "10.75"}]


def test_alert_states_fact_not_verdict():
    from amber.workflow.event import extract_event

    event = extract_event(_net_delta_facts("10.75"))
    alert = alert_from_event(event)
    body = json.dumps(alert.as_dict())
    assert "violation" not in body.lower()
    assert alert.detail["net_of_tax_delta_eur"] == "10.75"
    assert alert.detail["within_country_control_agree"] is True


# -- THE LAYER BOUNDARY: never write into the signed packet -------------- #
def test_arm_does_not_write_into_the_packet(tmp_path: Path):
    pdir = _packet(tmp_path, _net_delta_facts("10.75"))
    before = sorted(p.name for p in pdir.iterdir())
    before_bytes = (pdir / "facts.json").read_bytes()
    client = _FakeClient()
    arm_and_verify(pdir, client)
    after = sorted(p.name for p in pdir.iterdir())
    assert before == after  # no new file inside the packet
    assert (pdir / "facts.json").read_bytes() == before_bytes  # facts unchanged


@pytest.mark.skipif(not LIVE_PACKET.exists(), reason="live_packet sample missing")
def test_live_packet_arms_and_fires_against_fake_client():
    """End-to-end orchestration over the REAL packet, mocked transport."""
    client = _FakeClient(query_rows=[["10.75", "DE"]])
    armed, delta, alert = arm_and_verify(
        LIVE_PACKET, client, threshold=EventThreshold.from_eur("1.00")
    )
    assert armed.event.net_of_tax_delta_eur is not None
    assert "WHERE net_of_tax_delta_eur > 1.00" in armed.trigger_sql
    assert delta.fired is True
    assert alert is not None and "DE" in alert.fact_banner


@pytest.mark.skipif(not LIVE_PACKET.exists(), reason="live_packet sample missing")
def test_live_packet_still_verifies_green_after_workflow():
    """After running the workflow over it, the real packet still verifies GREEN."""
    from amber.cli import main as verify_main

    client = _FakeClient(query_rows=[["10.75", "DE"]])
    arm_and_verify(LIVE_PACKET, client)
    # verify_packet against the committed trusted signer allowlist -> exit 0.
    rc = verify_main([str(LIVE_PACKET)])
    assert rc == 0
