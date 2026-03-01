"""Tests for Codex and Gemini output parsers."""

from superai_mcp.parsers import parse_codex_output, parse_gemini_output

# -- Real CLI output fixtures --

CODEX_LINES = [
    '{"type":"thread.started","thread_id":"abc-123"}',
    '{"type":"turn.started"}',
    '{"type":"item.completed","item":{"id":"item_0","type":"reasoning","text":"thinking..."}}',
    '{"type":"item.completed","item":{"id":"item_1","type":"agent_message","text":"Hello"}}',
    '{"type":"turn.completed","usage":{"input_tokens":100,"output_tokens":10}}',
]

GEMINI_LINES = [
    '{"type":"init","session_id":"gem-456","model":"gemini-3"}',
    '{"type":"message","role":"user","content":"hi"}',
    '{"type":"message","role":"assistant","content":"Hello","delta":true}',
    '{"type":"message","role":"assistant","content":" there!","delta":true}',
    '{"type":"result","status":"success","stats":{"input_tokens":50,"output_tokens":5}}',
]


class TestCodexParser:
    def test_basic(self) -> None:
        r = parse_codex_output(CODEX_LINES)
        assert r.success is True
        assert r.session_id == "abc-123"
        assert r.content == "Hello"
        assert r.usage is not None
        assert r.usage["input_tokens"] == 100
        assert r.all_messages is None

    def test_return_all(self) -> None:
        r = parse_codex_output(CODEX_LINES, return_all=True)
        assert r.all_messages is not None
        assert len(r.all_messages) == 5

    def test_empty(self) -> None:
        r = parse_codex_output([])
        assert r.success is False
        assert r.content == "(no output)"
        assert r.session_id is None

    def test_multi_message(self) -> None:
        lines = [
            '{"type":"thread.started","thread_id":"x"}',
            '{"type":"item.completed","item":{"type":"agent_message","text":"A"}}',
            '{"type":"item.completed","item":{"type":"agent_message","text":"B"}}',
        ]
        r = parse_codex_output(lines)
        assert r.content == "A\n\nB"

    def test_malformed_json(self) -> None:
        r = parse_codex_output(["not json", "", '{"type":"thread.started","thread_id":"ok"}'])
        assert r.session_id == "ok"


class TestGeminiParser:
    def test_basic(self) -> None:
        r = parse_gemini_output(GEMINI_LINES)
        assert r.success is True
        assert r.session_id == "gem-456"
        assert r.content == "Hello there!"
        assert r.usage is not None
        assert r.usage["input_tokens"] == 50

    def test_return_all(self) -> None:
        r = parse_gemini_output(GEMINI_LINES, return_all=True)
        assert r.all_messages is not None
        assert len(r.all_messages) == 5

    def test_empty(self) -> None:
        r = parse_gemini_output([])
        assert r.success is False
        assert r.content == "(no output)"

    def test_failure_status(self) -> None:
        lines = [
            '{"type":"init","session_id":"f"}',
            '{"type":"result","status":"error"}',
        ]
        r = parse_gemini_output(lines)
        assert r.success is False

    def test_malformed_json(self) -> None:
        r = parse_gemini_output(["broken{", '{"type":"init","session_id":"ok"}'])
        assert r.session_id == "ok"
