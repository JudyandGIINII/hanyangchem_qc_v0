from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID, uuid4

from hyc_api.contracts import BoundingBox, ExtractionCandidate, ExtractionValue, SourceReference


class ExtractionProvider(Protocol):
    def extract(self, document_id: str, source_reference: str) -> ExtractionCandidate: ...


class SyntheticFixtureExtractionProvider:
    """Only synthetic contract data; this port never calls OCR or AI."""

    def extract(self, document_id: str, source_reference: str) -> ExtractionCandidate:
        reference = SourceReference(
            document_id=UUID(document_id),
            source_reference=source_reference,
            page_number=1,
            bbox=BoundingBox(left=0.0, top=0.0, right=1.0, bottom=1.0),
        )
        return ExtractionCandidate(
            schema_version="1.0",
            candidate_id=uuid4(),
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            document=reference,
            provider_name="synthetic-fixture",
            values=[
                ExtractionValue(
                    item_key="SYNTHETIC_VALUE",
                    raw_text="TEST_FIXTURE_VALUE",
                    normalized_value=Decimal("1.00"),
                    provenance=reference,
                    confidence=1.0,
                    review_required=False,
                )
            ],
            review_required=False,
        )
