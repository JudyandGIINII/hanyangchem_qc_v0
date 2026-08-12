from __future__ import annotations

from collections.abc import Generator
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from hyc_api.traceability_source import load_traceability_graph
from hyc_data.models import Base

# No postgres marker: the fixture uses sqlite, so these run in `make check`.


@pytest.fixture
def session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as value:
        yield value
    engine.dispose()


def test_flag_off_reads_no_table_at_all(session: Session) -> None:
    """The decisive seam condition: off must mean off, not "on but empty".

    A flag that still queries has a live path nobody authorised, so this counts
    statements rather than trusting the returned value.
    """

    statements: list[str] = []

    @event.listens_for(session.bind, "before_cursor_execute")
    def _record(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        statements.append(statement)

    graph = load_traceability_graph(session, enabled=False)

    assert graph.enabled is False
    assert graph.allocations == {}
    assert graph.consumptions == ()
    assert graph.production_lots == ()
    assert statements == [], f"flag-off path issued SQL: {statements}"


def test_flag_on_does_query_the_tables(session: Session) -> None:
    # Positive control. Without it the assertion above would also hold if the
    # loader were broken and never queried in either mode.
    statements: list[str] = []

    @event.listens_for(session.bind, "before_cursor_execute")
    def _record(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        statements.append(statement)

    graph = load_traceability_graph(session, enabled=True)

    assert graph.enabled is True
    assert statements != []


def test_loader_returns_domain_types_the_traversal_accepts(session: Session) -> None:
    from hyc_domain.traceability import impact_scope

    graph = load_traceability_graph(session, enabled=True)
    # An empty database must traverse to an empty result rather than raising:
    # the seam is expected to be live and unpopulated for a long time.
    assert (
        impact_scope("missing-lot", graph.allocations, graph.consumptions, graph.production_lots)
        == ()
    )


def test_quantities_stay_decimal(session: Session) -> None:
    # Guards the repository-wide rule that quality quantities never become float.
    from hyc_domain.traceability import Consumption

    sample = Consumption(
        allocation_id="a", production_lot_id="p", quantity=Decimal("1.50")
    )
    assert isinstance(sample.quantity, Decimal)
    assert str(sample.quantity) == "1.50"
    assert date(2026, 8, 1).isoformat() == "2026-08-01"
