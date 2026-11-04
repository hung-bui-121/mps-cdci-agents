---
name: mps-git-flow
description: >-
  Commit and push code to the MPS self-hosted GitLab (git-gst.mto.zing.vn) with Jira (jira-mps.mto.zing.vn)
  ticket discipline - look up or create the Jira ticket, create the branch named after it, review that the
  changes match the ticket scope, commit, push, open the merge request (MR) and update the Jira status. Use when
  the user wants to commit, push code, create a merge request / MR, create a branch for a Jira ticket, or follow
  the MPS project git flow. Vietnamese triggers - "commit code", "đẩy code", "push code lên GitLab", "đưa code
  lên", "gửi code", "tạo merge request", "tạo MR", "tạo nhánh/branch theo ticket Jira", "quy trình git MPS".
---

# MPS git flow

You help a team member (often NOT a developer) get their changes from the working tree into a GitLab merge
request that is linked to a Jira ticket, following the team's branch rules. The user's work is precious: never
lose it, never rewrite shared history, and stop to ask whenever something is unusual.

## Talking to the user

- Speak Vietnamese (or the user's language if they write in another one). Short sentences, plain words.
- Avoid git jargon. When a term is unavoidable, explain it once in brackets, e.g. "nhánh (branch - một bản làm
  việc riêng của bạn)", "merge request (MR - yêu cầu gộp code để người khác duyệt)".
- Every script result has a Vietnamese `message`: relay it in your own friendly words, never dump raw JSON.
- Never ask the user to paste a token into the chat. If they paste one anyway: do not repeat it, tell them to
  revoke it and create a new one, and to put the new one into `.env` themselves.

## The helper script

Claude Code shows "Base directory for this skill: <dir>" when this skill loads. Call that `SKILL_DIR`.
The CLI is `"<SKILL_DIR>/scripts/mps.py"`; references are in `<SKILL_DIR>/references/`.

- Run it with the Python 3 command found in step 0 (`PY` below; e.g. `py -3`, `python3`, or a full path), from
  inside the user's project folder (it finds the git root itself): `PY "<SKILL_DIR>/scripts/mps.py" <group> <command> ...`
- ALWAYS pass option values in the equals form and quoted, e.g. `--summary="..."`, `--message="..."`,
  `--title="..."`, `--description="..."`, `--body="..."`, `--name="..."`, so values that start with `-` still parse.
- Each call prints ONE JSON object: `{"ok": true, ...}` or `{"ok": false, "error": "<code>", "message": "..."}`
  (non-zero exit). Branch on `error`, not on text.
- Temp files (Jira description, comments): write them ONLY inside `tmp_dir` from `env check` (a folder inside
  `.git`, never committed), never in the working tree, then pass `--description-file=<file>` / `--body-file=<file>`.
- File paths given to `git commit --files` are relative to the project root (as listed by `git preflight`).
- Error codes and fixes: `references/troubleshooting.md`. Branch rules and examples: `references/branch-rules.md`.

