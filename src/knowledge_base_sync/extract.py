# Copyright (C) 2026 MESH Research
#
# kc-knowledge-base-sync is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.

"""Extract discrete how-to sections from KCWorks docs/source markdown."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

HOW_TO_HEADING_RE = re.compile(
    r"^(?P<level>#{2,4})\s+How do I\s+(?P<title>.+?)\?\s*$",
    re.MULTILINE | re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class HowToSection:
    """One admin-guide how-to extracted from a source markdown file."""

    title: str
    body: str
    heading: str
    source_file: Path
    anchor: str

    @property
    def kb_title(self) -> str:
        """Imperative title for the knowledge-base `#` heading (no 'How do I')."""
        return self.title[0].upper() + self.title[1:] if self.title else self.title


def slugify_title(title: str) -> str:
    """Return a knowledge-base filename stem (lowercase, hyphenated).

    Args:
        title: The how-to title without the leading "How do I".

    Returns:
        A slug suitable for ``<slug>.md`` per CONTRIBUTING.md.
    """
    cleaned = title.strip().rstrip("?")
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", cleaned.lower())
    return cleaned.strip("-")


def anchor_for_title(title: str) -> str:
    """Return a GitHub-style markdown anchor for a how-to title."""
    slug = slugify_title(f"how-do-i-{title}")
    return slug


@dataclass(frozen=True, slots=True)
class SourceDocument:
    """A parsed docs/source markdown file."""

    path: Path
    page_title: str
    intro: str
    how_tos: tuple[HowToSection, ...]


def _page_title(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return ""


def _intro_before_first_how_to(text: str) -> str:
    match = HOW_TO_HEADING_RE.search(text)
    if not match:
        return ""
    prefix = text[: match.start()].strip()
    lines = prefix.splitlines()
    if lines and lines[0].startswith("# "):
        prefix = "\n".join(lines[1:]).strip()
    return prefix


def extract_how_tos_from_file(path: Path) -> SourceDocument:
    """Parse one markdown file and return its how-to sections.

    Args:
        path: Path to a ``docs/source`` markdown file.

    Returns:
        A ``SourceDocument`` with zero or more ``HowToSection`` items.
    """
    text = path.read_text(encoding="utf-8")
    matches = list(HOW_TO_HEADING_RE.finditer(text))
    how_tos: list[HowToSection] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        title = match.group("title").strip()
        how_tos.append(
            HowToSection(
                title=title,
                body=body,
                heading=match.group(0).strip(),
                source_file=path,
                anchor=anchor_for_title(title),
            )
        )
    return SourceDocument(
        path=path,
        page_title=_page_title(text),
        intro=_intro_before_first_how_to(text),
        how_tos=tuple(how_tos),
    )


def collect_how_tos(paths: list[Path]) -> list[HowToSection]:
    """Extract how-tos from multiple source files."""
    sections: list[HowToSection] = []
    for path in paths:
        doc = extract_how_tos_from_file(path)
        sections.extend(doc.how_tos)
    return sections
