"""The compile gate — the check that makes "arXiv-ready" a verified claim.

Every other analyzer here reasons about the source. None of them can tell you the paper
*builds*. That gap matters at exactly one moment, submission, and it is where the
expensive failures live: an undefined reference that renders as ``[?]``, a missing figure
file, a stray ``\\end{itemize}``, a BibTeX entry the style file rejects. All of them
survive a clean lint and none of them survive a reviewer.

So this module runs the real toolchain — ``pdflatex``, ``bibtex``, ``pdflatex`` twice more
— and turns its output into the same :class:`~aurelius_ide.diagnostics.Diagnostic` objects
everything else produces. The two-pass repetition is not superstition: reference numbers
land in the ``.aux`` on one pass and are read back on the next, so undefined-reference
warnings are only trustworthy after the third run.

**Why this is not an analyzer.** ``BaseAnalyzer`` promises a pure function of a parsed
document, and the engine's two phases are "instant" and "network". A compile is neither:
it costs seconds, it needs a real file on a real disk rather than an editor buffer, and it
writes half a dozen artefacts next to the paper. Wiring it into the keystroke path would
mean recompiling a document while it is being typed, which is both useless and hostile.
It is a gate — you call it from CI, a pre-submission hook, or an explicit editor command.

**Why the runner is injected.** Tests may not touch the network and must not require a
TeX installation, so :class:`CompileRunner` is a protocol and the tests pass a stub that
replays canned log text. That also buys the container story for free: running the same
commands inside Docker is a different runner, not a different code path.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Protocol, Sequence, runtime_checkable

from .diagnostics import Code, Diagnostic, Severity
from .document import PositionIndex

#: pdflatex, then bibtex, then pdflatex twice. See the module docstring for why three
#: LaTeX passes rather than one.
DEFAULT_PASSES = ("latex", "bibtex", "latex", "latex")

DEFAULT_TIMEOUT_SECONDS = 120


@dataclass
class CompileOutcome:
    """Raw result of running the toolchain. Parsing happens separately."""

    log: str = ""
    blg: str = ""
    returncode: int = 0
    #: Set when the toolchain could not be run at all — no binary, timeout, no Docker.
    #: Distinct from a non-zero return code, which means LaTeX ran and rejected the paper.
    unavailable: Optional[str] = None
    commands: List[List[str]] = field(default_factory=list)


@runtime_checkable
class CompileRunner(Protocol):
    """Executes a LaTeX toolchain over a directory and returns its logs."""

    name: str

    def run(self, tex_path: Path, workdir: Path) -> CompileOutcome:
        ...


class SubprocessRunner:
    """Runs a locally installed TeX distribution.

    ``latexmk`` would handle the pass sequencing itself, but it is not always present and
    its absence should degrade to plain ``pdflatex`` rather than to no gate at all.
    """

    name = "subprocess"

    def __init__(
        self,
        latex: str = "pdflatex",
        bibtex: str = "bibtex",
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        passes: Sequence[str] = DEFAULT_PASSES,
    ) -> None:
        self.latex = latex
        self.bibtex = bibtex
        self.timeout = timeout
        self.passes = tuple(passes)

    @property
    def available(self) -> bool:
        return shutil.which(self.latex) is not None

    def _command(self, step: str, stem: str, workdir: Path) -> List[str]:
        if step == "bibtex":
            return [self.bibtex, stem]
        # -interaction=nonstopmode keeps a syntax error from parking the process on a "?"
        # prompt forever; without it a CI run hangs until the timeout. -halt-on-error is
        # deliberately absent — a gate should report every error in one run, not make the
        # author recompile once per mistake.
        return [
            self.latex,
            "-interaction=nonstopmode",
            "-file-line-error",
            stem + ".tex",
        ]

    def run(self, tex_path: Path, workdir: Path) -> CompileOutcome:
        if not self.available:
            return CompileOutcome(
                unavailable=f"'{self.latex}' is not on PATH; install a TeX distribution."
            )

        stem = tex_path.stem
        outcome = CompileOutcome()
        for step in self.passes:
            command = self._command(step, stem, workdir)
            outcome.commands.append(command)
            try:
                completed = subprocess.run(
                    command,
                    cwd=str(workdir),
                    capture_output=True,
                    text=True,
                    errors="replace",
                    timeout=self.timeout,
                )
            except FileNotFoundError:
                # bibtex missing is survivable — the paper may not use it at all.
                if step == "bibtex":
                    continue
                return CompileOutcome(unavailable=f"'{command[0]}' is not installed.")
            except subprocess.TimeoutExpired:
                return CompileOutcome(
                    unavailable=f"'{command[0]}' exceeded {self.timeout}s and was stopped."
                )
            if step != "bibtex":
                outcome.returncode = completed.returncode

        outcome.log = _read(workdir / (stem + ".log"))
        outcome.blg = _read(workdir / (stem + ".blg"))
        return outcome


class DockerRunner(SubprocessRunner):
    """Runs the same toolchain inside a container.

    The point is reproducibility: "it compiles on my machine" is not what a submission
    gate should certify, and a pinned image makes the answer the same everywhere. The
    workdir is bind-mounted, so artefacts land beside the paper exactly as they would
    locally.
    """

    name = "docker"

    def __init__(self, image: str = "texlive/texlive:latest", docker: str = "docker", **kwargs):
        super().__init__(**kwargs)
        self.image = image
        self.docker = docker

    @property
    def available(self) -> bool:
        return shutil.which(self.docker) is not None

    def _command(self, step: str, stem: str, workdir: Path) -> List[str]:
        inner = super()._command(step, stem, workdir)
        return [
            self.docker, "run", "--rm",
            "--network", "none",  # a compile has no business reaching the internet
            "-v", f"{workdir.resolve()}:/work",
            "-w", "/work",
            self.image,
            *inner,
        ]

    def run(self, tex_path: Path, workdir: Path) -> CompileOutcome:
        if not self.available:
            return CompileOutcome(unavailable=f"'{self.docker}' is not on PATH.")
        return super().run(tex_path, workdir)


class UnavailableRunner:
    """Stands in when no toolchain is configured. Always inconclusive, never a finding."""

    name = "unavailable"

    def __init__(self, reason: str = "No LaTeX toolchain configured.") -> None:
        self.reason = reason

    def run(self, tex_path: Path, workdir: Path) -> CompileOutcome:
        return CompileOutcome(unavailable=self.reason)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


# --------------------------------------------------------------------------------------
# Log parsing
# --------------------------------------------------------------------------------------

#: ``-file-line-error`` gives ``./paper.tex:42: Undefined control sequence.``, which is the
#: only log format that reliably carries a line number. The bare ``! ...`` form is the
#: fallback and its line, if any, arrives later on an ``l.42`` continuation line.
#:
#: The filename must end in a TeX-ish extension. Anchoring on that rather than on "no
#: colons" is what lets a Windows path (``C:\papers\paper.tex:42:``) match, and it stops
#: the pattern from claiming unrelated log lines that happen to contain ``word:12:``.
_FILE_LINE_ERROR_RE = re.compile(
    r"^(?P<file>.*?\.(?:tex|sty|cls|ltx|def|cfg)):(?P<line>\d+):\s*(?P<message>.+)$", re.M
)

#: A ``file:line:`` entry that is merely informational. pdfTeX prints genuine errors in
#: that format with no marker at all ("Undefined control sequence."), so warnings have to
#: be excluded by name rather than errors detected by one.
_FILE_LINE_NOISE_RE = re.compile(r"\b(?:Warning|Info)\b", re.IGNORECASE)
_BARE_ERROR_RE = re.compile(r"^!\s*(?P<message>.+)$", re.M)
_LINE_HINT_RE = re.compile(r"^l\.(?P<line>\d+)", re.M)

_UNDEFINED_REF_RE = re.compile(
    r"Warning:\s*(?P<kind>Citation|Reference)\s*[`'\"]?(?P<key>[^'\"\s]+?)['\"]?\s+"
    r"(?:on page \d+\s+)?undefined",
    re.IGNORECASE,
)
_RERUN_RE = re.compile(r"(?:Label\(s\) may have changed|Rerun to get)", re.IGNORECASE)
_BIBTEX_ERROR_RE = re.compile(
    r"^(?:I couldn't open|I was expecting|Warning--)(?P<message>.*)$", re.M
)

#: Noise every real document produces. Reporting these trains authors to ignore the gate,
#: which is the same failure mode the claim analyzer is built to avoid.
_IGNORABLE = re.compile(
    r"(?:Overfull|Underfull|\\hbox|\\vbox|Font Warning|Package caption Warning|"
    r"has changed|Some font shapes|Loading|LaTeX Font)",
    re.IGNORECASE,
)


@dataclass
class CompileGate:
    """Compiles a paper and reports what the toolchain said about it.

    ``runner`` defaults to a local TeX installation. Pass :class:`DockerRunner` for a
    reproducible build, or any object satisfying :class:`CompileRunner` in tests.
    """

    runner: CompileRunner = field(default_factory=SubprocessRunner)
    #: Keep the build directory instead of deleting it — useful when debugging a gate
    #: failure that does not reproduce by hand.
    keep_artifacts: bool = False

    def check(
        self,
        tex_path: Path,
        bib_path: Optional[Path] = None,
        source: Optional[str] = None,
    ) -> List[Diagnostic]:
        """Compile ``tex_path`` and return diagnostics anchored in it.

        ``source`` overrides the file's contents, so an editor can gate on the unsaved
        buffer rather than on what is last written to disk.
        """
        tex_path = Path(tex_path)
        text = source if source is not None else _read(tex_path)
        outcome = self._compile(tex_path, bib_path, text)

        # A toolchain we could not run tells us nothing about the paper. Reporting that
        # as a compile failure is the same error as reporting a dropped connection as a
        # fabricated citation, and it is just as alarming to be wrong about.
        if outcome.unavailable:
            return []

        return parse_log(outcome, text)

    def available(self) -> bool:
        return bool(getattr(self.runner, "available", True))

    def _compile(self, tex_path: Path, bib_path: Optional[Path], text: str) -> CompileOutcome:
        """Build in a scratch directory so the author's folder stays free of artefacts."""
        parent = tempfile.mkdtemp(prefix="aurelius-compile-")
        workdir = Path(parent)
        try:
            staged = workdir / tex_path.name
            staged.write_text(text, encoding="utf-8")
            _stage_siblings(tex_path, workdir, skip=tex_path.name)
            if bib_path and Path(bib_path).is_file():
                shutil.copy2(bib_path, workdir / Path(bib_path).name)
            return self.runner.run(staged, workdir)
        except OSError as exc:
            return CompileOutcome(unavailable=f"Could not stage the build: {exc}")
        finally:
            if not self.keep_artifacts:
                shutil.rmtree(parent, ignore_errors=True)


