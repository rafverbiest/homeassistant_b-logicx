# Releasing B-Logicx

Use this checklist so HACS custom-repository users get clean version upgrades.

## Before tagging

1. [ ] Integration changes are on the default branch and reviewed locally.
2. [ ] Bump version in `custom_components/b_logicx/manifest.json` (e.g. `0.8.3`).
3. [ ] Update `DESIGN.md` / wiki notes if behaviour changed.
4. [ ] Run tests:

   ```bash
   pip install -r requirements-dev.txt
   pytest
   ```

5. [ ] Push to GitHub and confirm CI is green:
   - Hassfest
   - HACS Action
   - Pytest (if enabled)

## Create the GitHub Release

1. [ ] Create a **Release** (not only a lightweight tag), e.g. tag `v0.8.3`.
2. [ ] Title/notes: short summary of user-facing changes.
3. [ ] Publish the release.

HACS prefers GitHub Releases so users can pick versions when downloading or upgrading.

## After release

1. [ ] In a test HA with the custom repository configured, check that HACS offers the new version.
2. [ ] Smoke-test: reload/restart, config flow, one Status probe / LDM or TSM refresh if relevant.

## Not required for custom-repo installs

- PR to `hacs/default` (default HACS store) — optional later; takes a maintainer review queue.
