"""The compile gate.

No test here runs LaTeX. :class:`StubRunner` replays log text captured from real
``pdflatex`` output, which keeps the suite hermetic and fast while still exercising the
part that actually has logic in it — the log parser. The runners themselves are tested
only for the decisions they make *before* spawning anything.
"""
from __future__ import annotations

from pathlib import Path

from aurelius_ide.compiling import (
    CompileGate,
    CompileOutcome,
    DockerRunner,
    SubprocessRunner,
    UnavailableRunner,
    parse_log,
)
from aurelius_ide.diagnostics import Code, Severity

PAPER = """\\documentclass{article}
\\begin{document}
\\section{Introduction}
Prior work \\cite{ghost2030} established the baseline.
We reference \\ref{fig:missing} here.
\\undefinedmacro
\\end{document}
"""


class StubRunner:
    """Replays canned toolchain output. Never spawns a process."""

    name = "stub"

    def __init__(self, log: str = "", blg: str = "", returncode: int = 0, unavailable=None):
        self.outcome = CompileOutcome(
            log=log, blg=blg, returncode=returncode, unavailable=unavailable
        )
        self.calls = 0

    def run(self, tex_path: Path, workdir: Path) -> CompileOutcome:
        self.calls += 1
        return self.outcome


# -- log parsing -------------------------------------------------------------------------


def test_file_line_error_is_anchored_to_its_line():
    log = "./paper.tex:6: Undefined control sequence.\nl.6 \\undefinedmacro\n"
    diags = parse_log(CompileOutcome(log=log), PAPER)
    errors = [d for d in diags if d.severity is Severity.ERROR]
    assert errors
    assert errors[0].code == Code.COMPILE_ERROR
    assert errors[0].range.start.line == 5  # 1-indexed log line 6 -> 0-indexed 5


def test_undefined_citation_points_at_the_cite_site():
    log = "LaTeX Warning: Citation `ghost2030' on page 1 undefined on input line 4.\n"
    diags = parse_log(CompileOutcome(log=log), PAPER)
    assert len(diags) == 1
    assert diags[0].severity is Severity.ERROR
    assert diags[0].code == Code.COMPILE_ERROR
    assert diags[0].data["key"] == "ghost2030"
    assert diags[0].range.start.line == 3  # the \cite{ghost2030} line
    assert "[?]" in diags[0].message


def test_undefined_reference_is_a_warning_not_an_error():
    log = "LaTeX Warning: Reference `fig:missing' on page 1 undefined on input line 5.\n"
    diags = parse_log(CompileOutcome(log=log), PAPER)
    assert len(diags) == 1
    assert diags[0].severity is Severity.WARNING
    assert diags[0].code == Code.COMPILE_WARNING
    assert diags[0].range.start.line == 4


def test_bare_error_uses_the_following_line_hint():
    log = "! Undefined control sequence.\nl.6 \\undefinedmacro\n                   \n"
    diags = parse_log(CompileOutcome(log=log), PAPER)
    assert diags[0].range.start.line == 5


def test_error_without_any_line_information_lands_on_line_zero():
    diags = parse_log(CompileOutcome(log="! Emergency stop.\n"), PAPER)
    assert len(diags) == 1
    assert diags[0].range.start.line == 0


def test_rerun_notice_becomes_a_warning():
    log = "LaTeX Warning: Label(s) may have changed. Rerun to get cross-references right.\n"
    diags = parse_log(CompileOutcome(log=log), PAPER)
    assert len(diags) == 1
    assert diags[0].severity is Severity.WARNING
    assert "stale" in diags[0].message


def test_bibtex_log_is_reported():
    blg = "Warning--I didn't find a database entry for \"ghost2030\"\n"
    diags = parse_log(CompileOutcome(blg=blg), PAPER)
    assert len(diags) == 1
    assert diags[0].data["source"] == "bibtex"
    assert diags[0].message.startswith("BibTeX:")


def test_duplicate_errors_are_reported_once():
    log = (
        "./paper.tex:6: Undefined control sequence.\n"
        "./paper.tex:6: Undefined control sequence.\n"
    )
    assert len(parse_log(CompileOutcome(log=log), PAPER)) == 1


def test_repeated_undefined_citation_across_passes_is_reported_once():
    log = (
        "LaTeX Warning: Citation `ghost2030' on page 1 undefined on input line 4.\n"
        "LaTeX Warning: Citation `ghost2030' on page 1 undefined on input line 4.\n"
    )
    assert len(parse_log(CompileOutcome(log=log), PAPER)) == 1


