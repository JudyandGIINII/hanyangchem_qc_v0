from __future__ import annotations

import hashlib
import json
import socket
import tarfile
from pathlib import Path

import pytest
from backend.scripts.bootstrap_local_ocr_models import (
    _validate_download_url,
    bootstrap,
)

from hyc_local_ocr.errors import LocalOcrError
from hyc_local_ocr.manifest import load_and_verify_manifest, load_manifest, model_tree_sha256
from hyc_local_ocr.network import deny_outbound_network


def _write_manifest(tmp_path: Path, *, tree_sha256: str, local_path: str = "detection") -> Path:
    payload = {
        "schema_version": "hyc.local-ocr-model-manifest.v1",
        "engine": "paddleocr",
        "engine_version": "3.7.0",
        "runtime_version": "3.3.1",
        "language": "korean-english-numeric",
        "artifacts": [
            {
                "role": "text-detection",
                "model": "PP-OCRv5_mobile_det",
                "version": "PP-OCRv5",
                "upstream": "PaddlePaddle/PaddleOCR",
                "license": "Apache-2.0",
                "source_url": (
                    "https://paddle-model-ecology.bj.bcebos.com/paddlex/"
                    "official_inference_model/paddle3.0.0/PP-OCRv5_mobile_det_infer.tar"
                ),
                "archive_size": 3,
                "archive_sha256": hashlib.sha256(b"tar").hexdigest(),
                "local_path": local_path,
                "tree_sha256": tree_sha256,
                "required_files": ["inference.json", "inference.pdiparams"],
            }
        ],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload))
    return path


def test_manifest_verifies_exact_local_tree_without_network(tmp_path: Path) -> None:
    model_dir = tmp_path / "models" / "detection"
    model_dir.mkdir(parents=True)
    (model_dir / "inference.json").write_text("{}")
    (model_dir / "inference.pdiparams").write_bytes(b"weights")
    digest = model_tree_sha256(model_dir)
    manifest_path = _write_manifest(tmp_path, tree_sha256=digest)

    attempts: list[object] = []
    original = socket.socket.connect

    def tracked_connect(self: socket.socket, address: object) -> None:
        attempts.append(address)
        original(self, address)  # pragma: no cover - the loader must never get here

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(socket.socket, "connect", tracked_connect)
        verified = load_and_verify_manifest(manifest_path, tmp_path / "models")

    assert verified.engine == "paddleocr"
    assert attempts == []


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("missing", "LOCAL_OCR_MODEL_MISSING"),
        ("mismatch", "LOCAL_OCR_MODEL_HASH_MISMATCH"),
        ("escape", "LOCAL_OCR_MODEL_PATH_INVALID"),
    ],
)
def test_manifest_fails_closed_with_stable_non_sensitive_codes(
    tmp_path: Path, mutation: str, expected_code: str
) -> None:
    model_dir = tmp_path / "models" / "detection"
    model_dir.mkdir(parents=True)
    (model_dir / "inference.json").write_text("{}")
    (model_dir / "inference.pdiparams").write_bytes(b"weights")
    digest = model_tree_sha256(model_dir)
    manifest_path = _write_manifest(
        tmp_path,
        tree_sha256="0" * 64 if mutation == "mismatch" else digest,
        local_path="../outside" if mutation == "escape" else "detection",
    )
    if mutation == "missing":
        (model_dir / "inference.pdiparams").unlink()

    with pytest.raises(LocalOcrError) as caught:
        load_and_verify_manifest(manifest_path, tmp_path / "models")

    assert caught.value.code == expected_code
    assert str(tmp_path) not in str(caught.value)


def test_runtime_network_guard_denies_dns_socket_and_http_primitives() -> None:
    with deny_outbound_network() as audit:
        with pytest.raises(LocalOcrError, match="LOCAL_OCR_NETWORK_ACCESS_DENIED"):
            socket.getaddrinfo("example.invalid", 443)
        with pytest.raises(LocalOcrError, match="LOCAL_OCR_NETWORK_ACCESS_DENIED"):
            socket.create_connection(("127.0.0.1", 9))

    assert audit.attempt_count == 2


def test_manifest_rejects_dot_as_model_root_with_stable_path_code(tmp_path: Path) -> None:
    manifest_path = _write_manifest(tmp_path, tree_sha256="0" * 64, local_path=".")

    with pytest.raises(LocalOcrError) as caught:
        load_and_verify_manifest(manifest_path, tmp_path / "models")

    assert caught.value.code == "LOCAL_OCR_MODEL_PATH_INVALID"


def test_bootstrap_supports_nested_model_destination(tmp_path: Path) -> None:
    source = tmp_path / "source" / "nested" / "detection"
    source.mkdir(parents=True)
    (source / "inference.json").write_text("{}")
    (source / "inference.pdiparams").write_bytes(b"weights")
    tree_digest = model_tree_sha256(source)
    archive_name = "PP-OCRv5_mobile_det_infer.tar"
    archives_root = tmp_path / "archives"
    archives_root.mkdir()
    archive = archives_root / archive_name
    with tarfile.open(archive, "w") as bundle:
        bundle.add(tmp_path / "source" / "nested", arcname="nested")
    payload = json.loads(
        _write_manifest(
            tmp_path,
            tree_sha256=tree_digest,
            local_path="nested/detection",
        ).read_text()
    )
    payload["artifacts"][0]["archive_size"] = archive.stat().st_size
    payload["artifacts"][0]["archive_sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
    manifest_path = tmp_path / "nested-manifest.json"
    manifest_path.write_text(json.dumps(payload))

    bootstrap(load_manifest(manifest_path), tmp_path / "models", archives_root)

    assert model_tree_sha256(tmp_path / "models" / "nested" / "detection") == tree_digest


def test_redirect_target_is_validated_before_following() -> None:
    _validate_download_url(
        "https://paddle-model-ecology.bj.bcebos.com/models/model.tar"
    )
    with pytest.raises(LocalOcrError) as caught:
        _validate_download_url("https://bj-gitea-online.cdn.bcebos.com/model.tar")

    assert caught.value.code == "LOCAL_OCR_MODEL_MANIFEST_INVALID"
