#!/usr/bin/env node
/**
 * Rebuilds `resources/python-embed/` — the embedded Python runtime a packaged Windows
 * build ships so a user with no Python installed at all can still run the app (see
 * `main/lspServer.ts::bundledPython`). Not checked into git: ~110 MB, entirely
 * reproducible from this script, and `resources/python-embed/` is gitignored.
 *
 * Ships aurelius-ide's own dependency-light `lsp` extra plus a real aurelius-mcp install,
 * so citation verification works out of the box too, not just structural diagnostics.
 * aurelius-ide isn't on PyPI yet (pre-Stage-4 in ARCHITECTURE.md's roadmap), so both
 * wheels are built from the local checkouts rather than downloaded.
 *
 * Windows-only, deliberately: this whole packaging effort targets a portable .exe for a
 * Windows machine with nothing installed, not a cross-platform release.
 */
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, rmSync, writeFileSync, readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const DESKTOP_DIR = dirname(dirname(fileURLToPath(import.meta.url)));
const BUILD_TOOLS = join(DESKTOP_DIR, "build-tools");
const EMBED_DIR = join(DESKTOP_DIR, "resources", "python-embed");
const REPO_ROOT = dirname(dirname(DESKTOP_DIR));

const PYTHON_VERSION = "3.11.9";
const PYTHON_ZIP_URL = `https://www.python.org/ftp/python/${PYTHON_VERSION}/python-${PYTHON_VERSION}-embed-amd64.zip`;
const GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py";

// AURELIUS_MCP_SOURCE lets a contributor without this exact checkout layout point at
// their own aurelius-mcp clone, or fall back to PyPI once aurelius-mcp's on_step release
// (>=0.7.0) is actually published there. No reliable convention ties the two repos'
// locations together, so this is a real machine-specific default, not a sibling-dir guess.
const AURELIUS_MCP_SOURCE =
  process.env.AURELIUS_MCP_SOURCE ??
  join(process.env.USERPROFILE ?? "", "Documents", "GitHub", "Aurelius");

function run(cmd, args, opts = {}) {
  console.log(`$ ${cmd} ${args.join(" ")}`);
  execFileSync(cmd, args, { stdio: "inherit", ...opts });
}

async function download(url, dest) {
  console.log(`downloading ${url}`);
  const res = await fetch(url);
  if (!res.ok) throw new Error(`GET ${url} -> ${res.status}`);
  writeFileSync(dest, Buffer.from(await res.arrayBuffer()));
}

async function main() {
  if (process.platform !== "win32") {
    console.error("bundle-python.mjs only supports Windows (the packaged build target).");
    process.exit(1);
  }

  mkdirSync(BUILD_TOOLS, { recursive: true });
  rmSync(EMBED_DIR, { recursive: true, force: true });
  mkdirSync(EMBED_DIR, { recursive: true });

  const zipPath = join(BUILD_TOOLS, "python-embed.zip");
  if (!existsSync(zipPath)) await download(PYTHON_ZIP_URL, zipPath);
  run("powershell", [
    "-NoProfile", "-Command",
    `Expand-Archive -Path '${zipPath}' -DestinationPath '${EMBED_DIR}' -Force`,
  ]);

  // The embeddable distribution disables site-packages by default (its ._pth file
  // comments out `import site`) — without this, pip-installed packages are invisible.
  // Idempotent: a `._pth` that's already uncommented has no "#import site" to replace.
  const pthPath = join(EMBED_DIR, "python311._pth");
  writeFileSync(pthPath, readFileSync(pthPath, "utf-8").replace("#import site", "import site"));

  const python = join(EMBED_DIR, "python.exe");
  const getPipPath = join(BUILD_TOOLS, "get-pip.py");
  if (!existsSync(getPipPath)) await download(GET_PIP_URL, getPipPath);
  run(python, [getPipPath, "--no-warn-script-location"]);

  // aurelius-ide isn't published, and pip inside an embeddable distribution can't create
  // the isolated build environment PEP 517 needs (no working `venv`) — so both packages
  // are pre-built into wheels with the *host* Python (which has real build tooling) and
  // installed as wheels here, which needs no build backend at all.
  const wheelsDir = join(BUILD_TOOLS, "wheels");
  rmSync(wheelsDir, { recursive: true, force: true });
  mkdirSync(wheelsDir, { recursive: true });
  run("python", ["-m", "pip", "install", "--quiet", "build"]);
  run("python", ["-m", "build", "--wheel", "--outdir", wheelsDir, REPO_ROOT]);
  if (!existsSync(AURELIUS_MCP_SOURCE)) {
    throw new Error(
      `aurelius-mcp source not found at ${AURELIUS_MCP_SOURCE}. Set AURELIUS_MCP_SOURCE, ` +
        "or wait for aurelius-mcp>=0.7.0 to land on PyPI and switch this script to install " +
        "it by name instead."
    );
  }
  run("python", ["-m", "build", "--wheel", "--outdir", wheelsDir, AURELIUS_MCP_SOURCE]);

  const { readdirSync } = await import("node:fs");
  const wheelFile = (prefix) => {
    const found = readdirSync(wheelsDir).find((f) => f.startsWith(prefix));
    if (!found) throw new Error(`no wheel matching ${prefix}* in ${wheelsDir}`);
    return join(wheelsDir, found);
  };

  run(python, [
    "-m", "pip", "install", "--no-warn-script-location",
    `${wheelFile("aurelius_ide-")}[lsp]`,
    wheelFile("aurelius_mcp-"),
  ]);

  run(python, [
    "-c",
    "import aurelius_ide, aurelius, pygls; " +
      "print('aurelius_ide', aurelius_ide.__version__); " +
      "print('aurelius-mcp', aurelius.__version__)",
  ]);

  console.log(`\nresources/python-embed/ ready.`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