# -- must not report ----------------------------------------------------------------------


def test_clean_log_produces_nothing():
    log = "This is pdfTeX, Version 3.141592653\nOutput written on paper.pdf (1 page).\n"
    assert parse_log(CompileOutcome(log=log), PAPER) == []


def test_overfull_and_underfull_boxes_are_ignored():
    log = (
        "Overfull \\hbox (12.0pt too wide) in paragraph at lines 4--5\n"
        "Underfull \\vbox (badness 10000) has occurred while \\output is active\n"
    )
    assert parse_log(CompileOutcome(log=log), PAPER) == []


def test_font_warnings_are_ignored():
    log = (
        "LaTeX Font Warning: Font shape `OT1/cmr/bx/sc' undefined on input line 3.\n"
        "Some font shapes were not available, defaults substituted.\n"
    )
    assert parse_log(CompileOutcome(log=log), PAPER) == []


def test_file_line_informational_lines_are_ignored():
    log = "./paper.tex:4: LaTeX Warning: Something merely informational.\n"
    assert parse_log(CompileOutcome(log=log), PAPER) == []


# -- inconclusive is not a finding ---------------------------------------------------------


def test_missing_toolchain_reports_nothing(tmp_path):
    # Same rule as an unreachable index: "we could not check" must never render as
    # "your paper does not build".
    gate = CompileGate(runner=UnavailableRunner("no pdflatex here"))
    tex = tmp_path / "paper.tex"
    tex.write_text(PAPER, encoding="utf-8")
    assert gate.check(tex) == []
    assert gate.available() is True  # UnavailableRunner exposes no `available` attribute


def test_gate_available_reflects_the_runner():
    gate = CompileGate(runner=SubprocessRunner(latex="definitely-not-a-real-binary"))
    assert gate.available() is False


def test_runner_failure_to_start_is_not_a_compile_failure(tmp_path):
    gate = CompileGate(runner=StubRunner(unavailable="docker daemon is not running"))
    tex = tmp_path / "paper.tex"
    tex.write_text(PAPER, encoding="utf-8")
    assert gate.check(tex) == []


# -- gate plumbing --------------------------------------------------------------------------


def test_gate_compiles_the_buffer_not_the_file_on_disk(tmp_path):
    tex = tmp_path / "paper.tex"
    tex.write_text("stale contents", encoding="utf-8")
    runner = StubRunner(log="./paper.tex:6: Undefined control sequence.\n")
    diags = CompileGate(runner=runner).check(tex, source=PAPER)
    assert runner.calls == 1
    assert diags[0].range.start.line == 5  # a line that only exists in the buffer


def test_gate_leaves_no_artifacts_beside_the_paper(tmp_path):
    tex = tmp_path / "paper.tex"
    tex.write_text(PAPER, encoding="utf-8")
    CompileGate(runner=StubRunner(log="")).check(tex)
    assert {p.name for p in tmp_path.iterdir()} == {"paper.tex"}


def test_missing_latex_binary_is_detected_without_running_anything():
    runner = SubprocessRunner(latex="definitely-not-a-real-binary")
    outcome = runner.run(Path("paper.tex"), Path("."))
    assert outcome.unavailable
    assert outcome.commands == []


def test_subprocess_command_uses_nonstopmode_and_file_line_error():
    command = SubprocessRunner()._command("latex", "paper", Path("."))
    assert "-interaction=nonstopmode" in command
    assert "-file-line-error" in command
    # A gate should surface every error in one run rather than stopping at the first.
    assert "-halt-on-error" not in command


def test_bibtex_pass_targets_the_stem():
    assert SubprocessRunner()._command("bibtex", "paper", Path(".")) == ["bibtex", "paper"]


def test_default_passes_run_latex_three_times_around_bibtex():
    # Reference numbers need a pass to be written and another to be read back.
    assert SubprocessRunner().passes == ("latex", "bibtex", "latex", "latex")


def test_docker_command_mounts_the_workdir_and_disables_networking(tmp_path):
    command = DockerRunner(image="texlive/texlive:TL2024")._command("latex", "paper", tmp_path)
    assert command[:3] == ["docker", "run", "--rm"]
    assert "--network" in command and "none" in command
    assert f"{tmp_path.resolve()}:/work" in command
    assert "texlive/texlive:TL2024" in command
    assert command[-1] == "paper.tex"
