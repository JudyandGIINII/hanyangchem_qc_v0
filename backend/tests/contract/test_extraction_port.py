from __future__ import annotations

from hyc_api.extraction import ExtractionProvider, SyntheticFixtureExtractionProvider
from hyc_api.storage import ImmutableSourceStorage


def test_synthetic_provider_is_contract_only() -> None:
    provider: ExtractionProvider = SyntheticFixtureExtractionProvider()
    candidate = provider.extract(
        "123e4567-e89b-12d3-a456-426614174001", "synthetic://fixture/document"
    )
    assert candidate.provider_name == "synthetic-fixture"
    assert candidate.review_required is False


def test_storage_port_is_a_type_only_boundary() -> None:
    # P1 must not instantiate a real-source storage adapter.
    assert ImmutableSourceStorage.__name__ == "ImmutableSourceStorage"
