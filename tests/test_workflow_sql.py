"""Tests for the TriggerWare SQL builder (query row + threshold predicate)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from amber.workflow.event import extract_event
from amber.workflow.sql import _sql_str, build_query_sql, build_trigger_sql
from tests.test_workflow_event import _denial_facts, _net_delta_facts


def test_sql_str_escapes_single_quotes():
    assert _sql_str("O'Brien") == "'O''Brien'"
    assert _sql_str("plain") == "'plain'"


def test_sql_str_renders_types():
    # TriggerWare mis-handles bare NULL/TRUE/FALSE, so they render as well-typed
    # string literals; numbers render unquoted.
    assert _sql_str(None) == "''"
    assert _sql_str(True) == "'true'"
    assert _sql_str(False) == "'false'"
    assert _sql_str(Decimal("10.75")) == "10.75"
    assert _sql_str(42) == "42"


def test_query_sql_is_a_single_select_with_named_columns():
    event = extract_event(_net_delta_facts("10.75"))
    sql = build_query_sql(event)
    assert sql.startswith("SELECT ")
    assert "AS net_of_tax_delta_eur" in sql
    assert "AS more_expensive_country" in sql
    # Money columns are NUMERIC literals (unquoted) so numeric predicates work.
    assert "10.75 AS net_of_tax_delta_eur" in sql
    assert "'10.75'" not in sql
    # String columns stay quoted.
    assert "'DE' AS more_expensive_country" in sql


def test_money_columns_are_numeric_not_quoted():
    event = extract_event(_net_delta_facts("10.75"))
    sql = build_query_sql(event)
    for col in ("net_of_tax_delta_eur", "gross_delta_eur", "cheaper_net_eur",
                "more_expensive_net_eur", "threshold_eur"):
        # numeric literal form "<num> AS <col>", never "'<num>' AS <col>"
        assert f" AS {col}" in sql
    assert "10.00 AS gross_delta_eur" in sql
    assert "139.67 AS cheaper_net_eur" in sql
    assert "150.42 AS more_expensive_net_eur" in sql
    assert "1.00 AS threshold_eur" in sql


def test_trigger_sql_net_delta_predicate_uses_threshold():
    event = extract_event(_net_delta_facts("10.75"), threshold=None)
    sql = build_trigger_sql(event, Decimal("1.00"))
    assert "WHERE net_of_tax_delta_eur > 1.00" in sql
    assert sql.startswith("SELECT * FROM (")
    assert ") AS amber_event WHERE" in sql


def test_trigger_sql_denial_predicate():
    event = extract_event(_denial_facts())
    sql = build_trigger_sql(event, Decimal("1.00"))
    assert "geo_blocked_countries <> ''" in sql
    # the denial finding's blocked country is materialised in the trigger row
    assert "'BE' AS geo_blocked_countries" in sql


def test_trigger_sql_threshold_above_delta_yields_unsatisfiable_predicate():
    """A high threshold builds a predicate the event row cannot satisfy."""
    event = extract_event(_net_delta_facts("10.75"))
    sql = build_trigger_sql(event, Decimal("9.00"))
    # The materialised row has 10.75; predicate > 9.00 -> would yield the row.
    assert "WHERE net_of_tax_delta_eur > 9.00" in sql


def test_trigger_sql_omits_verbose_prose_columns():
    """The saved trigger carries only compact signal columns (validator timeout fix).

    The verbose fact_banner / sku_label make TriggerWare's trigger validator time
    out, so they are NOT in the saved trigger SQL — they live on the alert + the
    /query row instead.
    """
    event = extract_event(_net_delta_facts("10.75"))
    sql = build_trigger_sql(event, Decimal("1.00"))
    assert "fact_banner" not in sql
    assert "sku_label" not in sql
    # but the predicate column + the key signal columns ARE present
    assert "net_of_tax_delta_eur" in sql
    assert "more_expensive_country" in sql
    assert "within_country_control_agree" in sql


def test_query_sql_includes_full_prose_columns():
    """The /query API row keeps the human-readable columns (it tolerates them)."""
    event = extract_event(_net_delta_facts("10.75"))
    sql = build_query_sql(event)
    assert "AS fact_banner" in sql
    assert "AS sku_label" in sql
    # NULL/bool are still well-typed strings (the engine mis-handles bare NULL/bool)
    assert "'true' AS within_country_control_agree" in sql
    assert "'' AS geo_blocked_countries" in sql


def test_trigger_sql_rejects_unknown_kind():
    event = extract_event(_net_delta_facts("10.75"))
    object.__setattr__(event, "kind", "MYSTERY")
    with pytest.raises(ValueError):
        build_trigger_sql(event, Decimal("1.00"))


def test_sku_label_with_quote_is_escaped_in_sql():
    facts = _net_delta_facts("10.75")
    facts["sku_label"] = "Brand's Gadget"
    event = extract_event(facts)
    sql = build_query_sql(event)
    assert "'Brand''s Gadget'" in sql
