#!/usr/bin/env python3
"""Propagate the one canonical version to every place that asserts one.

Before this existed there were four sources of truth and they had already drifted:
``pyproject.toml`` said 0.1.0, the extension manifest said 0.2.0, ``lsp.py`` hardcoded
``SERVER_VERSION``, and the marketing site asserted a test count that was 23 tests stale.
Nothing caught any of it, because nothing was comparing them.

The canonical version now lives in exactly one place — ``__version__`` in
``src/aurelius_ide/__init__.py``. Everything else is derived:

    __init__.py  ──►  pyproject.toml           (hatchling reads it dynamically)
                 ──►  lsp.py SERVER_VERSION    (imports it at runtime)
                 ──►  editors/vscode/package.json
                 ──►  release-manifest.json    (consumed by the website)

Run with ``--check`` in CI. It exits non-zero if anything has drifted, which is the only
reason the guarantee holds — a sync script nobody runs is just a fifth source of truth.

    python scripts/sync_version.py            # rewrite derived files
    python scripts/sync_version.py --check    # verify, change nothing
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INIT = ROOT / "src" / "aurelius_ide" / "__init__.py"
EXTENSION_MANIFEST = ROOT / "editors" / "vscode" / "package.json"
MANIFEST = ROOT / "release-manifest.json"

_VERSION_RE = re.compile(r'^__version__\s*=\s*"([^"]+)"', re.M)
_PKG_VERSION_RE = re.compile(r'^(\s*"version"\s*:\s*)"[^"]*"', re.M)


class Drift(Exception):
    """A derived file disagrees with the canonical version."""


def canonical_version() -> str:
    match = _VERSION_RE.search(INIT.read_text(encoding="utf-8"))
    if not match:
        raise SystemExit(f"No __version__ found in {INIT}")
    return match.group(1)


def test_count() -> int:
    """Number of collected tests, so the website can stop asserting a stale figure."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    # `-q --collect-only` prints "path::test" lines, then a per-file summary. Counting the
    # summary lines is stable across pytest versions; counting dots is not.
    return sum(
        int(m.group(1))
        for m in re.finditer(r"^tests[/\\]\S+:\s*(\d+)$", result.stdout, re.M)
    )


def sync_extension(version: str, *, check: bool) -> list[str]:
    """Keep the extension in lockstep with the package. They ship together."""
    text = EXTENSION_MANIFEST.read_text(encoding="utf-8")
    current = json.loads(text)["version"]
    if current == version:
        return []
    if check:
        raise Drift(
            f"{EXTENSION_MANIFEST.relative_to(ROOT)} says {current}, expected {version}"
        )
    # Regex rather than json.dump: rewriting the whole file would reformat every line and
    # bury the one-character change in a 160-line diff.
    EXTENSION_MANIFEST.write_text(
        _PKG_VERSION_RE.sub(rf'\g<1>"{version}"', text, count=1), encoding="utf-8"
    )
    # ASCII only: this runs in CI on Windows, where the console is cp1252 and printing a
    # rightwards arrow raises UnicodeEncodeError. A sync script that crashes on its own
    # success message is worse than useless.
    return [f"extension {current} -> {version}"]


def sync_manifest(version: str, *, check: bool) -> list[str]:
    """Emit the facts the website is otherwise tempted to hardcode."""
    payload = {
        "version": version,
        "tests": test_count(),
        "indexes": ["OpenAlex", "Crossref", "arXiv", "Semantic Scholar"],
        "diagnosticCodes": _diagnostic_codes(),
        "repository": "https://github.com/vibhorxpandey/Aurelius-IDE",
        "license": "MIT",
    }
    rendered = json.dumps(payload, indent=2) + "\n"
    existing = MANIFEST.read_text(encoding="utf-8") if MANIFEST.exists() else ""
    if existing == rendered:
        return []
    if check:
        raise Drift(f"{MANIFEST.name} is stale — run scripts/sync_version.py")
    MANIFEST.write_text(rendered, encoding="utf-8")
    return [f"{MANIFEST.name} regenerated"]


def _diagnostic_codes() -> list[str]:
    source = (ROOT / "src" / "aurelius_ide" / "diagnostics.py").read_text(encoding="utf-8")
    return sorted(set(re.findall(r'"(AUR\d{3})"', source)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify without writing")
    args = parser.parse_args()

    version = canonical_version()
    try:
        changes = sync_extension(version, check=args.check) + sync_manifest(
            version, check=args.check
        )
    except Drift as drift:
        print(f"version drift: {drift}", file=sys.stderr)
        print("run: python scripts/sync_version.py", file=sys.stderr)
        return 1

    if args.check:
        print(f"in sync at {version}")
    elif changes:
        for change in changes:
            print(change)
    else:
        print(f"already in sync at {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
