"""Skill data model and SKILL.md parser.

SKILL.md format (DeerFlow-compatible):
    ---
    name: skill-name          # required
    description: ...          # required
    version: "1.0"            # optional
    author: asgard-team       # optional
    tags: [tag1, tag2]        # optional
    tools: [tool1, tool2]     # optional
    ---

    # Skill Name
    Markdown body with instructions...
"""

from dataclasses import dataclass, field


@dataclass
class SkillConfig:
    """Parsed skill configuration from a SKILL.md file."""

    name: str = ""
    description: str = ""
    version: str = ""
    author: str = ""
    tags: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    content: str = ""  # Markdown body (after frontmatter)
    path: str = ""  # Source file path

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "tags": self.tags,
            "tools": self.tools,
            "content": self.content,
            "path": self.path,
        }


def _split_frontmatter(text: str) -> tuple[str, str]:
    """Split YAML frontmatter from markdown body.

    Returns (frontmatter_yaml, body_markdown).
    Raises ValueError if no valid frontmatter delimiters found.
    """
    stripped = text.strip()
    if not stripped.startswith("---"):
        raise ValueError("SKILL.md must start with YAML frontmatter (---)")

    # Find closing ---
    second_sep = stripped.find("---", 3)
    if second_sep == -1:
        raise ValueError("SKILL.md must start with YAML frontmatter (---)")

    frontmatter = stripped[3:second_sep].strip()
    body = stripped[second_sep + 3:].strip()
    return frontmatter, body


def _parse_yaml_simple(yaml_text: str) -> dict:
    """Minimal YAML parser for frontmatter — handles scalars and lists.

    Avoids PyYAML dependency. Supports:
      key: value
      key: [item1, item2]
      key: "quoted value"
    """
    result = {}
    for line in yaml_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue

        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()

        # Remove surrounding quotes
        if (value.startswith('"') and value.endswith('"')) or \
           (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]

        # Parse inline list: [item1, item2]
        if value.startswith("[") and value.endswith("]"):
            items = value[1:-1]
            if items.strip():
                result[key] = [
                    item.strip().strip('"').strip("'")
                    for item in items.split(",")
                ]
            else:
                result[key] = []
        else:
            result[key] = value

    return result


def parse_skill_file(path: str) -> SkillConfig:
    """Parse a SKILL.md file into a SkillConfig.

    Args:
        path: Path to the SKILL.md file.

    Returns:
        SkillConfig with parsed data.

    Raises:
        ValueError: If frontmatter is missing or required fields absent.
        FileNotFoundError: If the file does not exist.
    """
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    frontmatter_yaml, body = _split_frontmatter(text)
    meta = _parse_yaml_simple(frontmatter_yaml)

    # Validate required fields
    if "name" not in meta or not meta["name"]:
        raise ValueError(f"SKILL.md missing required field 'name': {path}")
    if "description" not in meta or not meta["description"]:
        raise ValueError(f"SKILL.md missing required field 'description': {path}")

    return SkillConfig(
        name=meta["name"],
        description=meta["description"],
        version=meta.get("version", ""),
        author=meta.get("author", ""),
        tags=meta.get("tags", []) if isinstance(meta.get("tags"), list) else [],
        tools=meta.get("tools", []) if isinstance(meta.get("tools"), list) else [],
        content=body,
        path=path,
    )
