"""Deterministic local scan for credential-like material in tracked/worktree files."""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_EXTENSIONS = {
    ".env",
    ".example",
    ".ini",
    ".json",
    ".md",
    ".mjs",
    ".py",
    ".sh",
    ".toml",
    ".ts",
    ".tsx",
    ".yaml",
    ".yml",
}
TEXT_FILENAMES = {"Dockerfile", "Makefile"}
ASSIGNMENT = re.compile(
    r"""(?ix)
    (?:^|(?<=[\[\({,;]))\s*
    (?:[\"'](?P<quoted_key>[A-Za-z_][A-Za-z0-9_.-]*)[\"']|(?P<key>[A-Za-z_][A-Za-z0-9_.-]*))
    \s*(?:=|:)\s*['\"]?(?P<value>[^'\"\s,}#]+)
    """
)
URI_CREDENTIALS = re.compile(r"(?i)[a-z][a-z0-9+.-]*://[^\s:/@]+:([^\s/@?#]+)@")
KNOWN_PLACEHOLDER_VALUES = {"***", "local-placeholder-only"}
CREDENTIAL_KEY_PREFIXES = {"api", "private", "access", "auth", "secret"}
APPROVED_FIXTURES = {
    "backend/tests/integration/importers/test_spec_workbook_dry_run.py": (
        "c0799b0413f093b06de41d56f9c27b20e388cb2448ef55e39de6e78120dba801"
    )
}


def candidate_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [ROOT / item for item in result.stdout.splitlines()]


def is_approved_fixture(relative_path: str, content: str) -> bool:
    expected_digest = APPROVED_FIXTURES.get(relative_path)
    return expected_digest == hashlib.sha256(content.encode()).hexdigest()


def is_credential_key(key: str) -> bool:
    """Classify credential keys without treating arbitrary key-like words as secrets."""
    tokens = tuple(token for token in re.split(r"[._-]+", key.lower()) if token)
    return bool(tokens) and (
        tokens[-1] in {"password", "passwd", "secret", "token"}
        or (len(tokens) > 1 and tokens[-1] == "key" and tokens[-2] in CREDENTIAL_KEY_PREFIXES)
    )


def credential_finding(
    relative_path: str, number: int, line: str, *, approved_fixture: bool = False
) -> str | None:
    """Return one safe finding without echoing the candidate credential value."""
    if approved_fixture:
        return None
    assignment = ASSIGNMENT.search(line)
    if assignment:
        key = assignment.group("quoted_key") or assignment.group("key")
        value = assignment.group("value")
        if is_credential_key(key) and value not in KNOWN_PLACEHOLDER_VALUES:
            return f"{relative_path}:{number}: credential-like assignment"
    uri_credentials = URI_CREDENTIALS.search(line)
    if uri_credentials and uri_credentials.group(1) not in KNOWN_PLACEHOLDER_VALUES:
        return f"{relative_path}:{number}: credential-like URI authority"
    return None


def is_text_candidate(path: Path) -> bool:
    return path.name in TEXT_FILENAMES or path.suffix.lower() in TEXT_EXTENSIONS


def main() -> int:
    findings: list[str] = []
    for path in candidate_files():
        relative = path.relative_to(ROOT).as_posix()
        if not is_text_candidate(path) or not path.is_file():
            continue
        content = path.read_text(errors="replace")
        approved_fixture = is_approved_fixture(relative, content)
        for number, line in enumerate(content.splitlines(), start=1):
            finding = credential_finding(relative, number, line, approved_fixture=approved_fixture)
            if finding:
                findings.append(finding)
    if findings:
        print("\n".join(findings))
        return 1
    print("secret scan passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
