---
name: mps-project-setup
description: >-
  For a project lead: integrate the mps-git-flow plugin into a project repository so every team member gets it
  (and its updates) automatically when they open the project in Claude Code. Writes .claude/settings.json
  (marketplace mps-cdci-agents with auto-update, plugin enabled, Claude attribution in commits / PRs hidden),
  makes sure .env is git-ignored, offers to create the project's code review rules file (.mps/review.md), then
  commits it through the normal mps-git-flow (ticket + merge request).
  Vietnamese triggers - "tích hợp plugin vào
  project", "cài mps-git-flow cho cả team", "thêm plugin vào dự án", "setup plugin cho project", "tạo quy tắc
  review code cho dự án".
---

# Integrate mps-git-flow into a project (lead)

Speak Vietnamese, plain words, as in mps-git-flow. `GITFLOW_DIR` = `<SKILL_DIR>/../mps-git-flow`.

1. Environment: do step 0 of `<GITFLOW_DIR>/SKILL.md` (bootstrap scripts in `<GITFLOW_DIR>/scripts/`), to get `PY`.
2. Run `PY "<GITFLOW_DIR>/scripts/mps.py" project setup`.
   - `settings_invalid_json` / `settings_not_object` / `settings_conflict`: nothing was changed; explain and stop
     (a developer fixes the file).
   - `files_to_commit` empty (`next: null`): the project is already integrated and committed; say so (then still do
     step 3 if `review_rules` is `absent`).
   - `changed: false` with a non-empty `files_to_commit`: the settings were written earlier but are not committed
     yet; continue with step 3 and the commit in step 5.
   - Change `marketplace_source_migrated`: the marketplace pointed to the old repo `hung-bui-121/mps-cdci-agents` and
     now points to `madpoly-studio/mps-cicd-agent-flow` (a pinned `ref` is kept); say so and commit it in step 5.
   - Warnings: `marketplace_source_differs` (an existing, different source is kept - confirm with the lead that this
     is intended), `settings_ignored_by_git` (the lead must remove that ignore line, or members never get the file),
     `attribution_kept` (the project already sets its own attribution text; it is kept - the helper script still
     strips AI attribution from every commit and MR it makes).
3. Code review rules (`review_rules`):
   - `absent`: explain in two sentences that the project can have its own code review rules in `.mps/review.md`
     (on top of the team's common rules and the rules for Unity C# / Python / web), and that only a rule the project
     marks `blocker` stops a commit; everything else is a warning written into the merge request. OFFER to create
     the file. Only if the lead agrees, run `PY "<GITFLOW_DIR>/scripts/mps.py" project setup --review-rules`
     (`review_rules: "created"`, `.mps/review.md` is added to `files_to_commit`). The new file has NO active rule
     yet: it explains the format and holds one example inside a code block.
   - `created` / `present`: if the lead wants rules now, write exactly the rules the lead describes (ID, severity,
     title, `paths:`, explanation with a wrong / right example), following the format in the file and in the README
     section "Quy tắc review code theo dự án". Never invent rules or choose `blocker` on your own; ask. Paths in
     `paths:` and `ignore:` always start at the repo root: for a Unity project in a subfolder write
     `**/Assets/Scripts/**/*.cs` (or the full `Client/Game/Assets/...`), never `Assets/Scripts/**/*.cs`. Files the
     stack rules skip (Unity `.prefab`, `.unity`, `.meta`, ...) are checked only by a rule that names them in an
     explicit `paths:` line (e.g. `paths: **/*.prefab`); a rule without `paths:` does not. Then run
     `project setup` again: `review_rules_problems` must be empty (each problem has `line` and `message`; fix them
     with the lead), and a warning `project_rule_matches_nothing` (`rule`, `paths`) means that rule's paths match no
     file in the repo, so it would never apply - fix its `paths:` with the lead. A file with problems is skipped
     entirely when members push code.
   - Tell the lead that the rules are read from the base branch on GitLab, so they apply only after this change
     is merged.
4. Explain in two or three plain sentences what the lead gets: when teammates open the project and accept the
   "trust this folder" dialog, Claude Code installs mps-git-flow from GitHub by itself and keeps it updated
   automatically. They can check under `/plugin` (tab Installed).
5. Commit `files_to_commit` with the mps-git-flow skill (ticket + branch + scope review + code review + MR), exactly
   like any other change. Suggest a ticket such as "Tích hợp plugin mps-git-flow vào project". Do not commit by any
   other means.
Never add `permissions` entries, never change other keys in `.claude/settings.json` (the script only adds
`extraKnownMarketplaces.mps-cdci-agents`, `enabledPlugins` and the missing parts of `attribution`), never edit
`.claude/settings.local.json`. Edit `.mps/review.md` only here, at the lead's request - never while pushing code
with mps-git-flow.
