"""Tests for Codex and Gemini output parsers."""

from superai_mcp.parsers import (
    is_quota_exhausted,
    is_rate_limited,
    parse_claude_output,
    parse_codex_output,
    parse_gemini_output,
)
from superai_mcp.models import CLIResult

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


CLAUDE_LINES = [
    '{"session_id":"claude-789","usage":{"input_tokens":200,"output_tokens":20},"result":"Hello from Claude"}',
]

CLAUDE_MULTILINE = [
    '{',
    '  "session_id": "claude-multi",',
    '  "usage": {"input_tokens": 100, "output_tokens": 10},',
    '  "result": "Multi-line response"',
    '}',
]


class TestClaudeParser:
    def test_basic(self) -> None:
        r = parse_claude_output(CLAUDE_LINES)
        assert r.success is True
        assert r.session_id == "claude-789"
        assert r.content == "Hello from Claude"
        assert r.model is None  # no model field in fixture
        assert r.usage is not None
        assert r.usage["input_tokens"] == 200
        assert r.all_messages is None

    def test_return_all(self) -> None:
        r = parse_claude_output(CLAUDE_LINES, return_all=True)
        assert r.all_messages is not None
        assert len(r.all_messages) == 1
        assert r.all_messages[0]["result"] == "Hello from Claude"

    def test_empty(self) -> None:
        r = parse_claude_output([])
        assert r.success is False
        assert r.content == "(no output)"
        assert r.session_id is None

    def test_single_line(self) -> None:
        r = parse_claude_output(CLAUDE_LINES)
        assert r.success is True
        assert r.content == "Hello from Claude"

    def test_multiline_json(self) -> None:
        r = parse_claude_output(CLAUDE_MULTILINE)
        assert r.success is True
        assert r.session_id == "claude-multi"
        assert r.content == "Multi-line response"

    def test_no_result(self) -> None:
        lines = ['{"session_id":"x","usage":{"input_tokens":10,"output_tokens":0}}']
        r = parse_claude_output(lines)
        assert r.success is False
        assert r.content == "(no output)"
        assert r.session_id == "x"

    def test_warning_before_json(self) -> None:
        lines = [
            "Warning: some deprecation notice",
            '{"session_id":"w","usage":{},"result":"OK"}',
        ]
        r = parse_claude_output(lines)
        assert r.success is True
        assert r.content == "OK"
        assert r.session_id == "w"

    def test_no_auth(self) -> None:
        lines = [
            "Error: Not authenticated. Please run claude login.",
        ]
        r = parse_claude_output(lines)
        assert r.success is False
        assert "authenticated" in r.content

    def test_missing_session_id(self) -> None:
        lines = ['{"usage":{},"result":"hi"}']
        r = parse_claude_output(lines)
        assert r.success is True
        assert r.session_id is None

    def test_malformed_json(self) -> None:
        lines = ["{broken json}"]
        r = parse_claude_output(lines)
        assert r.success is False
        assert r.content == "(no output)"

    def test_model_extracted(self) -> None:
        lines = ['{"session_id":"c","model":"claude-sonnet-4-6","usage":{},"result":"hi"}']
        r = parse_claude_output(lines)
        assert r.success is True
        assert r.model == "claude-sonnet-4-6"


