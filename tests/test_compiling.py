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
    TectonicRunner,
    UnavailableRunner,
    default_gate,
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

    def __init__(
        self,
        log: str = "",
        blg: str = "",
        returncode: int = 0,
        unavailable=None,
        produce_pdf: bool = False,
    ):
        self.outcome = CompileOutcome(
            log=log, blg=blg, returncode=returncode, unavailable=unavailable
        )
        self.calls = 0
        # Simulates a successful build actually producing a PDF, the way a real
        # SubprocessRunner/TectonicRunner would leave one in the workdir.
        self.produce_pdf = produce_pdf

    def run(self, tex_path: Path, workdir: Path) -> CompileOutcome:
        self.calls += 1
        if self.produce_pdf and not self.outcome.unavailable:
            (workdir / (tex_path.stem + ".pdf")).write_bytes(b"%PDF-1.5\n%stub\n")
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


# -- tectonic -----------------------------------------------------------------------------


def test_tectonic_is_a_single_pass_not_four():
    # Tectonic reruns itself until the aux file stabilises; DEFAULT_PASSES's four-step
    # dance exists to force that behaviour out of pdflatex, which doesn't do it alone.
    assert TectonicRunner().passes == ("tectonic",)


def test_tectonic_command_has_no_pdflatex_only_flags():
    command = TectonicRunner()._command("tectonic", "paper", Path("."))
    assert command[0] == "tectonic"
    assert command[-1] == "paper.tex"
    assert "--keep-logs" in command
    # These are pdflatex-specific and meaningless to Tectonic's CLI.
    assert "-interaction=nonstopmode" not in command
    assert "-file-line-error" not in command


def test_tectonic_missing_binary_is_detected_without_running_anything():
    runner = TectonicRunner(tectonic="definitely-not-a-real-binary")
    outcome = runner.run(Path("paper.tex"), Path("."))
    assert outcome.unavailable
    assert outcome.commands == []


def test_tectonic_uses_the_configured_executable_name():
    runner = TectonicRunner(tectonic="my-tectonic")
    assert runner._command("tectonic", "paper", Path("."))[0] == "my-tectonic"


# -- pdf persistence ------------------------------------------------------------------------


def test_compiled_pdf_is_copied_to_the_requested_output(tmp_path):
    tex = tmp_path / "paper.tex"
    tex.write_text(PAPER, encoding="utf-8")
    pdf_output = tmp_path / "paper.pdf"

    gate = CompileGate(runner=StubRunner(produce_pdf=True))
    gate.check(tex, pdf_output=pdf_output)

    assert pdf_output.is_file()
    assert pdf_output.read_bytes().startswith(b"%PDF-1.5")


def test_pdf_output_defaults_to_none_and_writes_nothing(tmp_path):
    tex = tmp_path / "paper.tex"
    tex.write_text(PAPER, encoding="utf-8")
    CompileGate(runner=StubRunner(produce_pdf=True)).check(tex)
    # No pdf_output was requested, so nothing should appear beside the source either —
    # the scratch directory that actually held the PDF is still destroyed.
    assert {p.name for p in tmp_path.iterdir()} == {"paper.tex"}


def test_no_pdf_is_written_when_the_compile_produced_none(tmp_path):
    tex = tmp_path / "paper.tex"
    tex.write_text(PAPER, encoding="utf-8")
    pdf_output = tmp_path / "paper.pdf"

    # produce_pdf=False: a real failed compile that never got as far as xdvipdfmx.
    gate = CompileGate(runner=StubRunner(log="! Emergency stop.\n", produce_pdf=False))
    gate.check(tex, pdf_output=pdf_output)

    assert not pdf_output.exists()


def test_no_pdf_is_written_when_the_toolchain_is_unavailable(tmp_path):
    tex = tmp_path / "paper.tex"
    tex.write_text(PAPER, encoding="utf-8")
    pdf_output = tmp_path / "paper.pdf"

    gate = CompileGate(runner=StubRunner(unavailable="no toolchain", produce_pdf=True))
    gate.check(tex, pdf_output=pdf_output)

    # produce_pdf is ignored when the stub itself reports unavailable, matching what a
    # real runner does: it never gets far enough to leave a PDF behind either.
    assert not pdf_output.exists()


def test_pdf_output_directory_is_created_if_missing(tmp_path):
    tex = tmp_path / "paper.tex"
    tex.write_text(PAPER, encoding="utf-8")
    pdf_output = tmp_path / "build" / "nested" / "paper.pdf"

    CompileGate(runner=StubRunner(produce_pdf=True)).check(tex, pdf_output=pdf_output)

    assert pdf_output.is_file()


# -- default_gate fallback chain ------------------------------------------------------------


def test_default_gate_prefers_explicit_docker_image(monkeypatch):
    monkeypatch.setenv("AURELIUS_LATEX_DOCKER_IMAGE", "texlive/texlive:TL2024")
    gate = default_gate()
    assert isinstance(gate.runner, DockerRunner)
    assert gate.runner.image == "texlive/texlive:TL2024"


def test_default_gate_honours_explicit_latex_override(monkeypatch):
    monkeypatch.delenv("AURELIUS_LATEX_DOCKER_IMAGE", raising=False)
    monkeypatch.setenv("AURELIUS_LATEX", "/opt/custom/pdflatex")
    gate = default_gate()
    assert isinstance(gate.runner, SubprocessRunner)
    assert not isinstance(gate.runner, TectonicRunner)
    assert gate.runner.latex == "/opt/custom/pdflatex"


def test_default_gate_falls_back_to_tectonic_when_pdflatex_is_absent(monkeypatch):
    monkeypatch.delenv("AURELIUS_LATEX_DOCKER_IMAGE", raising=False)
    monkeypatch.delenv("AURELIUS_LATEX", raising=False)
    monkeypatch.delenv("AURELIUS_TECTONIC", raising=False)

    import shutil as shutil_module

    def fake_which(name):
        return "/usr/bin/tectonic" if name == "tectonic" else None

    monkeypatch.setattr(shutil_module, "which", fake_which)
    gate = default_gate()
    assert isinstance(gate.runner, TectonicRunner)


def test_default_gate_reports_both_options_when_nothing_is_found(monkeypatch):
    monkeypatch.delenv("AURELIUS_LATEX_DOCKER_IMAGE", raising=False)
    monkeypatch.delenv("AURELIUS_LATEX", raising=False)
    monkeypatch.delenv("AURELIUS_TECTONIC", raising=False)

    import shutil as shutil_module

    monkeypatch.setattr(shutil_module, "which", lambda name: None)
    gate = default_gate()
    assert isinstance(gate.runner, UnavailableRunner)
    assert "Tectonic" in gate.runner.reason
    assert "TeX Live" in gate.runner.reason
