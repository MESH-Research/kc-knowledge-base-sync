# kc-knowledge-base-sync

Extract `## How do I …?` sections from KCWorks `docs/source` markdown and publish
one article per section to the [MESH knowledge-base](https://github.com/MESH-Research/knowledge-base)
repository.

## Install

From GitHub (once the repository is published):

```bash
uv add --dev kc-knowledge-base-sync \
  --index https://pypi.org/simple \
  # or in pyproject.toml:
  # [tool.uv.sources]
  # kc-knowledge-base-sync = { git = "https://github.com/MESH-Research/kc-knowledge-base-sync.git" }
```

Editable install from a local checkout:

```bash
uv pip install -e /path/to/kc-knowledge-base-sync
```

## Usage

```bash
kb-sync --config path/to/config.yaml --dry-run
kb-sync --config path/to/config.yaml --force
kb-sync --config path/to/config.yaml --use-llm --force --commit --pr
```

See `config.example.yaml` for configuration fields. In kcworks-next, copy
`docs/knowledge_base_sync/config.example.yaml` to `config.yaml` and adjust paths.

### Flags

| Flag | Description |
|------|-------------|
| `--dry-run` | List planned output paths; do not write files or touch git |
| `--use-llm` | Call LM Studio instead of the built-in formatter |
| `--force` | Overwrite existing destination articles |
| `--commit` | Create a branch, run `build_index.py`, and commit in the KB repo |
| `--branch NAME` | Branch name for `--commit` (default `kb-sync/YYYY-MM-DD`) |
| `--pr` | Push branch and run `gh pr create` (requires `--commit`) |

## Prerequisites

- A local clone of the knowledge-base repository.
- `uv` on your PATH (used to rebuild indexes in the knowledge-base repo).
- For `--pr`: the GitHub CLI (`gh`) authenticated for `MESH-Research/knowledge-base`.
- For `--use-llm`: [LM Studio](https://lmstudio.ai/) serving an OpenAI-compatible API.
