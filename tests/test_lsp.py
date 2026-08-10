"""URI <-> path conversion in the LSP transport.

``_uri_to_path`` had no test at all, on either platform, because nothing in the rest of
the suite ever round-trips a hand-built ``file://`` URI string — every other test talks
to the engine directly with plain URIs used only as opaque cache keys. The bug this file
pins down was found by pointing a real client (the desktop prototype in ``apps/desktop``)
at the real server with a real Windows path and watching bibliography resolution silently
find nothing.

``Path.as_uri()`` (the reverse direction, exercised by ``_path_to_uri``) was always
correct. Only the URI-to-path direction was broken, which is why it went unnoticed: any
test that only ever builds a URI *from* a path and never parses one *back* never exercises
the bug at all.
"""
from __future__ import annotations

import sys

import pytest

from aurelius_ide.lsp import _path_to_uri, _uri_to_path, server

WINDOWS_ONLY = pytest.mark.skipif(
    sys.platform != "win32", reason="drive-letter URIs are Windows-specific"
)
POSIX_ONLY = pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX-style absolute paths only apply there"
)


@WINDOWS_ONLY
def test_windows_drive_letter_uri_becomes_an_absolute_path():
    # The exact failure: parsing this used to yield WindowsPath('/D:/...'), which
    # `.is_absolute()` reports as False — a path that silently resolves against the
    # current drive instead of the file that was actually opened.
    path = _uri_to_path("file:///D:/papers/draft/paper.tex")
    assert path is not None
    assert path.is_absolute()
    assert str(path) == "D:\\papers\\draft\\paper.tex"


@WINDOWS_ONLY
def test_windows_path_round_trips_through_both_directions(tmp_path):
    original = tmp_path / "paper.tex"
    original.write_text("", encoding="utf-8")

    uri = _path_to_uri(original)
    assert uri.startswith("file:///")  # the triple-slash form every real client sends

    recovered = _uri_to_path(uri)
    assert recovered == original
    assert recovered.exists()


@WINDOWS_ONLY
def test_sibling_glob_finds_a_real_file_after_conversion(tmp_path):
    # This is the actual mechanism that was broken: resolve_bib()'s fallback globs
    # `tex_path.parent` for a .bib file. A relative-looking parent silently globs nothing,
    # which is why the symptom was "every citation is undefined" rather than an error.
    (tmp_path / "paper.tex").write_text("", encoding="utf-8")
    (tmp_path / "references.bib").write_text("", encoding="utf-8")

    tex_path = _uri_to_path(_path_to_uri(tmp_path / "paper.tex"))
    assert tex_path is not None
    assert tex_path.parent.is_dir()
    assert list(tex_path.parent.glob("*.bib")) == [tmp_path / "references.bib"]


@POSIX_ONLY
def test_posix_path_is_unaffected(tmp_path):
    original = tmp_path / "paper.tex"
    original.write_text("", encoding="utf-8")

    recovered = _uri_to_path(_path_to_uri(original))
    assert recovered == original


def test_non_file_scheme_returns_none():
    assert _uri_to_path("untitled:Untitled-1") is None


def test_percent_encoded_characters_are_decoded():
    path = _uri_to_path("file:///tmp/a%20paper.tex")
    assert path is not None
    assert path.name == "a paper.tex"


def test_engine_is_wired_to_publish_live_verification_progress(monkeypatch):
    """The engine's on_progress lands on the wire as aurelius/verificationProgress —
    a fire-and-forget notification a client can ignore, not a fifth panel command."""
    sent: list[tuple[str, object]] = []
    monkeypatch.setattr(
        server.protocol, "notify", lambda method, params: sent.append((method, params))
    )

    assert server.engine.on_progress == server._publish_progress
    server.engine.on_progress("file:///p.tex", "smith2020", "openalex", "checking")

    expected_params = {
        "uri": "file:///p.tex",
        "key": "smith2020",
        "source": "openalex",
        "status": "checking",
    }
    assert sent == [("aurelius/verificationProgress", expected_params)]
