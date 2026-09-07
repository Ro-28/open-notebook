"""Unit tests for scripts/app/subscription-proxy.py (routing + failover; no network)."""

import importlib.util
import sys
from pathlib import Path

import pytest

PROXY = Path(__file__).resolve().parents[1] / "scripts" / "app" / "subscription-proxy.py"


@pytest.fixture
def proxy(monkeypatch):
    monkeypatch.setenv("FALLBACK_CHAIN", "codex:gpt-5.5,anthropic:claude-haiku-4-5-20251001")
    spec = importlib.util.spec_from_file_location("subscription_proxy", PROXY)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["subscription_proxy"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _ok(model):
    return {"id": "x", "object": "chat.completion", "created": 0, "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": f"from {model}"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}


def test_provider_routing(proxy):
    assert proxy.provider_for("gpt-5.5") == "codex"
    assert proxy.provider_for("claude-sonnet-5") == "anthropic"
    assert proxy.provider_for("claude-haiku-4-5-20251001") == "anthropic"


def test_failover_walks_chain_and_reports(proxy, monkeypatch):
    calls = []

    def codex(model, data):
        calls.append(("codex", model))
        raise proxy.UpstreamError(429, "rate limited")

    def anthropic(model, data):
        calls.append(("anthropic", model))
        return _ok(model)

    monkeypatch.setattr(proxy, "codex_chat", codex)
    monkeypatch.setattr(proxy, "anthropic_chat", anthropic)
    result, served, errors = proxy.chat_with_failover({"model": "gpt-5.6", "messages": []})
    assert served == "anthropic:claude-haiku-4-5-20251001"
    assert result["choices"][0]["message"]["content"] == "from claude-haiku-4-5-20251001"
    assert calls == [("codex", "gpt-5.6"), ("codex", "gpt-5.5"), ("anthropic", "claude-haiku-4-5-20251001")]
    assert len(errors) == 2


def test_unsupported_model_400_still_fails_over(proxy, monkeypatch):
    monkeypatch.setattr(proxy, "codex_chat", lambda m, d: (_ for _ in ()).throw(
        proxy.UpstreamError(400, "The 'x' model is not supported when using Codex")))
    monkeypatch.setattr(proxy, "anthropic_chat", lambda m, d: _ok(m))
    _, served, _ = proxy.chat_with_failover({"model": "gpt-99", "messages": []})
    assert served.startswith("anthropic:")


def test_malformed_request_400_does_not_fail_over(proxy, monkeypatch):
    monkeypatch.setattr(proxy, "codex_chat", lambda m, d: (_ for _ in ()).throw(
        proxy.UpstreamError(400, "messages[0].content is required")))
    monkeypatch.setattr(proxy, "anthropic_chat", lambda m, d: pytest.fail("should not fall over on a bad body"))
    with pytest.raises(proxy.UpstreamError) as ei:
        proxy.chat_with_failover({"model": "gpt-5.5", "messages": []})
    assert ei.value.status == 400


def test_all_fail_raises_502(proxy, monkeypatch):
    monkeypatch.setattr(proxy, "codex_chat", lambda m, d: (_ for _ in ()).throw(proxy.UpstreamError(503, "down")))
    monkeypatch.setattr(proxy, "anthropic_chat", lambda m, d: (_ for _ in ()).throw(proxy.UpstreamError(529, "overloaded")))
    with pytest.raises(proxy.UpstreamError) as ei:
        proxy.chat_with_failover({"model": "gpt-5.5", "messages": []})
    assert ei.value.status == 502 and "all providers failed" in str(ei.value)


def test_openai_to_anthropic_message_shape(proxy):
    system, msgs = proxy._openai_messages_to_anthropic([
        {"role": "system", "content": "be terse"},
        {"role": "user", "content": [{"type": "text", "text": "hi"}]},
        {"role": "user", "content": "again"},
        {"role": "assistant", "content": "hello"},
        {"role": "tool", "content": "{}"},
    ])
    assert system == "be terse"
    assert msgs[0] == {"role": "user", "content": "hi\n\nagain"}  # consecutive same-role merged
    assert msgs[1]["role"] == "assistant"
    assert msgs[2]["role"] == "user" and msgs[2]["content"].startswith("[tool result]")


def test_claude_code_prefix_injected_once(proxy):
    d = proxy._inject_cc_prefix({"system": "hello"})
    assert d["system"][0]["text"] == proxy.CC_SYSTEM_PREFIX and d["system"][1]["text"] == "hello"
    d2 = proxy._inject_cc_prefix(d)
    assert len(d2["system"]) == 2


def test_sse_synthesis_ends_with_done(proxy):
    frames = proxy._chat_to_sse(_ok("gpt-5.5"))
    assert frames[0].startswith(b"data: ") and frames[-1] == b"data: [DONE]\n\n"
    assert b'"finish_reason": "stop"' in frames[-2]
