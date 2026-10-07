# Releasing `omem-os`

Cut a public version only when CI is green on `main`.

## Preconditions

- [ ] `dev` → `staging` → `main` promoted (or the release commit is already on `main`)
- [ ] CI green on the release commit ([Actions](https://github.com/mohitkumarrajbadi/omem/actions))
- [ ] `CHANGELOG.md` has a dated section for the new version (move items out of Unreleased)
- [ ] Version follows [VERSIONING.md](./VERSIONING.md) (`0.0.N` until GA)
- [ ] PyPI Trusted Publisher / `pypi` GitHub Environment is configured for this repo

## Cut the release

From a clean checkout of `main`:

```bash
git checkout main
git pull origin main

# Example: 0.0.3
VERSION=0.0.3
git tag -a "v${VERSION}" -m "omem-os ${VERSION}"
git push origin "v${VERSION}"
```

That tag push runs **Publish to PyPI** (wheels + sdist + Trusted Publisher upload).

Optional but recommended — also create a GitHub Release for notes/changelog UI:

```bash
gh release create "v${VERSION}" --title "omem-os ${VERSION}" --notes-file CHANGELOG.md --verify-tag
```

(A GitHub Release alone also triggers publish; prefer **one** trigger per version —
tag push is enough.)

## Verify

```bash
# Workflow
open "https://github.com/mohitkumarrajbadi/omem/actions/workflows/publish.yml"

# PyPI
pip index versions omem-os
pip install "omem-os==${VERSION}"
python -c "import omem; print(omem.__version__)"
OMEM_EMBEDDER=hash omem demo kill-resume
```

## After publish

1. Bump `fallback_version` in `pyproject.toml` to the **next** unreleased patch
   (e.g. after `0.0.3` ships → `0.0.4`).
2. Open a PR to `dev` if those doc/fallback edits were made on `main`.
3. Announce to design partners with the install pin above.

## Hotfix

Same process: bump patch (`0.0.4`), changelog entry, tag from `main`. Do not
overwrite an existing tag or re-upload the same version (PyPI is immutable;
`skip_existing` only skips duplicates).

## Failure playbook

| Symptom | Fix |
|---|---|
| Linux wheel job OOM / lost runner | Keep `CIBW_ARCHS_LINUX=x86_64` (no QEMU). Re-run workflow. |
| Windows ARM64 wheel fail | Not built; AMD64 + sdist only. |
| Version mismatch in sdist smoke | Ensure tag is `vX.Y.Z` and pretend version matches. |
| Trusted Publisher 403 | Check PyPI project `omem-os` ↔ GitHub `pypi` environment. |

Do **not** delete and recreate a tag that already published artifacts to PyPI.
Ship `0.0.N+1` instead.
