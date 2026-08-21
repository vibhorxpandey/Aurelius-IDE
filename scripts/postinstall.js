#!/usr/bin/env node
'use strict';

/*
 * aurelius-ide's actual language server is pure Python (see pyproject.toml — the
 * analysis engine has zero required dependencies). This npm package exists only to
 * let `npm install aurelius-ide` bootstrap that Python package via pip, the same way
 * tools like esbuild/playwright bootstrap a non-JS runtime from postinstall.
 *
 * It does NOT reimplement anything — it shells out to pip. If pip fails because this
 * version isn't on PyPI yet (this project's release pipeline is new), it falls back to
 * installing straight from the GitHub tag, same as the manual instructions in README.md.
 */

const { spawnSync } = require('child_process');
const pkg = require('../package.json');

const VERSION = pkg.version;
const EXTRA = process.env.AURELIUS_IDE_SKIP_VERIFY ? 'lsp' : 'all';
const GIT_FALLBACK =
  'aurelius-ide[' + EXTRA + '] @ git+https://github.com/vibhorxpandey/Aurelius-IDE@v' + VERSION;

function findPython() {
  const candidates = process.platform === 'win32' ? ['py', 'python', 'python3'] : ['python3', 'python'];
  for (const cmd of candidates) {
    const probe = spawnSync(cmd, ['--version'], { encoding: 'utf8' });
    if (probe.error || probe.status !== 0) continue;
    const versionText = (probe.stdout || probe.stderr || '').trim();
    const match = versionText.match(/(\d+)\.(\d+)/);
    if (!match) continue;
    const [major, minor] = [Number(match[1]), Number(match[2])];
    if (major > 3 || (major === 3 && minor >= 10)) return cmd;
  }
  return null;
}

function pipInstall(python, spec) {
  const result = spawnSync(python, ['-m', 'pip', 'install', '--quiet', '--upgrade', spec], {
    stdio: 'inherit',
  });
  return result.status === 0;
}

function main() {
  if (process.env.AURELIUS_IDE_SKIP_POSTINSTALL) {
    console.log('[aurelius-ide] AURELIUS_IDE_SKIP_POSTINSTALL set — skipping the Python install.');
    return;
  }

  const python = findPython();
  if (!python) {
    console.error(
      '\n[aurelius-ide] No Python 3.10+ found on PATH (tried "python"/"python3"/"py").\n' +
        '[aurelius-ide] aurelius-lsp is a Python package — install Python 3.10+ and re-run\n' +
        '[aurelius-ide] `npm install aurelius-ide`, or install it directly yourself:\n' +
        `[aurelius-ide]   pip install "aurelius-ide[${EXTRA}]"\n`
    );
    process.exitCode = 1;
    return;
  }

  const pinnedSpec = `aurelius-ide[${EXTRA}]==${VERSION}`;
  console.log(`[aurelius-ide] Found Python at "${python}". Installing ${pinnedSpec}...`);

  if (pipInstall(python, pinnedSpec)) {
    console.log('[aurelius-ide] Done — the aurelius-lsp language server is installed.');
    return;
  }

  console.warn(
    `[aurelius-ide] "pip install ${pinnedSpec}" failed (this version may not be on PyPI yet).`
  );
  console.warn(`[aurelius-ide] Falling back to: pip install "${GIT_FALLBACK}"`);

  if (pipInstall(python, GIT_FALLBACK)) {
    console.log('[aurelius-ide] Done — installed from source.');
    return;
  }

  console.error(
    '\n[aurelius-ide] Could not install the Python package automatically. Install it yourself:\n' +
      `[aurelius-ide]   pip install "${GIT_FALLBACK}"\n`
  );
  process.exitCode = 1;
}

main();
