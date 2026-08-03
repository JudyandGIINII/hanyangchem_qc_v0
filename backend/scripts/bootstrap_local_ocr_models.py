from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND / "src"))

from hyc_local_ocr.errors import LocalOcrError  # noqa: E402
from hyc_local_ocr.manifest import (  # noqa: E402
    LocalOcrModelManifest,
    load_and_verify_manifest,
    load_manifest,
    model_tree_sha256,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_download_url(url: str) -> None:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "paddle-model-ecology.bj.bcebos.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise LocalOcrError("LOCAL_OCR_MODEL_MANIFEST_INVALID")


class _ValidatedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        request: urllib.request.Request,
        file_pointer: object,
        code: int,
        message: str,
        headers: object,
        new_url: str,
    ) -> urllib.request.Request | None:
        _validate_download_url(new_url)
        return super().redirect_request(
            request, file_pointer, code, message, headers, new_url  # type: ignore[arg-type]
        )


def _download(url: str, destination: Path) -> None:
    _validate_download_url(url)
    request = urllib.request.Request(url, headers={"User-Agent": "hyc-local-ocr-bootstrap/1"})
    opener = urllib.request.build_opener(_ValidatedRedirectHandler())
    with opener.open(request, timeout=120) as response, destination.open("wb") as target:
        _validate_download_url(response.geturl())
        shutil.copyfileobj(response, target, length=1024 * 1024)


def _safe_extract(archive: Path, destination: Path) -> None:
    destination_resolved = destination.resolve()
    with tarfile.open(archive, mode="r:") as bundle:
        for member in bundle.getmembers():
            target = (destination / member.name).resolve()
            if target != destination_resolved and destination_resolved not in target.parents:
                raise LocalOcrError("LOCAL_OCR_MODEL_PATH_INVALID")
            if member.issym() or member.islnk() or member.isdev():
                raise LocalOcrError("LOCAL_OCR_MODEL_MANIFEST_INVALID")
        bundle.extractall(destination, filter="data")


def bootstrap(
    manifest: LocalOcrModelManifest, models_root: Path, archives_root: Path
) -> None:
    models_root.mkdir(parents=True, exist_ok=True)
    archives_root.mkdir(parents=True, exist_ok=True)
    for artifact in manifest.artifacts:
        final_model = models_root / artifact.local_path
        if final_model.exists():
            if model_tree_sha256(final_model) != artifact.tree_sha256:
                raise LocalOcrError("LOCAL_OCR_MODEL_HASH_MISMATCH")
            continue
        archive_name = Path(urlsplit(artifact.source_url).path).name
        archive = archives_root / archive_name
        if not archive.is_file() or archive.stat().st_size != artifact.archive_size:
            temporary_archive = archives_root / f".{archive_name}.partial"
            if temporary_archive.exists():
                temporary_archive.unlink()
            _download(artifact.source_url, temporary_archive)
            os.replace(temporary_archive, archive)
        if archive.stat().st_size != artifact.archive_size or _sha256(archive) != (
            artifact.archive_sha256
        ):
            raise LocalOcrError("LOCAL_OCR_MODEL_HASH_MISMATCH")
        temporary_root = Path(tempfile.mkdtemp(prefix="hyc-local-ocr-", dir=models_root))
        try:
            _safe_extract(archive, temporary_root)
            extracted = temporary_root / artifact.local_path
            if model_tree_sha256(extracted) != artifact.tree_sha256:
                raise LocalOcrError("LOCAL_OCR_MODEL_HASH_MISMATCH")
            final_model.parent.mkdir(parents=True, exist_ok=True)
            os.replace(extracted, final_model)
        finally:
            shutil.rmtree(temporary_root, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Explicit setup-only download of pinned official local OCR models"
    )
    parser.add_argument(
        "--manifest", type=Path, default=BACKEND / "local_ocr/model-manifest.v1.json"
    )
    parser.add_argument("--models-root", type=Path, required=True)
    parser.add_argument("--archives-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = load_manifest(args.manifest)
        bootstrap(manifest, args.models_root, args.archives_root)
        verified = load_and_verify_manifest(args.manifest, args.models_root)
    except LocalOcrError as error:
        print(error.code)
        return 2
    for artifact in verified.artifacts:
        print(
            "local-ocr-bootstrap: "
            f"role={artifact.role} archive_size={artifact.archive_size} "
            f"archive_sha256={artifact.archive_sha256} tree_sha256={artifact.tree_sha256}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
