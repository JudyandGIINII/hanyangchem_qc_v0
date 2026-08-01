from __future__ import annotations

import os
from dataclasses import dataclass
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from hyc_api.config import Settings
from hyc_api.main import create_app
from hyc_data.p3_fixture_seed import MOISTURE_SPEC_ITEM_ID


@dataclass(slots=True)
class P3Harness:
    client: TestClient
    inspector: dict[str, str]
    lead: dict[str, str]
    admin: dict[str, str]
    context: dict[str, object]
    database_url: str
    app_database_url: str

    def intake(self, *, suffix: str | None = None) -> dict[str, object]:
        marker = suffix or uuid4().hex
        body = {
            "supplier_id": self.context["supplier_id"],
            "material_id": self.context["material_id"],
            "model_id": self.context["model_id"],
            "inbound_no": f"P3-IN-{marker}",
            "receipt_date": "2026-08-01",
            "supplier_lot_no": f"P3-LOT-{marker}",
            "quantity": "100.00",
            "quantity_unit": "kg",
        }
        response = self.client.post(
            "/api/v1/intakes",
            json=body,
            headers=self.inspector | {"Idempotency-Key": f"intake-{marker}"},
        )
        assert response.status_code == 201, response.text
        return response.json()

    def reviewed_extraction(self, *, suffix: str | None = None) -> dict[str, object]:
        marker = suffix or uuid4().hex
        intake = self.intake(suffix=marker)
        document = self.client.post(
            "/api/v1/documents",
            content=f"P3 SYNTHETIC COA {marker}".encode(),
            headers=self.inspector
            | {"X-Filename": f"p3-{marker}.txt", "Content-Type": "text/plain"},
        )
        assert document.status_code == 201, document.text
        extraction = self.client.post(
            f"/api/v1/documents/{document.json()['document_id']}/extractions",
            headers=self.inspector,
        )
        assert extraction.status_code == 201, extraction.text
        fields = [
            {
                "field_key": field["field_key"],
                "manual_text": None,
                "final_text": field["ocr_text"],
                "source": "OCR",
                "reason": "synthetic fixture confirmed",
                "logic_conflict": False,
            }
            for field in extraction.json()["fields"]
        ]
        review = self.client.put(
            f"/api/v1/documents/{document.json()['document_id']}/reviews/"
            f"{extraction.json()['run_id']}",
            json={"fields": fields, "allocation_id": intake["allocation_id"]},
            headers=self.inspector | {"If-Match": str(extraction.json()["version"])},
        )
        assert review.status_code == 200, review.text
        return intake | document.json() | extraction.json()

    def reviewed(self, *, suffix: str | None = None) -> dict[str, object]:
        marker = suffix or uuid4().hex
        reviewed = self.reviewed_extraction(suffix=marker)
        inspection = self.client.post(
            "/api/v1/inspections",
            json={
                "allocation_id": reviewed["allocation_id"],
                "extraction_run_id": reviewed["run_id"],
            },
            headers=self.inspector | {"Idempotency-Key": f"inspection-{marker}"},
        )
        assert inspection.status_code == 201, inspection.text
        return reviewed | inspection.json()

    def clear_hold(self, inspection_id: str) -> dict[str, object]:
        current = self.client.get(
            f"/api/v1/inspections/{inspection_id}", headers=self.inspector
        ).json()
        response = self.client.put(
            f"/api/v1/inspections/{inspection_id}/internal-results",
            json={
                "results": [
                    {
                        "spec_item_id": str(MOISTURE_SPEC_ITEM_ID),
                        "values": ["0.10", "0.12", "0.11"],
                    }
                ]
            },
            headers=self.inspector | {"If-Match": str(current["version"])},
        )
        assert response.status_code == 200, response.text
        return response.json()

    def submit(self, inspection_id: str, version: int) -> dict[str, object]:
        response = self.client.post(
            f"/api/v1/inspections/{inspection_id}/submit",
            headers=self.inspector | {"If-Match": str(version)},
        )
        assert response.status_code == 200, response.text
        return response.json()

    def approve(self, inspection_id: str, version: int, *, key: str | None = None):
        return self.client.post(
            f"/api/v1/inspections/{inspection_id}/approvals",
            json={"action": "APPROVE", "reason": None},
            headers=self.lead
            | {
                "If-Match": str(version),
                "Idempotency-Key": key or f"approve-{inspection_id}",
            },
        )


def _auth(client: TestClient, fixture_principal: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/local-auth/sessions", json={"fixture_principal": fixture_principal}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['session_handle']}"}


@pytest.fixture(scope="session")
def p3() -> P3Harness:
    database_url = os.environ.get("HYC_P3_TEST_POSTGRES_DSN")
    if not database_url:
        pytest.skip("HYC_P3_TEST_POSTGRES_DSN is required")
    app_database_url = os.environ.get("HYC_P3_TEST_APP_DSN")
    if not app_database_url:
        pytest.skip("HYC_P3_TEST_APP_DSN is required")
    storage = os.environ.get("HYC_P3_TEST_STORAGE", "/tmp/hyc-p3-api-tests")
    app = create_app(
        Settings(
            database_url=database_url,
            redis_url="redis://127.0.0.1:1/0",
            check_database_on_ready=False,
            check_redis_on_ready=False,
            p3_fixture_mode=True,
            p3_storage_root=storage,
            p3_fault_injection_enabled=True,
        )
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        inspector = _auth(client, "p3-inspector")
        lead = _auth(client, "p3-lead")
        admin = _auth(client, "p3-admin")
        context_response = client.get("/api/v1/fixtures/p3/context", headers=inspector)
        assert context_response.status_code == 200, context_response.text
        yield P3Harness(
            client,
            inspector,
            lead,
            admin,
            context_response.json(),
            database_url,
            app_database_url,
        )
    create_engine(database_url).dispose()