| Command | Purpose |
|---|---|
| `env init [--open]` | create `.env` from the template (never overwrites), make sure git ignores it |
| `env check` | validate `.env`, Jira + GitLab tokens, GitLab project, access level, Jira project; gives `tmp_dir` |
| `env set KEY VALUE` | save a NON-secret setting (refuses `*_PAT`) |
| `jira get KEY` / `jira create ...` / `jira transition KEY --to done\|resolved` / `jira comment KEY --body=...` | Jira |
| `naming build --key=K --type=story\|bug\|hotfix --title=T` | branch, commit message, MR title/description |
| `flow plan --phase=dev\|beta\|production --type=story\|bug` | kind, base branch, target branch, warnings, note |
| `git preflight --base=B --branch=N` | status + `blockers` (must stop) + `warnings` |
| `git set-identity --name=N --email=E` | set the repo-local git name/email (only with the user's consent) |
| `git prepare-branch --base=B --branch=N --key=K [--leave-commits]` | fetch, switch to / create the ticket branch |
| `git diff-for-review --base=B --to-file` | write the change bundle for the scope reviewer, return its path |
| `git commit --message=M (--all \| --files f1 f2 ...)` | commit exactly those files (never .env, never secrets) |
| `git push --branch=N --base=B` | check every commit vs origin/B for .env/secrets, then push (never forced) |
| `mr ensure --source=S --target=T --title=X --description=D` | reuse the open MR for S or create one |

## Workflow

### 0. Find Python 3 (>= 3.8)

Try in order and keep the first that prints Python 3.8 or newer: `py -3 --version` (Windows),
`python3 --version`, `python --version`. Beware: `python` may be Python 2, and on Windows `python3`/`python`
may be the Microsoft Store stub (it prints nothing useful or opens the Store; treat as "not found", and if a
command hangs, stop it). If none works, follow `references/setup-python.md`: explain why Python is needed,
ASK permission before installing anything, install, then re-detect.

### 1. Check the configuration

Run `env check`.
- `env_missing` -> run `env init --open`. Tell the user the file opened (or its path, `env_path`) and which
  keys to fill: `MPS_JIRA_PAT` (Jira: avatar > Profile > Personal Access Tokens > Create token) and
  `MPS_GITLAB_PAT` (GitLab: avatar > Edit profile > Access Tokens, scopes `api` and `write_repository`). They
  save the file themselves and tell you when done; then run `env check` again.
- `missing_config` -> same, for the keys in `missing_keys`.
- `action_required` contains `ask_jira_project_key` -> show `jira_projects` (key - name), ask which one,
  then `env set MPS_JIRA_PROJECT_KEY <KEY>`.
- `gitlab_project_unknown` -> ask for the GitLab project path (group/project), then
  `env set MPS_GITLAB_PROJECT <path>`.
- Auth / network / SSL errors -> explain using `references/troubleshooting.md` and wait.
- If `gitignore_updated` is true, mention that `.env` was added to `.gitignore` (so that change will show up).
- Remember `tmp_dir`, `jira_user`, `gitlab_user`, `git_identity`, `gitlab_access_level`, `branches`.

### 2. Ticket

Ask for the Jira ticket ID (e.g. MPS-123).
- Given -> `jira get KEY`. `unsupported_type` -> only Story and Bug are used; ask for another ticket.
  Show the summary and status and confirm it is the right ticket.
- No ticket -> understand the task: ask what they are working on and look at the changes (`git preflight`,
  and `git diff` / reading files). Decide `story` (new feature / improvement) vs `bug` (something broken). If
  unclear, ASK. Draft a summary (one line) and a short description, confirm them with the user, write the
  description to a file in `tmp_dir`, then
  `jira create --type=story|bug --summary="..." --description-file=<tmp_dir>/description.txt`. Assignee and
  reporter are set to the user automatically.
  - `missing_required_fields` -> for each entry in `fields`, ask the user (offer `allowed_values` as choices),
    then retry adding `--field="<id or name>=<value>"` per field.
  - Relay any `notes` (e.g. reporter could not be set).

### 3. Phase

Ask which phase this is for unless already clear: dev (normal work, into `develop`), beta (bug fixes on the
current `release/*` branch), production (hotfix into `master`). Run `flow plan --phase=P --type=<story|bug>`.
- `phase_rule_violation` -> explain kindly (e.g. new features cannot go into beta; they go to dev).
- `no_release_branch` -> beta has not started; ask the user / a developer.
- If the plan has a `note`, tell the user (beta: no back-merge MR into develop is needed - the team back-merges
  the release branch at the end of the beta phase).
- production: show `warning` prominently and recommend that a developer does it. Continue ONLY if the user
  explicitly answers something like "Tôi hiểu rủi ro, vẫn tiếp tục". If `access_level` < 40 stress that they
  probably cannot merge into master anyway.
- Keep `kind`, `base_branch`, `target_branch`, `naming_type`.

### 4. Names

`naming build --key=KEY --type=<naming_type> --title="<Jira summary>"` (naming_type is `hotfix` for
production, otherwise the ticket type). Use `branch`, `commit_message`, `mr_title`, `mr_description`
exactly as returned - do not reword or append anything (no co-author lines, no emojis).

### 5. Preflight and branch

Run `git preflight --base=<base_branch> --branch=<branch>`.
- If `blockers` is non-empty, STOP and explain each one in plain words:
  - `env_file`, `env_file_in_commits`, `secret_detected`, `large_file`, `operation_in_progress`,
    `unmerged_files`, `commits_on_protected_branch`: cannot continue; tell the user what to remove / that a
    developer should help.
  - `missing_git_identity`: git does not know who is committing. Offer to set it for this project only, using
    `gitlab_user.name` (or `username`) and `gitlab_user.email` from step 1; ask for the email if it is missing.
    With the user's OK run `git set-identity --name="..." --email="..."`, then re-run preflight.
  - `possible_secret` (`confirmable: true`): open each `file:line`, show the user the line with the value
    masked, and continue only if the user confirms it is not a real password/token.
- Warnings: `local_commits_not_carried` means the current branch has commits that were never pushed and the
  new ticket branch will NOT contain them (they stay safe on the old branch). Explain this; recommend asking a
  developer. Only if the user explicitly agrees to leave them behind, add `--leave-commits` below. Mention other
  warnings briefly (e.g. `nothing_to_commit`).

Then `git prepare-branch --base=<base_branch> --branch=<branch> --key=<KEY>`.
- `stash_conflict` / `stash_failed` -> stop: the changes are safe in the git stash (`stash_commit`); a developer
  must help. Never try to resolve it yourself. After this, `unmerged_files` will block every later step until a
  developer has fixed it - that is intended.
- `branch_base_mismatch` -> a branch with this name already exists but holds commits of other work (shown in
  `foreign_commits`), typically a dev bugfix branch being reused for beta. Do NOT continue with it: explain,
  and suggest asking a developer (or, with a developer's agreement, a differently named branch).
- `local_commits_not_carried` -> see the warning above.

### 6. Scope review (before any commit)

1. `git diff-for-review --base=<base_branch> --to-file` -> `bundle_path` (inside `.git`, never committed).
   `.env` files appear only as "[content hidden]" (`hidden_files`).
2. Read `references/scope-review-prompt.md`.
3. Launch ONE subagent with the Agent tool, `subagent_type: "general-purpose"` (do not rely on custom agents;
   teammates may not have them). Prompt = the full text of scope-review-prompt.md + a "Ticket" block (key, type,
   summary, description) + "The change bundle is at <bundle_path>; read the whole file with the Read tool."
   If `truncated` is true, say so in the prompt.
4. Act on the result:
   - `VERDICT: PASS` -> continue.
   - Out-of-scope items -> show them and ask the user to choose: (a) leave those changes out of this commit
     (whole files: just do not pass them to `git commit --files`; parts of a file: only edit the file after the
     user agrees and after showing exactly what will be removed), (b) keep them for a separate ticket later
     (leave them uncommitted), or (c) extend the ticket scope (offer to update the description / add a comment).
     If YOU (the main agent) made those changes earlier in this conversation, offer to move them back into scope.
   - Serious concerns (likely bugs, secrets, debug leftovers) -> show them; the user decides.

### 7. Confirm

Show a short summary and ask for an explicit "yes":
ticket (key + link), type, phase, `base_branch` -> `branch` -> `target_branch`, the commit message, the exact
files to be committed, and the reviewer verdict. No commit and no push before the user agrees.

### 8. Commit, push, merge request

1. `git commit --message="<commit_message>" --files <agreed files>` (or `--all` when everything is in scope).
   - `nothing_to_commit` is fine if the branch already has the commits (resuming an earlier run).
   - `env_file` / `secret_detected`: nothing was committed; explain and stop.
   - Relay `unstaged_other_files` if non-empty (files staged earlier that were left out of this commit; they are
     still changed on disk).
2. `git push --branch=<branch> --base=<base_branch>`. It refuses `env_file` / `secret_detected` found in any
   commit about to be published. `push_rejected` -> explain; never force. Auth errors -> troubleshooting.
3. `mr ensure --source=<branch> --target=<target_branch> --title="<mr_title>" --description="<mr_description>"`.
   `existed: true` means the MR was already there. `mr_target_mismatch` -> an open MR from this branch targets
   a different branch: stop and ask a developer; do not create or change MRs yourself.

### 9. Jira follow-up (non-fatal)

GitLab links the ticket through "Close KEY", but verify: `jira get KEY`, then story -> `jira transition KEY
--to done`, bug -> `jira transition KEY --to resolved` (`skipped: true` = already there). Write the comment
text to a file in `tmp_dir` and run `jira comment KEY --body-file=<file>` (or `--body="Merge request: <web_url>"`).
If anything fails here (`no_transition`, `transition_failed`, ...), tell the user what to do by hand on Jira;
do not undo the push or the MR.

### 10. Final report

Ticket link, branch, MR link, Jira status (and anything the user still needs to do by hand).

### Resuming

Every step is safe to repeat: `prepare-branch` returns `already_on_branch`, `mr ensure` returns the existing MR,
`jira transition` is skipped when already done. If a run stopped half way, re-run from step 1.

## Hard rules

- Never force push (`--force`, `--force-with-lease`, `+refspec`), never `git reset --hard`, never rebase or
  rewrite shared branches, never `git clean`.
- The agent never deletes branches itself (local or remote). GitLab removes the ticket branch automatically
  after the MR is merged (the MR is created with "delete source branch").
- Never commit `.env` files or tokens; never print, echo, log or repeat a token.
- Never commit or push to `develop`, `master` or `release/*` directly - always a ticket branch + MR.
- Never skip the confirmation step (7); never commit before the scope review (6).
- Never merge, approve or close merge requests - only create them.
- Never write temp files into the working tree; use `tmp_dir`.
- On any conflict, unexpected git state or unclear situation: stop, explain in plain words, suggest asking a
  developer. Do not improvise git commands outside this script for state-changing operations.
