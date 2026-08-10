"""Command handlers, exercised through pygls's real argument dispatch.

Every other test that touches a ``@server.command`` handler calls the Python function
directly — `bibliography_status(ls, "file:///p.tex")` — which bypasses the one thing pygls
actually does before your handler ever runs: it inspects the handler's *own signature* and
unpacks the client's JSON ``arguments`` array positionally, one element per declared
parameter (after the injected ``ls``). That is a real, load-bearing step, and nothing in
this project's test suite exercised it until this file existed.

The gap it hid: every command handler here used to be written as
``def handler(ls, args): uri = args[0]``. For a client call sending ``arguments: [uri]``,
pygls does not hand the array to ``args`` — it has already consumed the array's one element
to fill that single declared parameter. So ``args`` was bound to the URI *string itself*,
and ``args[0]`` was its first *character*. Every real caller — the VS Code extension, the
desktop prototype — got ``"Only file:// documents can be compiled."`` for a perfectly valid
URI. It surfaced only when a real external client drove a real protocol-level compile,
which is precisely the gap this file closes: it drives the *same* dispatch pygls itself
runs, without needing a spawned process or a socket.
"""
from __future__ import annotations

from lsprotocol import types as lsp_types
from pygls.protocol.language_server import _prepare_command_arguments

from aurelius_ide.lsp import (
    BIBLIOGRAPHY_COMMAND,
    COMPILE_GATE_COMMAND,
    COMPILE_PDF_COMMAND,
    SEARCH_COMMAND,
    SUBMISSION_GATE_COMMAND,
    server,
)


def _dispatch(command: str, arguments):
    """The exact ``(args, kwargs)`` pygls computes for a real ``workspace/executeCommand``."""
    handler = server.protocol.fm.commands[command]
    params = lsp_types.ExecuteCommandParams(command=command, arguments=arguments)
    return _prepare_command_arguments(handler, params, server.protocol._converter)


URI_COMMANDS = (
    BIBLIOGRAPHY_COMMAND,
    SUBMISSION_GATE_COMMAND,
    COMPILE_GATE_COMMAND,
    COMPILE_PDF_COMMAND,
)


def test_single_uri_argument_is_delivered_whole_not_sliced():
    """The regression this file exists for: a one-element `arguments` array must reach
    the handler as that one string — not the string's first character."""
    for command in URI_COMMANDS:
        args, kwargs = _dispatch(command, ["file:///p.tex"])
        assert args == ("file:///p.tex",), f"{command} received {args!r}"
        assert kwargs == {}


def test_search_receives_query_and_limit_as_two_separate_positions():
    # This one would previously have raised TypeError outright — `args` consumed only the
    # query, and pygls's own leftover-argument check rejects the still-unconsumed limit.
    args, kwargs = _dispatch(SEARCH_COMMAND, ["retrieval augmented generation", 5])
    assert args == ("retrieval augmented generation", 5)
    assert kwargs == {}


def test_no_arguments_at_all_falls_back_to_the_handlers_own_default():
    # workspace/executeCommand with no `arguments` key: pygls returns straight away
    # without consulting the handler's signature at all, so "no URI supplied" has to be
    # carried by the Python parameter default, not by pygls.
    for command in URI_COMMANDS:
        args, kwargs = _dispatch(command, None)
        assert args == ()
        assert kwargs == {}


def test_every_panel_command_declares_named_parameters_not_a_generic_args_list():
    """Pins the fix at the signature level, so a future command can't reintroduce the
    same mistake by copy-pasting the old `def handler(ls, args)` shape."""
    import inspect

    for command in (*URI_COMMANDS, SEARCH_COMMAND):
        handler = server.protocol.fm.commands[command]
        params = list(inspect.signature(handler).parameters.values())
        # First param is the injected language server; every param after it must be a
        # plain named parameter (or **kwargs), never a single bare `args`/`*args` catch-all
        # that a human would be tempted to index by hand.
        for param in params[1:]:
            assert param.name != "args", (
                f"{command} declares a generic `args` parameter — pygls will bind it to "
                f"a single unpacked element, not the arguments list. Name it for what it "
                f"actually is."
            )
