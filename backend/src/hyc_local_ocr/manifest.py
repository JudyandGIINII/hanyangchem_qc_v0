from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from hyc_local_ocr.errors import LocalOcrError

SHA256_PATTERN = r"^[0-9a-f]{64}$"


class _ManifestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class ModelArtifact(_ManifestModel):
    role: Literal["text-detection", "text-recognition"]
    model: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")]
    version: Annotated[str, Field(min_length=1, max_length=64)]
    upstream: Literal["PaddlePaddle/PaddleOCR"]
    license: Literal["Apache-2.0"]
    source_url: Annotated[str, Field(min_length=1, max_length=512)]
    archive_size: Annotated[int, Field(gt=0)]
    archive_sha256: Annotated[str, Field(pattern=SHA256_PATTERN)]
    local_path: Annotated[str, Field(min_length=1, max_length=256)]
    tree_sha256: Annotated[str, Field(pattern=SHA256_PATTERN)]
    required_files: tuple[Annotated[str, Field(min_length=1, max_length=128)], ...]

    @field_validator("source_url")
    @classmethod
    def require_official_https_source(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "paddle-model-ecology.bj.bcebos.com"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("model source must be the credential-free official HTTPS origin")
        return value

    @field_validator("local_path")
    @classmethod
    def require_relative_local_path(cls, value: str) -> str:
        candidate = Path(value)
        if (
            candidate == Path(".")
            or candidate.is_absolute()
            or ".." in candidate.parts
            or value.startswith("~")
        ):
            raise ValueError("model local path must be a contained relative path")
        return value

    @field_validator("required_files", mode="before")
    @classmethod
    def freeze_required_files(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def validate_required_files(self) -> ModelArtifact:
        if not self.required_files or len(self.required_files) != len(set(self.required_files)):
            raise ValueError("model required files must be non-empty and unique")
        for value in self.required_files:
            candidate = Path(value)
            if candidate == Path(".") or candidate.is_absolute() or ".." in candidate.parts:
                raise ValueError("model required files must be contained relative paths")
        return self


class LocalOcrModelManifest(_ManifestModel):
    schema_version: Literal["hyc.local-ocr-model-manifest.v1"]
    engine: Literal["paddleocr"]
    engine_version: Literal["3.7.0"]
    runtime_version: Literal["3.3.1"]
    language: Literal["korean-english-numeric"]
    artifacts: tuple[ModelArtifact, ...]

    @field_validator("artifacts", mode="before")
    @classmethod
    def freeze_artifacts(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def require_unique_roles_and_paths(self) -> LocalOcrModelManifest:
        roles = tuple(item.role for item in self.artifacts)
        paths = tuple(item.local_path for item in self.artifacts)
        if not roles or len(roles) != len(set(roles)) or len(paths) != len(set(paths)):
            raise ValueError("model roles and local paths must be non-empty and unique")
        return self


def model_tree_sha256(model_dir: Path) -> str:
    if not model_dir.is_dir():
        raise LocalOcrError("LOCAL_OCR_MODEL_MISSING")
    digest = hashlib.sha256()
    files = sorted(path for path in model_dir.rglob("*") if path.is_file())
    if not files:
        raise LocalOcrError("LOCAL_OCR_MODEL_MISSING")
    for path in files:
        relative = path.relative_to(model_dir).as_posix()
        body = path.read_bytes()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(len(body)).encode("ascii"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(body).hexdigest().encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def load_manifest(manifest_path: Path) -> LocalOcrModelManifest:
    try:
        raw = json.loads(manifest_path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise LocalOcrError("LOCAL_OCR_MODEL_MANIFEST_INVALID") from error
    if isinstance(raw, dict) and raw.get("engine") not in (None, "paddleocr"):
        raise LocalOcrError("LOCAL_OCR_ENGINE_UNSUPPORTED")
    try:
        return LocalOcrModelManifest.model_validate(raw)
    except ValidationError as error:
        if any(
            validation_error.get("loc", ())[-1:] == ("local_path",)
            for validation_error in error.errors()
        ):
            raise LocalOcrError("LOCAL_OCR_MODEL_PATH_INVALID") from error
        raise LocalOcrError("LOCAL_OCR_MODEL_MANIFEST_INVALID") from error


def load_and_verify_manifest(manifest_path: Path, models_root: Path) -> LocalOcrModelManifest:
    manifest = load_manifest(manifest_path)
    root = models_root.resolve()
    for artifact in manifest.artifacts:
        model_dir = (root / artifact.local_path).resolve()
        if model_dir == root or root not in model_dir.parents:
            raise LocalOcrError("LOCAL_OCR_MODEL_PATH_INVALID")
        if not model_dir.is_dir():
            raise LocalOcrError("LOCAL_OCR_MODEL_MISSING")
        for required in artifact.required_files:
            candidate = (model_dir / required).resolve()
            if model_dir not in candidate.parents or not candidate.is_file():
                raise LocalOcrError("LOCAL_OCR_MODEL_MISSING")
        if model_tree_sha256(model_dir) != artifact.tree_sha256:
            raise LocalOcrError("LOCAL_OCR_MODEL_HASH_MISMATCH")
    return manifest


def manifest_binding_sha256(manifest: LocalOcrModelManifest) -> str:
    payload = manifest.model_dump(mode="json")
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
