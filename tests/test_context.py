"""Tests for Context Engineering — Sprint 35 Part C (TDD: written FIRST).

Context engineering manages the conversation context window by:
1. Keeping recent messages verbatim
2. Summarizing older messages when triggers fire (token limit, message count)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock


# ===========================================================================
# Test: ContextConfig — configurable triggers
# ===========================================================================

class TestContextConfig:
    """Test context configuration."""

    def test_default_config(self):
        """Default config has sensible trigger thresholds."""
        from bifrost.context.middleware import ContextConfig

        config = ContextConfig()
        assert config.max_messages > 0
        assert config.max_tokens > 0
        assert config.recent_messages_to_keep > 0

    def test_custom_config(self):
        """Custom trigger thresholds are respected."""
        from bifrost.context.middleware import ContextConfig

        config = ContextConfig(
            max_messages=30,
            max_tokens=8000,
            recent_messages_to_keep=5,
        )
        assert config.max_messages == 30
        assert config.max_tokens == 8000
        assert config.recent_messages_to_keep == 5


# ===========================================================================
# Test: Summarizer — LLM-based message summarization
# ===========================================================================

class TestSummarizer:
    """Test conversation summarizer."""

    @pytest.mark.asyncio
    async def test_summarize_messages(self):
        """Summarize a list of messages into a concise summary."""
        from bifrost.context.summarizer import Summarizer

        mock_heimdall = AsyncMock()
        mock_heimdall.chat_completion.return_value = {
            "choices": [{
                "message": {
                    "content": "The user asked about heart disease treatment. The assistant explained ACE inhibitors and beta blockers."
                },
                "finish_reason": "stop",
            }],
        }

        summarizer = Summarizer(heimdall=mock_heimdall)
        summary = await summarizer.summarize([
            {"role": "user", "content": "What's the treatment for heart disease?"},
            {"role": "assistant", "content": "Common treatments include ACE inhibitors, beta blockers..."},
            {"role": "user", "content": "What about dosages?"},
            {"role": "assistant", "content": "ACE inhibitor dosages vary by medication..."},
        ])

        assert "heart disease" in summary.lower()
        assert len(summary) > 10

    @pytest.mark.asyncio
    async def test_summarize_empty_messages(self):
        """Return empty string for no messages."""
        from bifrost.context.summarizer import Summarizer

        summarizer = Summarizer(heimdall=AsyncMock())
        summary = await summarizer.summarize([])

        assert summary == ""

    @pytest.mark.asyncio
    async def test_summarize_handles_llm_error(self):
        """Gracefully handle LLM errors — return fallback."""
        from bifrost.context.summarizer import Summarizer

        mock_heimdall = AsyncMock()
        mock_heimdall.chat_completion.side_effect = Exception("LLM timeout")

        summarizer = Summarizer(heimdall=mock_heimdall)
        summary = await summarizer.summarize([
            {"role": "user", "content": "Hello"},
        ])

        # Should return empty string on error, not crash
        assert summary == ""


# ===========================================================================
# Test: ContextMiddleware — trigger-based compression
# ===========================================================================

class TestContextMiddleware:
    """Test context compression middleware."""

    def test_estimate_tokens(self):
        """Token estimation works with word-based approximation."""
        from bifrost.context.middleware import ContextMiddleware, ContextConfig

        middleware = ContextMiddleware(
            summarizer=MagicMock(),
            config=ContextConfig(),
        )

        messages = [
            {"role": "user", "content": "Hello, how are you?"},
            {"role": "assistant", "content": "I'm fine, thank you!"},
        ]

        tokens = middleware.estimate_tokens(messages)
        assert tokens > 0
        assert isinstance(tokens, int)

    def test_should_compress_by_message_count(self):
        """Trigger compression when message count exceeds threshold."""
        from bifrost.context.middleware import ContextMiddleware, ContextConfig

        config = ContextConfig(max_messages=5, max_tokens=100000)
        middleware = ContextMiddleware(summarizer=MagicMock(), config=config)

        # 6 messages > max_messages (5) → should compress
        messages = [{"role": "user", "content": f"msg {i}"} for i in range(6)]
        assert middleware.should_compress(messages) is True

        # 4 messages < max_messages (5) → should NOT compress
        messages = [{"role": "user", "content": f"msg {i}"} for i in range(4)]
        assert middleware.should_compress(messages) is False

    def test_should_compress_by_token_count(self):
        """Trigger compression when token count exceeds threshold."""
        from bifrost.context.middleware import ContextMiddleware, ContextConfig

        config = ContextConfig(max_messages=100, max_tokens=50)
        middleware = ContextMiddleware(summarizer=MagicMock(), config=config)

        # Long messages → token count > 50 → should compress
        messages = [
            {"role": "user", "content": "This is a very long message " * 20},
        ]
        assert middleware.should_compress(messages) is True

    @pytest.mark.asyncio
    async def test_compress_keeps_recent_messages(self):
        """Compression keeps recent messages verbatim, summarizes older ones."""
        from bifrost.context.middleware import ContextMiddleware, ContextConfig
        from bifrost.context.summarizer import Summarizer

        mock_heimdall = AsyncMock()
        mock_heimdall.chat_completion.return_value = {
            "choices": [{
                "message": {"content": "Summary: User discussed topics A and B."},
                "finish_reason": "stop",
            }],
        }

        config = ContextConfig(max_messages=4, recent_messages_to_keep=2)
        summarizer = Summarizer(heimdall=mock_heimdall)
        middleware = ContextMiddleware(summarizer=summarizer, config=config)

        messages = [
            {"role": "user", "content": "Old message 1"},
            {"role": "assistant", "content": "Old response 1"},
            {"role": "user", "content": "Old message 2"},
            {"role": "assistant", "content": "Old response 2"},
            {"role": "user", "content": "Recent message 1"},
            {"role": "assistant", "content": "Recent response 1"},
        ]

        compressed = await middleware.compress(messages)

        # Should have: 1 summary message + 2 recent messages = 3
        assert len(compressed) == 3

        # First message should be the summary
        assert compressed[0]["role"] == "system"
        assert "Summary" in compressed[0]["content"]

        # Last 2 should be the recent messages (verbatim)
        assert compressed[-2]["content"] == "Recent message 1"
        assert compressed[-1]["content"] == "Recent response 1"

    @pytest.mark.asyncio
    async def test_compress_returns_original_if_no_trigger(self):
        """If no compression trigger fires, return messages unchanged."""
        from bifrost.context.middleware import ContextMiddleware, ContextConfig

        config = ContextConfig(max_messages=100, max_tokens=100000)
        middleware = ContextMiddleware(summarizer=MagicMock(), config=config)

        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ]

        compressed = await middleware.compress(messages)
        assert compressed == messages

    @pytest.mark.asyncio
    async def test_process_applies_compression_when_triggered(self):
        """process() method applies compression when thresholds exceeded."""
        from bifrost.context.middleware import ContextMiddleware, ContextConfig
        from bifrost.context.summarizer import Summarizer

        mock_heimdall = AsyncMock()
        mock_heimdall.chat_completion.return_value = {
            "choices": [{
                "message": {"content": "Summary of old conversation."},
                "finish_reason": "stop",
            }],
        }

        config = ContextConfig(max_messages=3, recent_messages_to_keep=2)
        summarizer = Summarizer(heimdall=mock_heimdall)
        middleware = ContextMiddleware(summarizer=summarizer, config=config)

        messages = [
            {"role": "user", "content": f"msg {i}"} for i in range(5)
        ]

        result = await middleware.process(messages)
        assert len(result) < len(messages)
