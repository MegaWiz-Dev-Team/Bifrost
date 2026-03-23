"""Tests for the skills system — Sprint 35 Task 1 (TDD: written FIRST)."""

import pytest
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers: create mock SKILL.md files in tmp dirs
# ---------------------------------------------------------------------------

VALID_SKILL_MD = """\
---
name: medical-research
description: Use this skill for medical literature research and evidence synthesis.
version: "1.0"
author: asgard-team
tags: [medical, research, evidence]
tools: [mimir_search, pubmed_search]
---

# Medical Research

## Overview
Systematic medical literature research skill.

## Instructions
1. Identify the clinical question
2. Search PubMed and medical knowledge bases
3. Synthesize evidence into structured summary
"""

MINIMAL_SKILL_MD = """\
---
name: simple-skill
description: A minimal skill with only required fields.
---

# Simple Skill

Does something simple.
"""

MISSING_NAME_MD = """\
---
description: This skill has no name field.
---

# Broken Skill
"""

MISSING_DESCRIPTION_MD = """\
---
name: no-desc
---

# Missing Description
"""

NO_FRONTMATTER_MD = """\
# No Frontmatter

This SKILL.md has no YAML frontmatter block at all.
"""

SKILL_SECURITY = """\
---
name: security-audit
description: Trigger for code security scanning, vulnerability assessment, and compliance checks.
version: "1.0"
tags: [security, audit, compliance]
tools: [huginn_scan, semgrep]
---

# Security Audit

## Instructions
1. Run Semgrep and Trivy scans
2. Analyze findings
3. Generate compliance report
"""

SKILL_DEPLOYMENT = """\
---
name: deployment
description: Use for deploying services, managing Docker containers, and CI/CD pipeline tasks.
version: "1.0"
tags: [devops, deployment, docker]
tools: [fenrir_execute, docker_compose]
---

# Deployment

## Instructions
1. Validate configuration
2. Build and push containers
3. Deploy to target environment
"""


# ===========================================================================
# Test: SkillConfig parsing
# ===========================================================================

class TestSkillParsing:
    """Test SKILL.md parsing into SkillConfig."""

    def test_parse_valid_skill_md(self, tmp_path: Path):
        """Parse a well-formed SKILL.md with all fields."""
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(VALID_SKILL_MD)

        from bifrost.skills.models import parse_skill_file

        skill = parse_skill_file(str(skill_file))

        assert skill.name == "medical-research"
        assert skill.description == "Use this skill for medical literature research and evidence synthesis."
        assert skill.version == "1.0"
        assert skill.author == "asgard-team"
        assert skill.tags == ["medical", "research", "evidence"]
        assert skill.tools == ["mimir_search", "pubmed_search"]
        assert "# Medical Research" in skill.content
        assert "Systematic medical literature research" in skill.content
        assert skill.path == str(skill_file)

    def test_parse_minimal_skill_md(self, tmp_path: Path):
        """Parse SKILL.md with only required fields (name + description)."""
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(MINIMAL_SKILL_MD)

        from bifrost.skills.models import parse_skill_file

        skill = parse_skill_file(str(skill_file))

        assert skill.name == "simple-skill"
        assert skill.description == "A minimal skill with only required fields."
        assert skill.version == ""
        assert skill.author == ""
        assert skill.tags == []
        assert skill.tools == []
        assert "# Simple Skill" in skill.content

    def test_parse_missing_name_raises(self, tmp_path: Path):
        """Raise ValueError when 'name' field is missing."""
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(MISSING_NAME_MD)

        from bifrost.skills.models import parse_skill_file

        with pytest.raises(ValueError, match="name"):
            parse_skill_file(str(skill_file))

    def test_parse_missing_description_raises(self, tmp_path: Path):
        """Raise ValueError when 'description' field is missing."""
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(MISSING_DESCRIPTION_MD)

        from bifrost.skills.models import parse_skill_file

        with pytest.raises(ValueError, match="description"):
            parse_skill_file(str(skill_file))

    def test_parse_no_frontmatter_raises(self, tmp_path: Path):
        """Raise ValueError when there is no YAML frontmatter."""
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(NO_FRONTMATTER_MD)

        from bifrost.skills.models import parse_skill_file

        with pytest.raises(ValueError, match="frontmatter"):
            parse_skill_file(str(skill_file))


# ===========================================================================
# Test: SkillsLoader — directory scanning
# ===========================================================================