#: Copied alongside the paper so figures and style files resolve. Deliberately excludes
#: build artefacts, which would otherwise let a stale .aux mask a real error.
_STAGED_SUFFIXES = frozenset(
    {".bib", ".bst", ".sty", ".cls", ".tex", ".pdf", ".png", ".jpg", ".jpeg", ".eps", ".svg"}
)


def _stage_siblings(tex_path: Path, workdir: Path, skip: str) -> None:
    source_dir = tex_path.parent
    if not source_dir.is_dir():
        return
    for entry in source_dir.iterdir():
        if entry.name == skip or not entry.is_file():
            continue
        if entry.suffix.lower() in _STAGED_SUFFIXES:
            try:
                shutil.copy2(entry, workdir / entry.name)
            except OSError:
                continue


def parse_log(outcome: CompileOutcome, text: str) -> List[Diagnostic]:
    """Turn toolchain logs into diagnostics anchored in the ``.tex``.

    Exposed separately from :class:`CompileGate` because it is the part worth testing
    exhaustively, and it needs no toolchain to test.
    """
    index = PositionIndex(text)
    line_starts = _line_start_offsets(text)
    out: List[Diagnostic] = []
    seen: set = set()

    def add(line_no: Optional[int], message: str, severity: Severity, code: str, data: Dict):
        message = message.strip()
        if not message or _IGNORABLE.search(message):
            return
        key = (line_no, message)
        if key in seen:
            return
        seen.add(key)
        start, end = _span_for_line(line_starts, text, line_no)
        out.append(
            Diagnostic(
                range=index.range(start, end),
                message=message,
                severity=severity,
                code=code,
                data=data,
            )
        )

    log = outcome.log

    for m in _FILE_LINE_ERROR_RE.finditer(log):
        message = m.group("message")
        if _FILE_LINE_NOISE_RE.search(message):
            continue
        add(
            int(m.group("line")),
            message.lstrip("! ").strip(),
            Severity.ERROR,
            Code.COMPILE_ERROR,
            {"file": m.group("file"), "source": "latex"},
        )

    # Errors the file:line format missed — take the nearest following "l.NNN" as the line.
    for m in _BARE_ERROR_RE.finditer(log):
        hint = _LINE_HINT_RE.search(log, m.end(), m.end() + 800)
        add(
            int(hint.group("line")) if hint else None,
            m.group("message"),
            Severity.ERROR,
            Code.COMPILE_ERROR,
            {"source": "latex"},
        )

    for m in _UNDEFINED_REF_RE.finditer(log):
        kind = m.group("kind").lower()
        key = m.group("key")
        add(
            _find_line(text, key),
            f"{m.group('kind')} '{key}' is undefined — it will render as [?] in the PDF.",
            Severity.ERROR if kind == "citation" else Severity.WARNING,
            Code.COMPILE_ERROR if kind == "citation" else Code.COMPILE_WARNING,
            {"key": key, "kind": kind, "source": "latex"},
        )

    if _RERUN_RE.search(log):
        add(
            None,
            "Labels changed on the final pass — cross-references may be stale.",
            Severity.WARNING,
            Code.COMPILE_WARNING,
            {"source": "latex"},
        )

    for m in _BIBTEX_ERROR_RE.finditer(outcome.blg):
        add(
            None,
            "BibTeX: " + m.group(0).replace("Warning--", "").strip(),
            Severity.WARNING,
            Code.COMPILE_WARNING,
            {"source": "bibtex"},
        )

    return out


