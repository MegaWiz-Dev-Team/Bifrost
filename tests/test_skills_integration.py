"""Tests for skills integration into agent executor — Sprint 35 Task 4 (TDD)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path


# ---------------------------------------------------------------------------
# Fixtures for mock skills
# ---------------------------------------------------------------------------

MEDICAL_SKILL_MD = """\
---
name: medical-research
description: Use for medical literature research and evidence synthesis.
version: "1.0"
tags: [medical, research]
tools: [mimir_search]
---

# Medical Research

## Instructions
1. Search PubMed
2. Synthesize evidence
"""

SECURITY_SKILL_MD = """\
---
name: security-audit
description: Trigger for code security scanning and vulnerability assessment.
version: "1.0"
tags: [security, audit]
tools: [huginn_scan]
---

# Security Audit

## Instructions
1. Run Semgrep scan
2. Generate report
"""


def _create_skill_dirs(tmp_path: Path) -> list[str]:
    """Helper: create skill dirs with test SKILL.md files."""
    public = tmp_path / "public"
    public.mkdir()
    (public / "medical-research").mkdir()
    (public / "medical-research" / "SKILL.md").write_text(MEDICAL_SKILL_MD)
    (public / "security-audit").mkdir()
    (public / "security-audit" / "SKILL.md").write_text(SECURITY_SKILL_MD)
    return [str(public)]


# ===========================================================================
# Test: Skills-enhanced executor
# ===========================================================================

class TestSkillsIntegration:
    """Test that the executor injects relevant skills into system prompt."""

    def test_executor_accepts_skills_loader(self):
        """AgentExecutor constructor accepts optional skills_loader."""
        from bifrost.core.executor import AgentExecutor
        from bifrost.skills.loader import SkillsLoader

        loader = SkillsLoader()
        executor = AgentExecutor(
            heimdall=MagicMock(),
            tool_registry=MagicMock(),
            skills_loader=loader,
            skills_dirs=["/tmp/skills"],
        )

        assert executor.skills_loader is loader
        assert executor.skills_dirs == ["/tmp/skills"]

    def test_executor_without_skills_loader(self):
        """AgentExecutor works without skills_loader (backward-compatible)."""
        from bifrost.core.executor import AgentExecutor

        executor = AgentExecutor(
            heimdall=MagicMock(),
            tool_registry=MagicMock(),
        )

        assert executor.skills_loader is None
        assert executor.skills_dirs == []

    @pytest.mark.asyncio
    async def test_execute_injects_skills_into_system_prompt(self, tmp_path: Path):
        """When skills_loader is set, relevant skills are injected into system prompt."""
        from bifrost.core.executor import AgentExecutor
        from bifrost.skills.loader import SkillsLoader

        skill_dirs = _create_skill_dirs(tmp_path)
        loader = SkillsLoader()

        # Mock Heimdall to capture the messages sent
        mock_heimdall = AsyncMock()
        mock_heimdall.chat_completion.return_value = {
            "choices": [{
                "message": {"content": "Here is the security audit result."},
                "finish_reason": "stop",
            }],
        }

        mock_registry = MagicMock()
        mock_registry.get_openai_tools.return_value = []

        executor = AgentExecutor(
            heimdall=mock_heimdall,
            tool_registry=mock_registry,
            skills_loader=loader,
            skills_dirs=skill_dirs,
        )

        result = await executor.execute(
            system_prompt="You are a helpful assistant.",
            user_input="scan code for security vulnerabilities",
        )

        # Check that Heimdall was called with skills-augmented system prompt
        call_args = mock_heimdall.chat_completion.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages") or call_args[0][0]

        system_msg = messages[0]
        assert system_msg["role"] == "system"
        assert "<skills>" in system_msg["content"]
        assert "security-audit" in system_msg["content"]
        assert "# Security Audit" in system_msg["content"]

    @pytest.mark.asyncio
    async def test_execute_no_skills_when_unrelated_query(self, tmp_path: Path):
        """When no skills match, system prompt is NOT augmented."""
        from bifrost.core.executor import AgentExecutor
        from bifrost.skills.loader import SkillsLoader

        skill_dirs = _create_skill_dirs(tmp_path)
        loader = SkillsLoader()

        mock_heimdall = AsyncMock()
        mock_heimdall.chat_completion.return_value = {
            "choices": [{
                "message": {"content": "I like pizza too."},
                "finish_reason": "stop",
            }],
        }

        mock_registry = MagicMock()
        mock_registry.get_openai_tools.return_value = []

        executor = AgentExecutor(
            heimdall=mock_heimdall,
            tool_registry=mock_registry,
            skills_loader=loader,
            skills_dirs=skill_dirs,
        )

        result = await executor.execute(
            system_prompt="You are a helpful assistant.",
            user_input="what is the best pizza recipe?",
        )

        # No skills should be injected
        call_args = mock_heimdall.chat_completion.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages") or call_args[0][0]

        system_msg = messages[0]
        assert "<skills>" not in system_msg["content"]
        assert system_msg["content"] == "You are a helpful assistant."

    @pytest.mark.asyncio
    async def test_execute_without_loader_unchanged(self):
        """Without skills_loader, execute behaves exactly as before."""
        from bifrost.core.executor import AgentExecutor

        mock_heimdall = AsyncMock()
        mock_heimdall.chat_completion.return_value = {
            "choices": [{
                "message": {"content": "Hello!"},
                "finish_reason": "stop",
            }],
        }

        mock_registry = MagicMock()
        mock_registry.get_openai_tools.return_value = []

        executor = AgentExecutor(
            heimdall=mock_heimdall,
            tool_registry=mock_registry,
        )

        result = await executor.execute(
            system_prompt="You are a helpful assistant.",
            user_input="hello",
        )

        call_args = mock_heimdall.chat_completion.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages") or call_args[0][0]

        system_msg = messages[0]
        assert system_msg["content"] == "You are a helpful assistant."
        assert result.output == "Hello!"
