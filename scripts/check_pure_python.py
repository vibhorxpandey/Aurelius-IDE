#!/usr/bin/env python3
"""Assert Aurelius's own dependency closure contains no compiled extension modules.

Shipping an embedded Python runtime inside a desktop app is cheap only while every
dependency is pure Python: one set of files works on every OS and architecture, with no
manylinux, universal2 or musl variants to build and test. Today that holds — stdlib plus
pygls, lsprotocol, attrs and cattrs, all pure.

The day something pulls in a compiled module, packaging stops being a two-week job. Nobody
notices at the time; they notice months later at the packaging stage. This fails at the
moment the dependency is added.

It walks the *declared dependency closure* of ``aurelius-ide`` rather than everything
installed, because a developer's environment routinely contains numpy, torch and friends
that have nothing to do with this project.

    pip install -e ".[lsp]"
    python scripts/check_pure_python.py [--extra lsp --extra verify]
"""
from __future__ import annotations

import argparse
import importlib.metadata as metadata
import re
import sys

ROOT_PACKAGE = "aurelius-ide"

NATIVE_SUFFIXES = (".so", ".pyd", ".dylib")

# Requirement strings carry full PEP 508 markers — `extra == "verify"`, but also
# `python_version < "3.11"` and `sys_platform == "win32"`. Evaluating only the extras marker
# made this script demand `exceptiongroup` on Python 3.14, where it is correctly absent.
#
# `packaging` is not guaranteed: it rides along with pytest and build, so it is present in a
# dev environment but not after a bare `pip install -e ".[lsp]"`. The GitHub Windows runner
# image happens to ship it and the Linux and macOS ones do not, which is how this passed on
# one platform and crashed on the other two.
try:
    from packaging.requirements import Requirement  # noqa: E402
except ModuleNotFoundError:  # pragma: no cover - environment-dependent
    print(
        "error: this check needs `packaging` to evaluate dependency markers.\n"
        "       pip install packaging",
        file=sys.stderr,
    )
    raise SystemExit(1) from None


def normalise(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def applies(requirement: Requirement, extras: set[str]) -> bool:
    """True if this requirement is actually installed in this environment for these extras."""
    if requirement.marker is None:
        return True
    # A requirement gated on any extra is evaluated once per requested extra; one match is
    # enough. Requirements with non-extra markers are evaluated against the environment.
    if "extra" in str(requirement.marker):
        return any(requirement.marker.evaluate({"extra": extra}) for extra in extras)
    return requirement.marker.evaluate()


def closure(root: str, extras: set[str]) -> tuple[set[str], set[str]]:
    """Distributions reachable from ``root``, split into (installed, missing).

    Missing ones are reported rather than skipped: a dependency that is declared but not
    installed cannot be inspected, so treating its absence as "pure" would turn this check
    into a false pass — which is exactly what it did on the first run.
    """
    seen: set[str] = set()
    missing: set[str] = set()
    queue = [(normalise(root), extras)]

    while queue:
        name, active_extras = queue.pop()
        if name in seen or name in missing:
            continue
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            missing.add(name)
            continue
        seen.add(name)

        for raw in dist.requires or []:
            try:
                requirement = Requirement(raw)
            except Exception:
                continue
            if not applies(requirement, active_extras):
                continue
            # A child's own extras are only pulled in when the parent asked for them.
            queue.append((normalise(requirement.name), set(requirement.extras)))
    return seen - {normalise(root)}, missing


def native_files(name: str) -> list[str]:
    try:
        dist = metadata.distribution(name)
    except metadata.PackageNotFoundError:
        return []
    return [str(f) for f in (dist.files or []) if str(f).endswith(NATIVE_SUFFIXES)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--extra",
        action="append",
        default=None,
        help="extras to include (default: lsp — what the desktop bundle ships)",
    )
    args = parser.parse_args()
    # Only `lsp` by default, because only `lsp` goes inside the bundled runtime. `verify`
    # is deliberately excluded: aurelius-mcp pulls pydantic-core and rpds-py, both compiled
    # Rust. See the note at the bottom of this file.
    extras = set(args.extra or ["lsp"])

    try:
        metadata.distribution(ROOT_PACKAGE)
    except metadata.PackageNotFoundError:
        print(
            f"error: {ROOT_PACKAGE} is not installed. Run: pip install -e \".[lsp]\"",
            file=sys.stderr,
        )
        return 1

    installed, missing = closure(ROOT_PACKAGE, extras)
    dependencies = sorted(installed)

    if missing:
        print(
            "error: these declared dependencies are not installed, so they cannot be "
            "inspected:",
            file=sys.stderr,
        )
        for name in sorted(missing):
            print(f"  {name}", file=sys.stderr)
        print(
            f'\nInstall them first: pip install -e ".[{",".join(sorted(extras))}]"',
            file=sys.stderr,
        )
        return 1

    impure = {name: files for name in dependencies if (files := native_files(name))}

    if impure:
        print("error: Aurelius's dependency tree is no longer pure Python.", file=sys.stderr)
        print(
            "Single-runtime packaging breaks — every OS/arch now needs its own build.",
            file=sys.stderr,
        )
        for name, files in sorted(impure.items()):
            print(f"  {name}: {', '.join(files[:4])}", file=sys.stderr)
        print(
            "\nIf the dependency is genuinely required, desktop packaging grows by weeks. "
            "Decide deliberately, then update this check.",
            file=sys.stderr,
        )
        return 1

    listed = ", ".join(dependencies) if dependencies else "none installed"
    print(f"pure Python: {ROOT_PACKAGE} + extras {sorted(extras)}")
    print(f"  closure ({len(dependencies)}): {listed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# A finding worth recording, because it contradicts an assumption that was nearly baked
# into the packaging plan:
#
#   pip install -e ".[lsp]"      -> pure Python (pygls, lsprotocol, cattrs, attrs)
#   pip install -e ".[verify]"   -> NOT pure. aurelius-mcp pulls pydantic-core and rpds-py,
#                                   both compiled Rust, plus pywin32 on Windows.
#
# So the embedded runtime in the desktop app ships the `lsp` extra only. That is not a
# compromise: without `verify`, structural analysis, literature search (OpenAlexSearcher is
# stdlib urllib) and the compile gate all still work, and scholarly verification degrades to
# NullVerifier, which reports inconclusive and emits nothing. Users who want the full
# verification chain install `aurelius-mcp` themselves, into their own Python.
#
# If that ever becomes unacceptable, the alternative is running aurelius-mcp out of process
# rather than inside the bundle — not adding compiled wheels to the bundled runtime.
