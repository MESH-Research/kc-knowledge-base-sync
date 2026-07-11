# Copyright (C) 2026 MESH Research
#
# kc-knowledge-base-sync is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.

"""Optional LM Studio (OpenAI-compatible) formatting pass."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from importlib import resources
from pathlib import Path

import requests

from knowledge_base_sync.extract import HowToSection

DEFAULT_BASE_URL = "http://localhost:1234/v1"

REQUIRED_OUTLINE = """\
# <title>

> **Summary:** <one sentence — metadata only>
> **Audience:** … · **Last reviewed:** … · **Owner:** …
> **Keywords:** …

## Overview
<opening narrative paragraphs from source, before ### subsections or step lists>

## Before you start
<bulleted prerequisites only>

## Steps
<### subsection per distinct task, when present in source>
<narrative paragraphs verbatim, immediately before the steps/commands they introduce>
<numbered steps and/or fenced code blocks>

## Notes & gotchas
<admonitions and cautions>

## Related
<links>
"""


@dataclass(frozen=True, slots=True)
class LMStudioConfig:
    """Connection settings for a local LM Studio server."""

    base_url: str = DEFAULT_BASE_URL
    model: str = ""
    api_key: str = "lm-studio"
    temperature: float = 0.2
    timeout_seconds: int = 300


def load_how_to_template() -> str:
    """Load the bundled KCWorks how-to template used for LLM formatting.

    Returns:
        Template markdown shipped with this package (not the knowledge-base
        repo copy).
    """
    return (
        resources.files("knowledge_base_sync")
        .joinpath("templates/how-to-template.md")
        .read_text(encoding="utf-8")
    )


def _build_prompt(
    section: HowToSection,
    template: str,
    secrets_policy: str,
    page_intro: str = "",
) -> str:
    return f"""You are reformatting KCWorks administrator documentation into a
knowledge-base how-to article. This is a layout pass, not a rewrite.

Output ONLY the finished markdown article. Do not wrap the answer in a code fence.

REQUIRED DOCUMENT OUTLINE (use these section headings in this order; omit
Overview only when SOURCE BODY has no opening narrative before subsections or
steps):

{REQUIRED_OUTLINE}

Layout rules:
- Title (`#` heading): short imperative phrase. No "How to" or "How do I" prefix.
- Blockquote metadata: include Summary, Audience, Last reviewed, Owner, Keywords.
- Use today's date for Last reviewed: {date.today().isoformat()}.
- Owner: _unassigned_
- Audience: Developers / ops
- Two different "summary" roles:
  - Blockquote **Summary:** exactly one sentence for metadata.
  - **## Overview:** all opening narrative paragraphs from SOURCE BODY that appear
    before the first `###` subsection or before the first numbered/bulleted step
    list. Copy verbatim. Do not fold Overview into the blockquote or Before you start.
- **## Before you start:** bulleted prerequisites only (from PARENT PAGE INTRO and
  explicit prereqs in the source). No procedural narrative or steps here.
- **## Steps:** preserve the source structure:
  - Use `###` headings for each distinct task group present in the source.
  - Place narrative paragraphs verbatim immediately before the numbered list or
    code block they introduce. Never jump from `## Steps` or `###` straight to
    `1.` when the source has explanatory prose in between.
  - When the source has multiple task groups, keep each as its own `###` block.
- Preserve procedural accuracy: steps, commands, flags, file paths, and warning
  text from SOURCE BODY verbatim unless a rule below requires a mechanical change.
- Do not omit, merge, summarize, or paraphrase steps, notes, or cautions.
- Do not invent prerequisites, steps, or warnings that are not in the source.
- Convert MyST admonitions like ```{{note}}``` into **Notes & gotchas** without
  changing their substance or wording.
- Replace relative doc links with paths under
  https://mesh-research.github.io/knowledge-commons-works/ . Keep the same referent.
- Keep code blocks and shell commands copy-pasteable inside fenced ```bash blocks.
  Keep multiple related commands on separate lines inside the same fenced block.
- Never include passwords, API keys, tokens, or connection strings with embedded
  passwords. Hostnames, ports, usernames, and container commands are fine.
- End **Related** with a link to internal/works-maintenance README.

SECRETS POLICY:
{secrets_policy}

TEMPLATE (annotated example — follow structure, not placeholder text):
{template}

PARENT PAGE INTRO (prerequisites for Before you start only):
{page_intro or "(none)"}

SOURCE HEADING:
{section.heading}

SOURCE BODY:
{section.body}
"""


def format_with_lm_studio(
    section: HowToSection,
    *,
    config: LMStudioConfig,
    knowledge_base_root: Path,
    page_intro: str = "",
) -> str:
    """Call LM Studio to format one how-to section.

    Args:
        section: Extracted section to format.
        config: LM Studio connection settings.
        knowledge_base_root: Path to the cloned knowledge-base repo (for
            ``SECRETS.md`` policy text).
        page_intro: Shared intro from the parent docs page.

    Returns:
        Formatted markdown article text.

    Raises:
        RuntimeError: When the API call fails or returns empty content.
        ValueError: When the model output fails basic validation.
    """
    template = load_how_to_template()
    secrets_path = knowledge_base_root / "SECRETS.md"
    if secrets_path.is_file():
        secrets = secrets_path.read_text(encoding="utf-8")
    else:
        secrets = (
            "Do not include passwords, API keys, tokens, or connection strings "
            "with embedded passwords."
        )
    prompt = _build_prompt(section, template, secrets, page_intro=page_intro)

    if not config.model:
        models_resp = requests.get(
            f"{config.base_url.rstrip('/')}/models",
            timeout=30,
        )
        models_resp.raise_for_status()
        models = models_resp.json().get("data", [])
        if not models:
            raise RuntimeError(
                "LM Studio returned no models; load one in the server UI."
            )
        model = models[0]["id"]
    else:
        model = config.model

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You reformat existing KCWorks ops documentation into knowledge-base "
                    "markdown. Preserve source wording and procedural detail; change "
                    "section layout only. Output only the article markdown."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": config.temperature,
    }
    response = requests.post(
        f"{config.base_url.rstrip('/')}/chat/completions",
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        },
        data=json.dumps(payload),
        timeout=config.timeout_seconds,
    )
    response.raise_for_status()
    data = response.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Unexpected LM Studio response: {data!r}") from exc

    content = content.strip()
    if content.startswith("```"):
        content = re_strip_fence(content)

    validate_kb_markdown(content)
    sync_line = (
        f"\n\n<!-- synced-from: kcworks-next/{section.source_file.as_posix()}"
        f"#{section.anchor} -->"
    )
    if sync_line.strip() not in content:
        content += sync_line
    return content.rstrip() + "\n"


def re_strip_fence(text: str) -> str:
    """Remove a single outer markdown code fence if the model added one."""
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def validate_kb_markdown(text: str) -> None:
    """Raise ValueError when required knowledge-base fields are missing."""
    if not text.startswith("# "):
        raise ValueError("Formatted article must start with a `#` title line.")
    if "**Summary:**" not in text:
        raise ValueError("Formatted article must include a Summary metadata line.")
    for heading in ("## Before you start", "## Steps"):
        if heading not in text:
            raise ValueError(f"Formatted article must include `{heading}`.")
    lowered = text.lower()
    for forbidden in ("password=", "api_key=", "secret=", "bearer "):
        if forbidden in lowered:
            raise ValueError(
                f"Formatted article appears to contain a secret ({forbidden!r})."
            )
