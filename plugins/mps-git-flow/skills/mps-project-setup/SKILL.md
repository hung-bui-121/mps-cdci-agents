---
name: mps-project-setup
description: >-
  For a project lead: integrate the mps-git-flow plugin into a project repository so every team member gets it
  (and its updates) automatically when they open the project in Claude Code. Writes .claude/settings.json
  (marketplace mps-cdci-agents with auto-update, plugin enabled, Claude attribution in commits / PRs hidden),
  makes sure .env is git-ignored, then commits it through the normal mps-git-flow (ticket + merge request).
  Vietnamese triggers - "tích hợp plugin vào
  project", "cài mps-git-flow cho cả team", "thêm plugin vào dự án", "setup plugin cho project".
---

# Integrate mps-git-flow into a project (lead)

Speak Vietnamese, plain words, as in mps-git-flow. `GITFLOW_DIR` = `<SKILL_DIR>/../mps-git-flow`.

1. Environment: do step 0 of `<GITFLOW_DIR>/SKILL.md` (bootstrap scripts in `<GITFLOW_DIR>/scripts/`), to get `PY`.
2. Run `PY "<GITFLOW_DIR>/scripts/mps.py" project setup`.
   - `settings_invalid_json` / `settings_not_object` / `settings_conflict`: nothing was changed; explain and stop
     (a developer fixes the file).
   - `files_to_commit` empty (`next: null`): the project is already integrated and committed; say so and stop.
   - `changed: false` with a non-empty `files_to_commit`: the settings were written earlier but are not committed
     yet; continue with step 3 and the commit in step 4.
   - Warnings: `marketplace_source_differs` (an existing, different source is kept - confirm with the lead that this
     is intended), `settings_ignored_by_git` (the lead must remove that ignore line, or members never get the file),
     `attribution_kept` (the project already sets its own attribution text; it is kept - the helper script still
     strips AI attribution from every commit and MR it makes).
3. Explain in two or three plain sentences what the lead gets: when teammates open the project and accept the
   "trust this folder" dialog, Claude Code installs mps-git-flow from GitHub by itself and keeps it updated
   automatically. They can check under `/plugin` (tab Installed).
4. Commit `files_to_commit` with the mps-git-flow skill (ticket + branch + scope review + MR), exactly like any other
   change. Suggest a ticket such as "Tích hợp plugin mps-git-flow vào project". Do not commit by any other means.
Never add `permissions` entries, never change other keys in `.claude/settings.json` (the script only adds
`extraKnownMarketplaces.mps-cdci-agents`, `enabledPlugins` and the missing parts of `attribution`), never edit
`.claude/settings.local.json`.
