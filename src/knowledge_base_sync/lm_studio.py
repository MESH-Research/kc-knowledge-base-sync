# Copyright (C) 2026 MESH Research
#
# kc-knowledge-base-sync is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.

"""Optional LM Studio (OpenAI-compatible) formatting pass."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import requests

from knowledge_base_sync.extract import HowToSection

DEFAULT_BASE_URL = "http://localhost:1234/v1"


@dataclass(frozen=True, slots=True)
class LMStudioConfig:
    """Connection settings for a local LM Studio server."""

    base_url: str = DEFAULT_BASE_URL
    model: str = ""
    api_key: str = "lm-studio"
    temperature: float = 0.2
    timeout_seconds: int = 300


def _build_prompt(
    section: HowToSection,
    template: str,
    secrets_policy: str,
    page_intro: str = "",
) -> str:
    return f"""You are converting KCWorks administrator documentation into a
knowledge-base how-to article.

Follow the template structure exactly. Output ONLY the finished markdown article.
Do not wrap the answer in a code fence.

Rules:
- Title (`#` heading): short imperative phrase. No "How to" or "How do I" prefix.
- Include Summary, Audience, Last reviewed, Owner, and Keywords in the blockquote metadata.
- Use today's date for Last reviewed: {date.today().isoformat()}.
- Owner: _unassigned_
- Audience: Developers / ops
- Never include passwords, API keys, tokens, or connection strings with embedded passwords.
- Hostnames, ports, usernames, and container commands are fine.
- Convert MyST admonitions like ```{{note}}``` into the "Notes & gotchas" section.
- Rewrite relative doc links to plain-language references; do not link to kcworks-next paths.
- Keep shell commands copy-pasteable inside fenced ```bash blocks.
- End with a "## Related" section pointing to internal/works-maintenance README.

SECRETS POLICY:
{secrets_policy}

TEMPLATE:
{template}

PARENT PAGE INTRO (shared context; fold into "Before you start" if relevant):
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
        knowledge_base_root: Path to the cloned knowledge-base repo.
        page_intro: Shared intro from the parent docs page.

    Returns:
        Formatted markdown article text.

    Raises:
        RuntimeError: When the API call fails or returns empty content.
        ValueError: When the model output fails basic validation.
    """
    template = (knowledge_base_root / "templates/how-to-template.md").read_text(
        encoding="utf-8"
    )
    secrets = (knowledge_base_root / "SECRETS.md").read_text(encoding="utf-8")
    prompt = _build_prompt(section, template, secrets, page_intro=page_intro)

    if not config.model:
        models_resp = requests.get(
            f"{config.base_url.rstrip('/')}/models",
            timeout=30,
        )
        models_resp.raise_for_status()
        models = models_resp.json().get("data", [])
        if not models:
            raise RuntimeError("LM Studio returned no models; load one in the server UI.")
        model = models[0]["id"]
    else:
        model = config.model

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You write concise internal ops runbooks in markdown. "
                    "Output only the article markdown."
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
    lowered = text.lower()
    for forbidden in ("password=", "api_key=", "secret=", "bearer "):
        if forbidden in lowered:
            raise ValueError(f"Formatted article appears to contain a secret ({forbidden!r}).")
