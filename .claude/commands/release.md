---
description: Commit pending work and cut a versioned release (bump → tag → GitHub Release with notes)
argument-hint: "[major|minor|patch|X.Y.Z] (default: patch)"
allowed-tools: Bash(git status:*), Bash(git add:*), Bash(git commit:*), Bash(git push:*), Bash(git tag:*), Bash(git log:*), Bash(git diff:*), Bash(uv run:*), Bash(python scripts/bump_version.py:*), Bash(gh release:*), Bash(gh run:*), Read, Edit
---

You are cutting a release for the **label-studio-mcp-server** project. Follow this
exact process — it mirrors the CI in `.github/workflows/release-mcpb.yml`, which
builds and attaches the `.mcpb` bundle when a `v*` tag is pushed.

## Bump level
The requested bump is: **$1** (if empty, default to `patch`).
Choose by impact if the user didn't specify:
- new tool / user-visible feature → `minor`
- bug fix / perf / docs only → `patch`
- breaking change to tool signatures or config → `major`

## Steps

1. **Inspect** what's being released:
   - `git status -s` and `git diff` for uncommitted work.
   - `git log $(git describe --tags --abbrev=0)..HEAD --oneline` for commits since the last tag.
   Summarize the user-facing changes — you'll need them for the notes.

2. **Pre-flight checks** (abort and report if any fail):
   - Must be on `master` with the intended changes present.
   - Run the test/import smoke check: `uv run python -c "import asyncio; from label_studio_mcp.mcp_server import mcp; print(len(asyncio.run(mcp.list_tools())), 'tools')"`.
   - Confirm versions are currently in sync: `python scripts/bump_version.py --check`.

3. **Commit pending work** (if any) with a clear Conventional-Commits message
   (`feat:` / `fix:` / `perf:` / `chore:`). End the message with:
   ```
   Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
   ```

4. **Bump the version** (keeps `manifest.json` + `pyproject.toml` in sync):
   `python scripts/bump_version.py $1` (or `patch` by default).
   Capture the new `X.Y.Z`. Commit it: `chore(release): vX.Y.Z`.

5. **Push** the branch: `git push origin master`.

6. **Tag and push** — this triggers the `.mcpb` build/attach workflow.
   The tag MUST be `vX.Y.Z` and match `manifest.json` exactly (CI enforces this):
   `git tag vX.Y.Z && git push origin vX.Y.Z`.

7. **Create the GitHub Release** with notes. Match the house style of prior
   releases (`gh release view <prev-tag>`): **Ukrainian**, emoji section headings
   (`## 🐛 Виправлення`, `## ✨ Нове`, etc.), a `### Деталі` list, a `### Сумісність`
   note, and a `**Full Changelog:**` compare link. End the body with:
   ```
   🤖 Generated with [Claude Code](https://claude.com/claude-code)
   ```
   Create it with a heredoc body and the just-built tag:
   `gh release create vX.Y.Z --title "vX.Y.Z — <short title>" --notes "$(cat <<'EOF' ... EOF)"`
   (The CI workflow attaches the `.mcpb` asset to this release once it finishes;
   you don't upload the bundle yourself.)

8. **Verify**: `gh run list --workflow=release-mcpb.yml -L 1` to confirm the build
   started, and `gh release view vX.Y.Z` to confirm the release exists. Report the
   release URL and whether the bundle is attached yet (CI may still be running).

## Guardrails
- Never delete or rewrite existing tags/releases without explicit confirmation.
- If `bump_version.py --check` fails, fix the desync before tagging — CI will reject a mismatched tag.
- Keep each tool/operation fast and idempotent; if `git push` of the tag fails because it exists, stop and ask.