def _line_start_offsets(text: str) -> List[int]:
    starts = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            starts.append(i + 1)
    return starts


def _span_for_line(line_starts: List[int], text: str, line_no: Optional[int]):
    """Offsets covering a 1-indexed log line, or the first line when it is unknown."""
    if not line_no or line_no < 1 or line_no > len(line_starts):
        first_end = text.find("\n")
        return 0, (len(text) if first_end == -1 else first_end)
    start = line_starts[line_no - 1]
    end = text.find("\n", start)
    return start, (len(text) if end == -1 else end)


def _find_line(text: str, key: str) -> Optional[int]:
    """1-indexed line of the first ``\\cite``/``\\ref`` mentioning ``key``.

    The log reports undefined citations without a line number, so we locate the offending
    site ourselves rather than dumping every one of them onto line 1.
    """
    pattern = re.compile(r"\\(?:cite|nocite|ref|eqref|autoref)[a-zA-Z]*(?:\[[^\]]*\])*\{[^}]*\b"
                         + re.escape(key) + r"\b[^}]*\}")
    match = pattern.search(text)
    if match is None:
        return None
    return text.count("\n", 0, match.start()) + 1


def default_gate() -> CompileGate:
    """A gate honouring ``AURELIUS_LATEX_DOCKER_IMAGE`` / ``AURELIUS_LATEX``.

    Environment-driven rather than argument-driven because the thing that varies is the
    machine, not the call site: the same CI config should work on a runner with TeX Live
    installed and on one that only has Docker.
    """
    image = os.environ.get("AURELIUS_LATEX_DOCKER_IMAGE")
    if image:
        return CompileGate(runner=DockerRunner(image=image))
    runner = SubprocessRunner(latex=os.environ.get("AURELIUS_LATEX", "pdflatex"))
    return CompileGate(runner=runner if runner.available else UnavailableRunner())
