# kc-knowledge-base-sync

Sync KCWorks administrator how-tos from `docs/source` markdown into the
[MESH knowledge-base](https://github.com/MESH-Research/knowledge-base) repository.

- **Repository:** [github.com/MESH-Research/kc-knowledge-base-sync](https://github.com/MESH-Research/kc-knowledge-base-sync)
- **CLI command:** `kb-sync`
- **Python package:** `kc-knowledge-base-sync` (import name `knowledge_base_sync`)
- **License:** MIT

In [kcworks-next](https://github.com/MESH-Research/kcworks-next), this package is
included as a git submodule at
`site/kcworks/dependencies/kc-knowledge-base-sync` and installed as a **dev-only**
dependency via `uv`.

## What it does

1. Scans configured markdown files under `docs/source` (typically the admin guide).
2. Extracts discrete how-to sections (see [Section extraction](#section-extraction)).
3. Formats each section as a knowledge-base article (deterministic converter or optional LM Studio pass).
4. Writes one `.md` file per section into your local knowledge-base clone.
5. Optionally rebuilds indexes, commits, and opens a pull request in the knowledge-base repo.

Each generated file ends with an HTML comment recording the kcworks-next source path
and anchor.

## Prerequisites

- [uv](https://github.com/astral-sh/uv) on your PATH
- A local clone of the [knowledge-base](https://github.com/MESH-Research/knowledge-base) repository
- For `--pr`: [GitHub CLI](https://cli.github.com/) (`gh`) authenticated for `MESH-Research/knowledge-base`
- For `--use-llm`: [LM Studio](https://lmstudio.ai/) (or any OpenAI-compatible API) reachable from your machine

## Installation

### In kcworks-next (recommended)

From the kcworks-next repository root:

```bash
git submodule update --init site/kcworks/dependencies/kc-knowledge-base-sync
uv sync --group dev
```

The submodule is wired in `pyproject.toml` as an editable path dependency:

```toml
[dependency-groups]
dev = [
  "kc-knowledge-base-sync",
  # ...
]

[tool.uv.sources]
kc-knowledge-base-sync = { path = "./site/kcworks/dependencies/kc-knowledge-base-sync", editable = true }
```

### Standalone checkout

```bash
git clone https://github.com/MESH-Research/kc-knowledge-base-sync.git
cd kc-knowledge-base-sync
uv pip install -e .
```

Or add as a git dependency in another project:

```toml
[tool.uv.sources]
kc-knowledge-base-sync = { git = "https://github.com/MESH-Research/kc-knowledge-base-sync.git" }
```

## Configuration

### kcworks-next

Copy the example config and adjust paths for your machine:

```bash
cp docs/knowledge_base_sync/config.example.yaml docs/knowledge_base_sync/config.yaml
```

`docs/knowledge_base_sync/config.yaml` is gitignored. When you run `kb-sync` from
the kcworks-next root, this file is the **default** config (no `--config` flag needed).

Key fields:

| Field | Description |
|-------|-------------|
| `kcworks_root` | Path to the kcworks-next repository root |
| `knowledge_base_path` | Path to your local knowledge-base clone |
| `sources` | List of doc directories / files mapped to knowledge-base topic folders |
| `lm_studio` | Connection settings for the optional LLM formatting pass |
| `audience`, `owner`, `branch_prefix` | Metadata and git branch defaults |

See `config.example.yaml` in this repository for a minimal standalone example.

### Source mappings

Each `sources` entry maps a `docs_dir` (relative to `kcworks_root`) to a `kb_topic`
folder inside the knowledge-base (for example `internal/works-maintenance`). Use
`files` to limit which markdown files are scanned; omit `files` to include every
`*.md` in the directory.

## Section extraction

Sections are included when **either**:

1. The heading matches `## How do I …?` (heading levels 2–4), or
2. An HTML comment tag appears on the line immediately above a `##`–`####` heading.

### Automatic headings

```markdown
## How do I import a list of users from a KC CSV file?
```

The article title becomes **Import a list of users from a KC CSV file** (the `How do I` / `?` wrapper is removed).

### Manual `kb-sync` tag

Use this for headings that do not follow the `How do I …?` pattern:

```markdown
<!-- kb-sync -->
## Deploy a hotfix without downtime
```

Optional knowledge-base title override (the heading text is not used as the article title):

```markdown
<!-- kb-sync: Deploy a hotfix -->
## Internal procedure (staging only)
```

Do not place `<!-- kb-sync -->` above headings that already match `How do I …?`; those are picked up automatically.

### Filename slugs

Output filenames are derived from the section title: lowercase, non-alphanumeric
characters become hyphens. **Apostrophes are stripped** (not turned into hyphens):

| Title fragment | Slug fragment |
|----------------|---------------|
| `user's` | `users` |
| `change a user's name` | `change-a-users-name` |

## Usage

Run from the **kcworks-next repository root** (so the default config path resolves):

```bash
uv run kb-sync --dry-run
uv run kb-sync --force
uv run kb-sync --use-llm --force --commit --pr
```

Override the config path when needed:

```bash
uv run kb-sync --config path/to/config.yaml --dry-run
```

### Flags

| Flag | Description |
|------|-------------|
| `--config PATH` | YAML config file (default: `docs/knowledge_base_sync/config.yaml`) |
| `--kcworks-root PATH` | Override `kcworks_root` from the config file |
| `--dry-run` | List planned output paths; do not write files or touch git |
| `--use-llm` | Format articles with LM Studio instead of the built-in converter |
| `--force` | Overwrite existing destination articles |
| `--commit` | Create a branch, run `build_index.py`, and commit in the KB repo |
| `--branch NAME` | Branch name for `--commit` (default: `kb-sync/YYYY-MM-DD`) |
| `--pr` | Push branch and open a GitHub pull request (requires `--commit`) |
| `--pr-title TEXT` | Pull request title (default: derived from changed articles) |

### Typical workflow

```bash
# Preview
uv run kb-sync --dry-run

# Write articles locally
uv run kb-sync --force

# Write, rebuild indexes, commit, and open a PR
uv run kb-sync --force --commit --pr
```

If you write files without `--commit`, rebuild indexes manually in the knowledge-base repo:

```bash
cd ~/Development/knowledge-base
uv run python scripts/build_index.py
```

## LM Studio formatting

With `--use-llm`, the tool reads `templates/how-to-template.md` and `SECRETS.md`
from the knowledge-base repo and sends each section to an OpenAI-compatible API.
Configure the endpoint in your YAML config:

```yaml
lm_studio:
  base_url: http://your-host:1234/v1
  model: ""  # empty = use the first loaded model
  temperature: 0.2
  timeout_seconds: 300
```

The deterministic formatter (default) does not call an LLM and is suitable for most
admin-guide how-tos.

## Notes

- Pages that are not how-tos (for example overview sections in `moderation.md`) are
  skipped unless marked with `<!-- kb-sync -->`.
- Introductory material before the first extracted section is folded into **Before you start**
  when using the deterministic formatter.
- The knowledge-base pre-commit hook runs gitleaks; do not publish content with
  credentials. The LLM path includes `SECRETS.md` in its prompt and basic output validation.

## Development

```bash
uv pip install -e .
ruff check src
kb-sync --help
```

Changes to this package should be committed in the
[kc-knowledge-base-sync](https://github.com/MESH-Research/kc-knowledge-base-sync)
repository, then the submodule pointer updated in kcworks-next.
