# Copyright (C) 2026 MESH Research
#
# kc-knowledge-base-sync is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.

"""Format extracted how-tos into knowledge-base markdown."""

from __future__ import annotations

import re
from datetime import date
from textwrap import dedent

from knowledge_base_sync.extract import HowToSection, slugify_title

MYST_ADMON_RE = re.compile(
    r"```\{(?P<kind>note|important|danger|warning)\}\s*(?P<title>[^\n]*)\n"
    r"(?P<body>.*?)\n```",
    re.DOTALL,
)
RELATIVE_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def _strip_myst_admonitions(text: str) -> tuple[str, list[str]]:
    notes: list[str] = []

    def repl(match: re.Match[str]) -> str:
        kind = match.group("kind")
        title = match.group("title").strip()
        body = match.group("body").strip()
        label = title or kind.capitalize()
        notes.append(f"**{label}:** {body}")
        return ""

    cleaned = MYST_ADMON_RE.sub(repl, text)
    return cleaned.strip(), notes


def _rewrite_links(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        label = match.group(1)
        href = match.group(2)
        if href.startswith("http://") or href.startswith("https://"):
            return match.group(0)
        if "running_commands" in href:
            return (
                f"{label} (open an interactive shell in the KCWorks UI app "
                "container on the target instance)"
            )
        if href.startswith("#"):
            return label
        return label

    return RELATIVE_LINK_RE.sub(repl, text)


def _first_summary_sentence(section: HowToSection) -> str:
    for paragraph in re.split(r"\n\s*\n", section.body):
        stripped = paragraph.strip()
        if not stripped or stripped.startswith("```") or stripped.startswith("#"):
            continue
        if stripped.startswith("- ") or re.match(r"^\d+\.", stripped):
            continue
        sentence = stripped.split("\n")[0].strip()
        return sentence.rstrip(".") + "."
    return f"Perform: {section.kb_title.lower()}."


def _keywords(section: HowToSection, extra: list[str] | None = None) -> str:
    words = re.findall(r"[a-zA-Z]{3,}", section.kb_title.lower())
    tokens = sorted(set(words + (extra or [])))
    return ", ".join(tokens)


def _split_steps_and_notes(body: str) -> tuple[str, list[str]]:
    cleaned, admon_notes = _strip_myst_admonitions(body)
    cleaned = _rewrite_links(cleaned)
    trailing_notes: list[str] = []
    if "### " in cleaned:
        parts = re.split(r"\n(?=### )", cleaned)
        main = parts[0].strip()
        for part in parts[1:]:
            trailing_notes.append(part.strip())
        cleaned = main
    return cleaned.strip(), admon_notes + trailing_notes


def format_deterministic(
    section: HowToSection,
    *,
    audience: str = "Developers / ops",
    owner: str = "_unassigned_",
    reviewed: date | None = None,
    extra_keywords: list[str] | None = None,
    page_intro: str = "",
) -> str:
    """Render a knowledge-base article without calling an LLM.

    Args:
        section: Extracted how-to section.
        audience: Value for the metadata line.
        owner: GitHub handle or ``_unassigned_``.
        reviewed: ``Last reviewed`` date; defaults to today.
        extra_keywords: Additional search keywords.
        page_intro: Shared intro text from the parent page (e.g. container access).

    Returns:
        Markdown formatted per ``templates/how-to-template.md``.
    """
    reviewed = reviewed or date.today()
    summary = _first_summary_sentence(section)
    steps_body, note_blocks = _split_steps_and_notes(section.body)

    prerequisites: list[str] = []
    if page_intro:
        for line in page_intro.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                prerequisites.append(stripped.lstrip("- ").strip())

    before_you_start = dedent(
        """\
        - Access to the KCWorks UI app container on the target instance (staging or production).
        - Ability to run ``invenio`` CLI commands inside that container.
        """
    ).strip()
    if prerequisites:
        before_you_start = "\n".join(f"- {p}" for p in prerequisites[:3])

    notes_section = ""
    if note_blocks:
        notes_section = "## Notes & gotchas\n\n" + "\n\n".join(
            f"- {block}" for block in note_blocks
        )

    related = dedent(
        f"""\
        ## Related

        - Other KCWorks runbooks under [internal/works-maintenance](README.md).
        - Source: ``kcworks-next/{section.source_file.as_posix()}`` (KCWorks technical docs).
        """
    ).strip()

    sync_comment = (
        f"<!-- synced-from: kcworks-next/{section.source_file.as_posix()}"
        f"#{section.anchor} -->"
    )

    return dedent(
        f"""\
        # {section.kb_title}

        > **Summary:** {summary}
        > **Audience:** {audience} · **Last reviewed:** {reviewed.isoformat()} · **Owner:** {owner}
        > **Keywords:** {_keywords(section, extra_keywords)}

        ## Before you start

        {before_you_start}

        ## Steps

        {steps_body}

        {notes_section}

        {related}

        {sync_comment}
        """
    ).strip() + "\n"


def output_path_for_section(
    section: HowToSection,
    kb_topic_dir: str,
    *,
    filename_prefix: str = "",
) -> str:
    """Return the destination path relative to the knowledge-base repo root."""
    slug = slugify_title(section.title)
    filename = f"{filename_prefix}{slug}.md"
    return f"{kb_topic_dir.rstrip('/')}/{filename}"
