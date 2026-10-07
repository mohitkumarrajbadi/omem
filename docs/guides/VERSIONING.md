# Versioning, naming, and branching

Canonical rules for the open-source package. Cloud SaaS lives in `omem-cloud`
and is versioned separately.

## Naming

| Surface | Name | Notes |
|---|---|---|
| GitHub repo | `omem` | https://github.com/mohitkumarrajbadi/omem |
| PyPI package | **`omem-os`** | `pip install omem-os` — do **not** rename |
| Python import | `omem` | `from omem import AgentState, OMem` |
| CLI entrypoint | `omem` | `omem demo kill-resume` |
| Local checkout folder | often `omem-oss` | Workspace name only; not the package name |
| Cloud product | `omem-cloud` | Separate repo / deploy |

Never publish under `omem`, `omem-oss`, or `memx-ai`. The installable name is
always **`omem-os`**.

## SemVer (tech preview)

We use [Semantic Versioning](https://semver.org/) on the **`0.0.x`** line until
GA:

| Part | Meaning for OMem today |
|---|---|
| `0.0.MAJOR-patch` style → **`0.0.PATCH`** | Each PyPI cut is `0.0.N` |
| Breaking public API | Document in CHANGELOG; still bump `0.0.N` until 0.1 / 1.0 |
| GA | First stable line will be announced as `0.1.0` or `1.0.0` explicitly |

**Git tags** are `v` + the PyPI version: `v0.0.3` → PyPI `0.0.3`.

**Do not** invent parallel “v2 / v3 product” version numbers for releases.
Internal architecture milestones belong in docs and CHANGELOG prose, not in
PyPI versions.

### Historical oddities (do not repeat)

| Version | What happened |
|---|---|
| PyPI `1.0.0` (2026-04-25) | Incorrect early upload; treat as non-current |
| GitHub `v0.0.2` | Tagged on GitHub; not published to PyPI |
| PyPI `0.0.1` | First real public install |

Next intended public cut: **`0.0.3`** on both GitHub and PyPI.

## How the version is computed

Versions are dynamic via [setuptools-scm](https://github.com/pypa/setuptools_scm):

- On a **`v*` tag**: version is that tag (minus the leading `v`).
- Between tags (editable / CI): local/dev version derived from git, with
  `fallback_version` in `pyproject.toml` only when git metadata is missing.
- Publish CI sets `SETUPTOOLS_SCM_PRETEND_VERSION` so wheels/sdists match the
  tag exactly.

Check locally:

```bash
python -c "import omem; print(omem.__version__)"
```

## Branching

```
feature/*  ──PR──►  dev  ──promote──►  staging  ──promote──►  main
                                              │
                                              └──merge──►  cloud  (demo deploy)
```

| Branch | Purpose | Who merges |
|---|---|---|
| `dev` | Default integration branch. All PRs land here. | Maintainers |
| `staging` | Pre-release soak / partner builds | Maintainers |
| `main` | Release branch. Tags (`v*`) are cut from here. | Maintainers |
| `cloud` | Linode/Akamai demo track (from `staging`) | Maintainers |
| `feat/*`, `fix/*` | Short-lived work branches | Contributors |

Rules:

1. **PRs target `dev`**, never `main` (redirect if needed).
2. **Promote** `dev → staging → main` with merge commits (or PRs), not force-push.
3. **Release tags** only on commits that are on `main` (see [RELEASING.md](./RELEASING.md)).
4. Tag push or a published GitHub Release triggers `.github/workflows/publish.yml`.
5. Do not reuse or move a tag that already shipped to PyPI.

## Related

- [RELEASING.md](./RELEASING.md) — cut a release
- [CHANGELOG.md](../../CHANGELOG.md) — user-facing history
- [CONTRIBUTING.md](../../CONTRIBUTING.md) — day-to-day workflow
