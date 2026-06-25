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
KB_SYNC_TAG_RE = re.compile(
    r"^<!--\s*kb-sync(?:\s*:\s*(?P<override>[^\n]*?))?\s*-->\s*$",
    re.IGNORECASE,
)
HEADING_LINE_RE = re.compile(r"^(?P<level>#{2,4})\s+(?P<text>.+?)\s*$")
APOSTROPHE_RE = re.compile(r"[''\u2019]")


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


@dataclass(frozen=True, slots=True)
class _SectionStart:
    """Internal marker for the beginning of one extractable section."""

    position: int
    content_start: int
    title: str
    heading: str


def slugify_title(title: str) -> str:
    """Return a knowledge-base filename stem (lowercase, hyphenated).

    Apostrophes are removed (not turned into hyphens), so ``user's`` becomes
    ``users`` in the slug.

    Args:
        title: The how-to title without the leading "How do I".

    Returns:
        A slug suitable for ``<slug>.md`` per CONTRIBUTING.md.
    """
    cleaned = title.strip().rstrip("?")
    cleaned = APOSTROPHE_RE.sub("", cleaned)
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


def _title_from_heading_text(heading_text: str) -> str:
    match = re.match(r"^How do I\s+(.+?)\?\s*$", heading_text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return heading_text.strip()


def _find_tagged_section_starts(text: str) -> list[_SectionStart]:
    """Return section starts declared with ``<!-- kb-sync -->`` above a heading."""
    lines = text.splitlines(keepends=True)
    if not lines:
        return []

    offsets: list[int] = []
    pos = 0
    for line in lines:
        offsets.append(pos)
        pos += len(line)

    starts: list[_SectionStart] = []
    index = 0
    while index < len(lines):
        tag_match = KB_SYNC_TAG_RE.match(lines[index].strip())
        if tag_match:
            heading_index = index + 1
            while heading_index < len(lines) and not lines[heading_index].strip():
                heading_index += 1
            if heading_index < len(lines):
                heading_match = HEADING_LINE_RE.match(lines[heading_index].strip())
                if heading_match:
                    heading_line = lines[heading_index].strip()
                    heading_text = heading_match.group("text").strip()
                    if HOW_TO_HEADING_RE.match(heading_line):
                        index = heading_index + 1
                        continue
                    override = (tag_match.group("override") or "").strip()
                    title = override or _title_from_heading_text(heading_text)
                    content_start = offsets[heading_index] + len(lines[heading_index])
                    starts.append(
                        _SectionStart(
                            position=offsets[index],
                            content_start=content_start,
                            title=title,
                            heading=heading_line,
                        )
                    )
                    index = heading_index + 1
                    continue
        index += 1
    return starts


def _find_section_starts(text: str) -> list[_SectionStart]:
    """Collect standard and tagged how-to section boundaries."""
    starts: list[_SectionStart] = []
    for match in HOW_TO_HEADING_RE.finditer(text):
        title = match.group("title").strip()
        starts.append(
            _SectionStart(
                position=match.start(),
                content_start=match.end(),
                title=title,
                heading=match.group(0).strip(),
            )
        )

    starts.extend(_find_tagged_section_starts(text))
    return sorted(starts, key=lambda item: item.position)


def _intro_before_first_section(text: str, starts: list[_SectionStart]) -> str:
    if not starts:
        return ""
    prefix = text[: starts[0].position].strip()
    lines = prefix.splitlines()
    if lines and lines[0].startswith("# "):
        prefix = "\n".join(lines[1:]).strip()
    return prefix


def extract_how_tos_from_file(path: Path) -> SourceDocument:
    """Parse one markdown file and return its how-to sections.

    Sections are included when the heading matches ``How do I …?`` or when an
    HTML comment tag ``<!-- kb-sync -->`` appears on the line immediately above
    a ``##``–``####`` heading. An optional override title may be supplied as
    ``<!-- kb-sync: Custom KB title -->``.

    Args:
        path: Path to a ``docs/source`` markdown file.

    Returns:
        A ``SourceDocument`` with zero or more ``HowToSection`` items.
    """
    text = path.read_text(encoding="utf-8")
    starts = _find_section_starts(text)
    how_tos: list[HowToSection] = []
    for index, start in enumerate(starts):
        end = starts[index + 1].position if index + 1 < len(starts) else len(text)
        body = text[start.content_start : end].strip()
        how_tos.append(
            HowToSection(
                title=start.title,
                body=body,
                heading=start.heading,
                source_file=path,
                anchor=anchor_for_title(start.title),
            )
        )
    return SourceDocument(
        path=path,
        page_title=_page_title(text),
        intro=_intro_before_first_section(text, starts),
        how_tos=tuple(how_tos),
    )


def collect_how_tos(paths: list[Path]) -> list[HowToSection]:
    """Extract how-tos from multiple source files."""
    sections: list[HowToSection] = []
    for path in paths:
        doc = extract_how_tos_from_file(path)
        sections.extend(doc.how_tos)
    return sections
