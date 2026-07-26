#!/usr/bin/env python3
"""Verify the Python server and the TypeScript client agree about command names.

Four command ids cross the process boundary between ``lsp.py`` and ``client.ts``. They are
matched by string at runtime, so a rename on one side compiles cleanly on both, ships, and
then fails as a panel that silently never populates — the worst failure shape available,
because nothing errors and the feature just looks broken.

This turns that into a CI failure. It also checks the reverse direction the VS Code manifest
cares about: every command declared in ``package.json`` must actually be registered in
``extension.ts``, or the palette offers an entry that throws when selected.

    python scripts/check_command_contract.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LSP = ROOT / "src" / "aurelius_ide" / "lsp.py"
CLIENT = ROOT / "editors" / "vscode" / "src" / "client.ts"
EXTENSION = ROOT / "editors" / "vscode" / "src" / "extension.ts"
MANIFEST = ROOT / "editors" / "vscode" / "package.json"

#: Registered on the client but intentionally absent from package.json — it takes arguments,
#: so surfacing it in the command palette would offer the user something that always throws.
INTERNAL_COMMANDS = {"aurelius.revealEntry"}


def server_commands() -> set[str]:
    """Command ids actually registered with ``@server.command(...)``."""
    source = LSP.read_text(encoding="utf-8")
    constants = dict(re.findall(r'^(\w+_COMMAND)\s*=\s*"([^"]+)"', source, re.M))
    registered = re.findall(r"@server\.command\((\w+)\)", source)
    missing = [name for name in registered if name not in constants]
    if missing:
        raise SystemExit(f"@server.command references undefined constants: {missing}")
    return {constants[name] for name in registered}


def client_commands() -> set[str]:
    """Command ids the extension sends, from the COMMANDS map in client.ts."""
    block = re.search(
        r"export const COMMANDS = \{(.*?)\} as const;", CLIENT.read_text(encoding="utf-8"), re.S
    )
    if block is None:
        raise SystemExit(f"No COMMANDS map found in {CLIENT}")
    return set(re.findall(r'"([^"]+)"', block.group(1)))


def main() -> int:
    failures: list[str] = []

    server = server_commands()
    client = client_commands()

    orphaned = client - server
    if orphaned:
        failures.append(
            "client.ts calls commands the server does not register: "
            + ", ".join(sorted(orphaned))
        )

    declared = {
        entry["command"]
        for entry in json.loads(MANIFEST.read_text(encoding="utf-8"))["contributes"]["commands"]
    }
    registered = set(
        re.findall(
            r'registerCommand\(\s*"(aurelius\.[\w.]+)"',
            EXTENSION.read_text(encoding="utf-8"),
        )
    )

    unregistered = declared - registered
    if unregistered:
        failures.append(
            "package.json declares commands extension.ts never registers: "
            + ", ".join(sorted(unregistered))
        )

    undeclared = registered - declared - INTERNAL_COMMANDS
    if undeclared:
        failures.append(
            "extension.ts registers commands package.json does not declare: "
            + ", ".join(sorted(undeclared))
        )

    if failures:
        for failure in failures:
            print(f"error: {failure}", file=sys.stderr)
        return 1

    print(f"command contract holds ({len(server)} server, {len(declared)} contributed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
