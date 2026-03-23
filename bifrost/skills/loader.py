"""Skills loader — scan directories, progressive loading, prompt injection.

Follows DeerFlow pattern: skills are loaded progressively — only when the
task needs them, not all at once. This keeps the context window lean.
"""

import logging
from pathlib import Path

from bifrost.skills.models import SkillConfig, parse_skill_file

logger = logging.getLogger("bifrost.skills")


class SkillsLoader:
    """Scan, filter, and format skills for agent system prompts."""

    def scan(self, directories: list[str]) -> list[SkillConfig]:
        """Walk directories and parse all valid SKILL.md files.

        Each skill lives in its own sub-directory:
            skills/public/medical-research/SKILL.md
            skills/custom/my-skill/SKILL.md

        Invalid or broken SKILL.md files are skipped with a warning.

        Args:
            directories: List of directory paths to scan.

        Returns:
            List of successfully parsed SkillConfig objects.
        """
        skills: list[SkillConfig] = []

        for dir_path in directories:
            base = Path(dir_path)
            if not base.exists() or not base.is_dir():
                logger.warning(f"Skills directory not found: {dir_path}")
                continue

            for skill_file in sorted(base.rglob("SKILL.md")):
                try:
                    skill = parse_skill_file(str(skill_file))
                    skills.append(skill)
                    logger.debug(f"Loaded skill: {skill.name} from {skill_file}")
                except (ValueError, FileNotFoundError) as e:
                    logger.warning(f"Skipping invalid skill: {skill_file} — {e}")

        return skills

    def get_relevant_skills(
        self,
        task_description: str,
        all_skills: list[SkillConfig],
    ) -> list[SkillConfig]:
        """Filter skills relevant to the given task description.

        Uses keyword matching against skill name, description, and tags.
        This is the "progressive loading" mechanism — only inject skills
        that match the current task to keep context window lean.

        Args:
            task_description: Natural language description of the task.
            all_skills: All available skills.

        Returns:
            List of matching skills, sorted by relevance score (desc).
        """
        if not task_description or not all_skills:
            return []

        task_lower = task_description.lower()
        task_words = set(task_lower.split())

        scored: list[tuple[float, SkillConfig]] = []

        for skill in all_skills:
            score = 0.0

            # Match against skill name
            name_words = set(skill.name.lower().replace("-", " ").split())
            name_overlap = task_words & name_words
            score += len(name_overlap) * 3.0

            # Match against description
            desc_words = set(skill.description.lower().split())
            desc_overlap = task_words & desc_words
            # Filter out common stop words
            stop_words = {"use", "this", "for", "and", "the", "a", "an", "is", "to", "of", "in", "on", "trigger"}
            meaningful_overlap = desc_overlap - stop_words
            score += len(meaningful_overlap) * 2.0

            # Match against tags
            for tag in skill.tags:
                if tag.lower() in task_lower:
                    score += 4.0

            if score > 0:
                scored.append((score, skill))

        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)
        return [skill for _, skill in scored]

    def format_skills_prompt(self, skills: list[SkillConfig]) -> str:
        """Render selected skills into a <skills> prompt block.

        Format:
            <skills>
            <skill name="skill-name">
            [markdown content]
            </skill>
            </skills>

        Args:
            skills: Skills to include in the prompt.

        Returns:
            Formatted prompt string, or empty string if no skills.
        """
        if not skills:
            return ""

        parts = ["<skills>"]
        for skill in skills:
            parts.append(f'<skill name="{skill.name}">')
            if skill.content:
                parts.append(skill.content)
            else:
                # Fallback: use description if no content body
                parts.append(f"# {skill.name}\n\n{skill.description}")
            parts.append("</skill>")
        parts.append("</skills>")

        return "\n".join(parts)
