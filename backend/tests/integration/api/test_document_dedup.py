from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest

pytestmark = pytest.mark.postgres


def test_document_sequential_and_concurrent_deduplication(p3) -> None:
    body = f"P3 SYNTHETIC DEDUPE {uuid4()}".encode()
    headers = p3.inspector | {"X-Filename": "synthetic.txt", "Content-Type": "text/plain"}
    first = p3.client.post("/api/v1/documents", content=body, headers=headers)
    second = p3.client.post("/api/v1/documents", content=body, headers=headers)
    assert (first.status_code, second.status_code) == (201, 200)
    assert first.json()["document_id"] == second.json()["document_id"]

    concurrent_body = f"P3 SYNTHETIC CONCURRENT {uuid4()}".encode()
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(
            executor.map(
                lambda _: p3.client.post(
                    "/api/v1/documents", content=concurrent_body, headers=headers
                ),
                range(2),
            )
        )
    assert sorted(response.status_code for response in responses) == [200, 201]
    assert len({response.json()["document_id"] for response in responses}) == 1


@pytest.mark.parametrize(
    ("body", "expected_status", "expected_message"),
    [
        (b"", 422, "Document body is empty"),
        (b"x" * (10 * 1024 * 1024 + 1), 413, "Document body exceeds 10 MiB"),
    ],
    ids=["empty", "over-limit"],
)
def test_document_upload_rejects_invalid_sizes_without_storage_residue(
    p3, body: bytes, expected_status: int, expected_message: str
) -> None:
    settings = p3.client.app.state.settings
    configured_root = Path(settings.p3_storage_root)
    invalid_root = configured_root / f"invalid-upload-{uuid4().hex}"
    settings.p3_storage_root = str(invalid_root)
    try:
        response = p3.client.post(
            "/api/v1/documents",
            content=body,
            headers=p3.inspector
            | {"X-Filename": "invalid-size.txt", "Content-Type": "text/plain"},
        )
    finally:
        settings.p3_storage_root = str(configured_root)

    assert response.status_code == expected_status
    assert response.json() == {
        "schema_version": "1.0",
        "code": "HTTP_ERROR",
        "message": expected_message,
        "correlation_id": response.headers["X-Correlation-ID"],
    }
    assert str(invalid_root) not in response.text
    assert "p3-upload-" not in response.text
    assert not invalid_root.exists()
