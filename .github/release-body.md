## Install

Not yet on PyPI. Install from this tag:

```bash
pip install "aurelius-ide[all] @ git+https://github.com/vibhorxpandey/Aurelius-IDE"
```

The VS Code extension is attached below as a `.vsix`. Install it with
**Extensions → … → Install from VSIX**, or:

```bash
code --install-extension aurelius-ide-*.vsix
```

The extension needs the Python package on your machine — it is a thin client and the
analysis runs in the language server.

## Verify what you downloaded

`SHA256SUMS.txt` is attached. Build provenance is attested via GitHub, so you can check the
artifacts were built by this workflow from this commit:

```bash
gh attestation verify aurelius_ide-*.whl --repo vibhorxpandey/Aurelius-IDE
```

## Changes

See [CHANGELOG.md](https://github.com/vibhorxpandey/Aurelius-IDE/blob/main/CHANGELOG.md).