class TestCodexParser:
    def test_basic(self) -> None:
        r = parse_codex_output(CODEX_LINES)
        assert r.success is True
        assert r.session_id == "abc-123"
        assert r.content == "Hello"
        assert r.model is None  # codex output has no model info
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

    def test_non_object_json(self) -> None:
        r = parse_codex_output(['[]', '"string"', '123', 'null'])
        assert r.success is False
        assert r.content == "(no output)"

    def test_missing_thread_id(self) -> None:
        r = parse_codex_output(['{"type":"thread.started"}'])
        assert r.session_id is None

    def test_auth_failure_401(self) -> None:
        """Real codex output when API key is missing/invalid."""
        lines = [
            '{"type":"thread.started","thread_id":"abc"}',
            '{"type":"turn.started"}',
            '{"type":"error","message":"Reconnecting... 1/5 (401 Unauthorized)"}',
            '{"type":"error","message":"Reconnecting... 2/5 (401 Unauthorized)"}',
            '{"type":"error","message":"401 Unauthorized: Missing bearer auth"}',
            '{"type":"turn.failed","error":{"message":"401 Unauthorized: Missing bearer auth"}}',
        ]
        r = parse_codex_output(lines)
        assert r.success is False
        assert "401" in r.content
        assert "Unauthorized" in r.content
        # Reconnect lines should be filtered out
        assert "Reconnecting" not in r.content

    def test_bad_model(self) -> None:
        """Real codex output when model name is invalid."""
        lines = [
            '{"type":"thread.started","thread_id":"abc"}',
            '{"type":"item.completed","item":{"type":"error","message":"Model not found"}}',
            '{"type":"turn.failed","error":{"message":"Model not supported"}}',
        ]
        r = parse_codex_output(lines)
        assert r.success is False
        assert "Model not found" in r.content
        assert "Model not supported" in r.content

    def test_error_with_agent_output(self) -> None:
        """If there IS agent output, errors don't override it."""
        lines = [
            '{"type":"thread.started","thread_id":"x"}',
            '{"type":"error","message":"some warning"}',
            '{"type":"item.completed","item":{"type":"agent_message","text":"Hello"}}',
            '{"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":5}}',
        ]
        r = parse_codex_output(lines)
        assert r.success is True
        assert r.content == "Hello"


class TestIsRateLimited:
    def test_gemini_resource_exhausted(self) -> None:
        r = CLIResult(success=False, content="Error: RESOURCE_EXHAUSTED quota exceeded")
        assert is_rate_limited(r) is True

    def test_claude_overloaded(self) -> None:
        r = CLIResult(success=False, content="overloaded_error: model is overloaded")
        assert is_rate_limited(r) is True

    def test_http_429(self) -> None:
        r = CLIResult(success=False, content="429 Too Many Requests")
        assert is_rate_limited(r) is True

    def test_rate_limit_keyword(self) -> None:
        r = CLIResult(success=False, content="rate_limit_exceeded")
        assert is_rate_limited(r) is True

    def test_too_many_requests(self) -> None:
        r = CLIResult(success=False, content="Error: too many requests, please retry")
        assert is_rate_limited(r) is True

    def test_quota_keyword(self) -> None:
        r = CLIResult(success=False, content="API quota exceeded for this project")
        assert is_rate_limited(r) is True

    def test_success_result_not_detected(self) -> None:
        r = CLIResult(success=True, content="RESOURCE_EXHAUSTED")
        assert is_rate_limited(r) is False

    def test_other_error_not_detected(self) -> None:
        r = CLIResult(success=False, content="401 Unauthorized")
        assert is_rate_limited(r) is False

    def test_empty_content(self) -> None:
        r = CLIResult(success=False, content="")
        assert is_rate_limited(r) is False

    def test_case_insensitive(self) -> None:
        r = CLIResult(success=False, content="resource_exhausted")
        assert is_rate_limited(r) is True

    def test_backward_compat_alias(self) -> None:
        r = CLIResult(success=False, content="RESOURCE_EXHAUSTED")
        assert is_quota_exhausted(r) is True
        assert is_quota_exhausted is is_rate_limited


class TestGeminiParser:
    def test_basic(self) -> None:
        r = parse_gemini_output(GEMINI_LINES)
        assert r.success is True
        assert r.session_id == "gem-456"
        assert r.content == "Hello there!"
        assert r.model == "gemini-3"
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

    def test_non_object_json(self) -> None:
        r = parse_gemini_output(['[1,2]', '"str"', '42'])
        assert r.success is False

    def test_missing_session_id(self) -> None:
        r = parse_gemini_output(['{"type":"init"}'])
        assert r.session_id is None

    def test_no_auth_plain_text(self) -> None:
        """Real gemini output when auth is not configured."""
        lines = [
            "Please set an Auth method in your settings.json or specify GEMINI_API_KEY",
        ]
        r = parse_gemini_output(lines)
        assert r.success is False
        assert "Auth" in r.content
        assert "GEMINI_API_KEY" in r.content

    def test_mixed_plain_and_json(self) -> None:
        """Gemini sometimes prints warnings before JSON."""
        lines = [
            "Loaded cached credentials.",
            '{"type":"init","session_id":"x"}',
            '{"type":"message","role":"assistant","content":"Hi","delta":true}',
            '{"type":"result","status":"success","stats":{"input_tokens":10}}',
        ]
        r = parse_gemini_output(lines)
        assert r.success is True
        assert r.content == "Hi"
        assert r.session_id == "x"
