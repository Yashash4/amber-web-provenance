"""Build the TriggerWare SQL for an Amber event row + the threshold predicate.

TriggerWare is "SQL Over Everything": a trigger is a saved SQL query that it
polls on a schedule, accumulating the rows that the query returns. Amber turns a
signed observation into a one-row ``SELECT`` of the event's signed facts, gated
by a ``WHERE`` predicate that encodes the brand's alert threshold. When (and
only when) the signed net-of-tax delta exceeds the threshold — or an
access/payment denial is present — the query yields a row, so the trigger fires
and the polling agent sees it as an ``added`` delta.

All literals are emitted with safe SQL escaping (single-quote doubling); numbers
go through :class:`decimal.Decimal` -> fixed-point so no float drift reaches the
predicate. No value is invented — every column comes from the signed Layer-1
facts via :mod:`amber.workflow.event`.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from amber.workflow.event import KIND_ACCESS_DENIAL, KIND_NET_DELTA, AmberEvent

# Columns that MUST be emitted as NUMERIC SQL literals (never quoted strings) so
# TriggerWare's SQL engine can evaluate numeric predicates on them. (A quoted
# '10.75' makes `> 1.00` an "invalid operands for infix operator >" error on the
# real API — confirmed live; this is the root fix, not a workaround.) These are
# pulled from the event's typed Decimal fields, not the JSON-string row.
MONEY_COLUMNS: tuple[str, ...] = (
    "net_of_tax_delta_eur",
    "gross_delta_eur",
    "cheaper_net_eur",
    "more_expensive_net_eur",
    "threshold_eur",
)

# The compact, well-typed signal columns the TRIGGER carries. A trigger is a
# DETECTOR — it needs the predicate column(s) + short identifying scalars, NOT
# the verbose human prose. Long descriptive literals (the fact_banner, the full
# SKU label) make TriggerWare's trigger validator time out (HTTP 500 "Request
# timed out" — confirmed live), and they belong on the alert + the /query row
# anyway (both rendered/served locally and tolerant of any content). Restricting
# the saved trigger to these signal columns is the root design fix.
TRIGGER_COLUMNS: tuple[str, ...] = (
    "kind",
    "countries",
    "net_of_tax_delta_eur",
    "gross_delta_eur",
    "cheaper_country",
    "more_expensive_country",
    "cheaper_net_eur",
    "more_expensive_net_eur",
    "geo_blocked_countries",
    "purchasable_countries",
    "within_country_control_agree",
    "sku_identity_confidence",
    "threshold_eur",
)


# How a None column is serialised in SQL sent to TriggerWare. The engine — BOTH
# /query and the trigger validator — silently mis-handles bare NULL and bare
# TRUE/FALSE literals (a NULL/bool column makes /query return 0 rows and a
# trigger create return HTTP 500 — both confirmed live). So every column is
# emitted as a concretely-typed scalar: None -> '' and bool -> 'true'/'false'
# (string literals). This is the root serialisation fix, not a workaround.
_NULL_LITERAL = "''"


def _sql_str(value: Any) -> str:
    """Render a value as a well-typed SQL literal for the TriggerWare engine.

    Every column is a concretely-typed scalar: ``None`` -> ``''`` and ``bool`` ->
    ``'true'``/``'false'`` (string literals), because TriggerWare mis-handles bare
    ``NULL``/``TRUE``/``FALSE``. Numbers render unquoted; strings are single-quoted
    with quote-doubling.
    """
    if value is None:
        return _NULL_LITERAL
    if isinstance(value, bool):
        return "'true'" if value else "'false'"
    if isinstance(value, (int, Decimal)):
        return format(value, "f") if isinstance(value, Decimal) else str(value)
    # Everything else -> a single-quoted string with quote-doubling.
    return "'" + str(value).replace("'", "''") + "'"


def _sql_literal_for(name: str, value: Any) -> str:
    """SQL literal for a column: numeric (unquoted) for money columns, else typed.

    Money columns arrive in ``as_row()`` as fixed-point strings (JSON-safe); for
    SQL we re-render them as bare numeric literals so predicates like
    ``net_of_tax_delta_eur > 1.00`` are numeric comparisons, not string ones.
    """
    if name in MONEY_COLUMNS and value is not None:
        # value is a fixed-point money string; emit it unquoted as a number.
        return format(Decimal(str(value)), "f")
    return _sql_str(value)


def _column(name: str, value: Any) -> str:
    return f"{_sql_literal_for(name, value)} AS {name}"


def build_query_sql(event: AmberEvent, *, restrict_to_signal: bool = False) -> str:
    """A one-row SELECT of the event's signed facts (the queryable API row).

    This is what ``POST /query`` materialises and what the brand-protection agent
    can run ad hoc to read the current signed observation as a table row. Money
    columns are emitted as numeric literals so numeric predicates work; NULL/bool
    are serialised as well-typed strings (the engine mis-handles bare NULL/bool).
    With ``restrict_to_signal=True`` only the compact signal columns are emitted
    (the verbose prose columns make the trigger validator time out) — that is the
    form the saved TRIGGER uses.
    """
    row = event.as_row()
    if restrict_to_signal:
        items = [(name, row[name]) for name in TRIGGER_COLUMNS]
    else:
        items = list(row.items())
    cols = [_column(name, value) for name, value in items]
    return "SELECT " + ", ".join(cols)


def build_trigger_sql(event: AmberEvent, threshold_eur: Decimal) -> str:
    """The trigger's saved SQL: the signal columns, gated by the alert predicate.

    For a net-of-tax delta the predicate is ``net_of_tax_delta_eur >
    <threshold>`` (the brand's alert knob). For an access/payment denial the
    finding itself is the event (no numeric threshold), so the predicate tests
    that a geo-blocked country is present (a non-empty string column). The query
    yields its single row only when the predicate holds, so the trigger fires
    exactly when Amber's signed facts cross the brand's alert condition.
    """
    base = build_query_sql(event, restrict_to_signal=True)
    if event.kind == KIND_NET_DELTA:
        predicate = f"net_of_tax_delta_eur > {format(threshold_eur, 'f')}"
    elif event.kind == KIND_ACCESS_DENIAL:
        # geo_blocked_countries is a (possibly empty) string in trigger form.
        predicate = "geo_blocked_countries <> ''"
    else:  # defensive: unknown kind never silently becomes an always-fire query
        raise ValueError(f"cannot build trigger SQL for event kind {event.kind!r}")
    # Wrap so the predicate evaluates against the materialised, named columns.
    return f"SELECT * FROM ({base}) AS amber_event WHERE {predicate}"
