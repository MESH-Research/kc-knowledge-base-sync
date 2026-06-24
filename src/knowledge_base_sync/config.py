# Copyright (C) 2026 MESH Research
#
# kc-knowledge-base-sync is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.

"""Load YAML configuration for knowledge-base publishing."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from knowledge_base_sync.lm_studio import DEFAULT_BASE_URL, LMStudioConfig


@dataclass(frozen=True, slots=True)
class SourceMapping:
    """One docs/source folder or file list mapped to a KB topic directory."""

    docs_paths: tuple[Path, ...]
    kb_topic: str
    filename_prefix: str = ""
    extra_keywords: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SyncConfig:
    """Full configuration for a publish run."""

    kcworks_root: Path
    knowledge_base_root: Path
    sources: tuple[SourceMapping, ...]
    audience: str = "Developers / ops"
    owner: str = "_unassigned_"
    lm_studio: LMStudioConfig = field(default_factory=LMStudioConfig)
    branch_prefix: str = "kb-sync"
    pr_base: str = "main"


def _expand_docs_paths(kcworks_root: Path, entry: dict) -> tuple[Path, ...]:
    docs_dir = kcworks_root / entry["docs_dir"]
    if "files" in entry:
        return tuple(docs_dir / name for name in entry["files"])
    return tuple(sorted(docs_dir.glob("*.md")))


def load_config(path: Path, *, kcworks_root: Path | None = None) -> SyncConfig:
    """Load a YAML config file.

    Args:
        path: Path to the YAML config.
        kcworks_root: Override the repo root (defaults to config value or cwd).

    Returns:
        Parsed ``SyncConfig``.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    config_dir = path.parent.resolve()
    kc_root_raw = raw.get("kcworks_root") or kcworks_root or Path.cwd()
    kc_root = Path(kc_root_raw).expanduser()
    if not kc_root.is_absolute():
        kc_root = (config_dir / kc_root).resolve()
    else:
        kc_root = kc_root.resolve()
    kb_root = Path(raw["knowledge_base_path"]).expanduser()

    lm_raw = raw.get("lm_studio") or {}
    lm_config = LMStudioConfig(
        base_url=lm_raw.get("base_url", DEFAULT_BASE_URL),
        model=lm_raw.get("model", ""),
        api_key=lm_raw.get("api_key", "lm-studio"),
        temperature=float(lm_raw.get("temperature", 0.2)),
        timeout_seconds=int(lm_raw.get("timeout_seconds", 300)),
    )

    sources: list[SourceMapping] = []
    for entry in raw.get("sources", []):
        sources.append(
            SourceMapping(
                docs_paths=_expand_docs_paths(kc_root, entry),
                kb_topic=entry["kb_topic"],
                filename_prefix=entry.get("filename_prefix", ""),
                extra_keywords=tuple(entry.get("extra_keywords", [])),
            )
        )

    return SyncConfig(
        kcworks_root=kc_root,
        knowledge_base_root=kb_root,
        sources=tuple(sources),
        audience=raw.get("audience", "Developers / ops"),
        owner=raw.get("owner", "_unassigned_"),
        lm_studio=lm_config,
        branch_prefix=raw.get("branch_prefix", "kb-sync"),
        pr_base=raw.get("pr_base", "main"),
    )
