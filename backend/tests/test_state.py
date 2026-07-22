"""State reducer semantics: errors accumulate, they never overwrite."""

import operator
from typing import get_type_hints

from src.core.state import PolarisState


def test_errors_reducer_is_additive():
    hints = get_type_hints(PolarisState, include_extras=True)
    reducer = hints["errors"].__metadata__[0]
    assert reducer is operator.add
    merged = reducer([{"agent": "a"}], [{"agent": "b"}])
    assert [e["agent"] for e in merged] == ["a", "b"]


def test_contracts_round_trip_through_state():
    from src.core.contracts import ParsedNotice

    parsed = ParsedNotice(
        doc_type="capital_call", fund_name_raw="TechVantage Fund LP", amount_usd=850_000.0
    )
    dumped = parsed.model_dump(mode="json")  # what lives in state / checkpoints
    assert ParsedNotice.model_validate(dumped) == parsed