class TestSkillsLoader:
    """Test SkillsLoader scan and loading."""

    def _create_skill_dir(self, base: Path, name: str, content: str) -> Path:
        """Helper: create a skill directory with SKILL.md."""
        skill_dir = base / name
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(content)
        return skill_dir

    def test_scan_directories(self, tmp_path: Path):
        """Scan public/ and custom/ dirs, find all SKILL.md files."""
        public = tmp_path / "public"
        custom = tmp_path / "custom"
        public.mkdir()
        custom.mkdir()

        self._create_skill_dir(public, "medical-research", VALID_SKILL_MD)
        self._create_skill_dir(public, "security-audit", SKILL_SECURITY)
        self._create_skill_dir(custom, "deployment", SKILL_DEPLOYMENT)

        from bifrost.skills.loader import SkillsLoader

        loader = SkillsLoader()
        skills = loader.scan([str(public), str(custom)])

        assert len(skills) == 3
        names = {s.name for s in skills}
        assert names == {"medical-research", "security-audit", "deployment"}

    def test_scan_empty_directory(self, tmp_path: Path):
        """Return empty list when directory has no skills."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        from bifrost.skills.loader import SkillsLoader

        loader = SkillsLoader()
        skills = loader.scan([str(empty_dir)])

        assert skills == []

    def test_scan_nonexistent_directory(self, tmp_path: Path):
        """Gracefully handle non-existent directory."""
        from bifrost.skills.loader import SkillsLoader

        loader = SkillsLoader()
        skills = loader.scan([str(tmp_path / "does-not-exist")])

        assert skills == []

    def test_scan_skips_invalid_skills(self, tmp_path: Path):
        """Skip SKILL.md files that fail to parse (no crash)."""
        public = tmp_path / "public"
        public.mkdir()

        self._create_skill_dir(public, "good-skill", VALID_SKILL_MD)
        self._create_skill_dir(public, "bad-skill", MISSING_NAME_MD)

        from bifrost.skills.loader import SkillsLoader

        loader = SkillsLoader()
        skills = loader.scan([str(public)])

        assert len(skills) == 1
        assert skills[0].name == "medical-research"


# ===========================================================================
# Test: Progressive loading — get relevant skills
# ===========================================================================

class TestProgressiveLoading:
    """Test skill relevance matching for progressive loading."""

    def _build_skills(self):
        """Build a list of SkillConfig objects for testing."""
        from bifrost.skills.models import SkillConfig

        return [
            SkillConfig(
                name="medical-research",
                description="Use for medical literature research and evidence synthesis.",
                tags=["medical", "research"],
                tools=["mimir_search"],
            ),
            SkillConfig(
                name="security-audit",
                description="Trigger for code security scanning and vulnerability assessment.",
                tags=["security", "audit"],
                tools=["huginn_scan"],
            ),
            SkillConfig(
                name="deployment",
                description="Use for deploying services and managing Docker containers.",
                tags=["devops", "deployment"],
                tools=["fenrir_execute"],
            ),
        ]

    def test_get_relevant_skills_by_keyword(self):
        """Match skills by keyword in description."""
        from bifrost.skills.loader import SkillsLoader

        loader = SkillsLoader()
        skills = self._build_skills()

        relevant = loader.get_relevant_skills("scan code for security vulnerabilities", skills)

        names = {s.name for s in relevant}
        assert "security-audit" in names

    def test_get_relevant_skills_by_tag(self):
        """Match skills by tag."""
        from bifrost.skills.loader import SkillsLoader

        loader = SkillsLoader()
        skills = self._build_skills()

        relevant = loader.get_relevant_skills("medical patient research", skills)

        names = {s.name for s in relevant}
        assert "medical-research" in names

    def test_get_relevant_skills_returns_empty_for_unrelated(self):
        """Return empty list when no skills match."""
        from bifrost.skills.loader import SkillsLoader

        loader = SkillsLoader()
        skills = self._build_skills()

        relevant = loader.get_relevant_skills("cook a pizza recipe", skills)

        assert relevant == []


# ===========================================================================
# Test: Prompt formatting
# ===========================================================================

class TestPromptFormatting:
    """Test rendering skills into system prompt."""

    def test_format_skills_prompt(self):
        """Render selected skills into a <skills> prompt block."""
        from bifrost.skills.models import SkillConfig
        from bifrost.skills.loader import SkillsLoader

        skills = [
            SkillConfig(
                name="medical-research",
                description="Medical literature research.",
                content="# Medical Research\n\n## Instructions\n1. Search PubMed\n2. Synthesize evidence",
            ),
        ]

        loader = SkillsLoader()
        prompt = loader.format_skills_prompt(skills)

        assert "<skills>" in prompt
        assert "</skills>" in prompt
        assert "medical-research" in prompt
        assert "# Medical Research" in prompt
        assert "Search PubMed" in prompt

    def test_format_skills_prompt_empty(self):
        """Return empty string when no skills are provided."""
        from bifrost.skills.loader import SkillsLoader

        loader = SkillsLoader()
        prompt = loader.format_skills_prompt([])

        assert prompt == ""
