---
name: mps-git-flow
description: >-
  Commit and push code to the MPS self-hosted GitLab (git-gst.mto.zing.vn) with Jira (jira-mps.mto.zing.vn)
  ticket discipline - look up or create the Jira ticket (any board, e.g. MPS or the artist board), create the
  branch named after it, review that the changes match the ticket scope, commit only the in-scope files, push,
  open the merge request (MR) back into the branch the work came from, and update the Jira status. Use when
  the user wants to commit, push code, create a merge request / MR, create a branch for a Jira ticket, or follow
  the MPS project git flow. Vietnamese triggers - "commit code", "đẩy code", "push code lên GitLab", "đưa code
  lên", "gửi code", "tạo merge request", "tạo MR", "tạo nhánh/branch theo ticket Jira", "quy trình git MPS".
---

# MPS git flow

You help a team member (often NOT a developer) get their changes from the working tree into a GitLab merge
request that is linked to a Jira ticket, following the team's branch rules. The user's work is precious: never
lose it, never rewrite shared history, never commit what was not meant for this ticket, and stop to ask
whenever something is unusual.

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
- Temp files (Jira description, comments, the reviewer's reply): write them ONLY inside `tmp_dir` from
  `env check` (a folder inside `.git`, never committed), never in the working tree.
- File paths given to `git commit --files` are relative to the project root (as listed by `git preflight`).
- Error codes and fixes: `references/troubleshooting.md`. Branch rules and examples: `references/branch-rules.md`.

| Command | Purpose |
|---|---|
| `env init [--open]` | create `.env` from the template (never overwrites), make sure git ignores it |
| `env check` | validate `.env`, Jira + GitLab tokens, GitLab project, access level, Jira project; gives `tmp_dir` |
| `env set KEY VALUE` | save a NON-secret setting (refuses `*_PAT`) |
| `jira get KEY` | read a ticket from ANY Jira project |
| `jira projects` | list Jira projects (boards) the user can see, plus the configured default |
| `jira create --type=story\|bug --summary=S --description-file=F [--project=KEY] [--field=...]` | create a ticket |
| `jira transition KEY --to=done\|resolved` / `jira comment KEY --body-file=F` | update a ticket |
| `naming build --key=K --type=story\|bug\|hotfix --title=T` | branch, commit message, MR title/description |
| `flow plan --type=story\|bug --key=K [--phase=dev\|beta\|production]` | phase from the branch holding the work; base = target |
| `git preflight --base=B --branch=N` | status, branch role + `blockers` (must stop) + `warnings` |
| `git set-identity --name=N --email=E` | set the repo-local git name/email (only with the user's consent) |
| `git prepare-branch --base=B --branch=N --key=K [--leave-commits]` | fetch, switch to / create the ticket branch, record its base |
| `git diff-for-review --base=B --to-file` | write the change bundle (a snapshot with a `Bundle-ID`) for the scope reviewer |
| `review classify --base=B --result-file=F` | check the reviewer's `FILES:` block, derive commit / exclude lists, save them |
| `git commit --message=M --files f1 f2 ... [--include-out-of-scope f ...]` | commit exactly those reviewed files |
| `git push --branch=N --base=B` | check every commit vs origin/B for .env/secrets, then push (never forced) |
| `mr ensure --source=S --target=T --title=X --description=D --key=K --type=story\|bug` | verify target = recorded base, then reuse / create the MR |

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
- `action_required` contains `ask_jira_project_key` -> show `jira_projects` (key - name), ask which Jira project
  is the team's usual board for new tickets, then `env set MPS_JIRA_PROJECT_KEY <KEY>`. It may differ from the
  GitLab project name.
- `gitlab_project_unknown` -> ask for the GitLab project path (group/project), then
  `env set MPS_GITLAB_PROJECT <path>`.
- Auth / network / SSL errors -> explain using `references/troubleshooting.md` and wait.
- If `gitignore_updated` is true, mention that `.env` was added to `.gitignore` (so that change will show up).
- Remember `tmp_dir`, `jira_project` (the default board), `jira_user`, `gitlab_user`, `git_identity`,
  `gitlab_access_level`, `branches`.

### 2. Ticket

Ask for the Jira ticket ID. A ticket from ANY board is fine (e.g. `MPS-123`, or `ART-12` from the artist
team's board) - the ticket's project does not have to match the GitLab project.
- Given -> `jira get KEY`. `unsupported_type` -> only Story and Bug are used; ask for another ticket.
  Show the summary and status and confirm it is the right ticket.
- No ticket -> understand the task: ask what they are working on and look at the changes (`git preflight`,
  and `git diff` / reading files). Decide `story` (new feature / improvement) vs `bug` (something broken). If
  unclear, ASK. Draft a summary (one line) and a short description and confirm them with the user.
  - Board: tell the user the ticket will be created on the default board (`jira_project` from step 1) and ask
    whether it belongs to another board (e.g. the artist board). If so, run `jira projects`, let them pick,
    and pass `--project=<KEY>` for this one ticket. Do NOT change `MPS_JIRA_PROJECT_KEY` unless the user says
    that board should become the default.
  - Write the description to a file in `tmp_dir`, then
    `jira create --type=story|bug --summary="..." --description-file=<tmp_dir>/description.txt [--project=KEY]`.
    Assignee and reporter are set to the user automatically.
  - `jira_project_not_found` -> the chosen board does not exist / is not visible; show `available_projects`.
  - `missing_required_fields` -> for each entry in `fields`, ask the user (offer `allowed_values` as choices),
    then retry adding `--field="<id or name>=<value>"` per field.
  - Relay any `notes` (e.g. reporter could not be set).

### 3. Phase (from the branch that holds the work)

A change made on branch X always goes back into X. Run `flow plan --type=<story|bug> --key=<KEY>` WITHOUT
`--phase` first (it fetches from GitLab with `--prune`, so deleted branches are noticed):
- Files tools rewrite on their own do not count as work here: inside a Unity project root (a folder with
  `ProjectSettings/ProjectVersion.txt`) its `ProjectSettings/**`, `UserSettings/**`, `Library/**`,
  `Packages/packages-lock.json` and the `*.csproj` / `*.sln` directly in it, plus the user's own
  `MPS_GENERATED_PATTERNS`. A folder that only has the same name deeper down (`Assets/Plugins/Library/...`) is
  real work. If `generated_changes` is non-empty, mention them briefly ("Unity tự sửa các file này, không ảnh
  hưởng việc chọn giai đoạn"). They are still classified by the scope review in step 6 and never committed
  automatically. A warning `invalid_generated_pattern` lists patterns from `.env` that were ignored; tell the
  user (they fix `.env` themselves).
- The current branch pins the phase only when work sits on it (other uncommitted changes or unpushed commits,
  `work_in_progress`) or when it is THIS ticket's own branch made by this skill: `develop` -> dev, any
  `release/*` -> beta (that exact release branch, even if not the newest), `master` -> production, own ticket
  branch -> the phase of its `recorded_base`. A detached HEAD sitting exactly on one of them counts as that
  branch. Tell the user in plain words, e.g. "Bạn đang làm trên nhánh release/1.1 nên thay đổi sẽ gộp về
  release/1.1 (giai đoạn beta)", and let them confirm (`phase_source: "detected"`).
- `phase_required` -> nothing pins the phase (clean tree, personal branch, another ticket's branch): ask dev
  (normal work, into `develop`), beta (bug fixes on the current `release/*`), production (hotfix into
  `master`); `detected_phase` may hint at the current branch. Re-run with `--phase=<phase>`; on a clean tree the
  user's choice is used (`phase_source: "requested_clean_tree"`).
- `phase_conflict` -> the user chose a phase different from the branch that holds the work. Explain that changes
  made on one branch cannot silently move to another phase; suggest a developer. Never work around it.
- `detached_head` -> changes exist but HEAD is on no branch: stop, a developer must help.
- `recorded_base_gone` (error: work in progress on a ticket branch whose base was deleted on GitLab) -> stop, a
  developer must help. As a warning (clean tree) the old ticket branch is simply not reused; continue normally.
- `release_branch_gone` -> the release branch the work sits on no longer exists on GitLab: stop, ask a developer.
- `warnings`: `not_latest_release` -> tell the user they are on an older (still existing) release branch
  (`latest` names the newest) and confirm that this is intended. `other_ticket_branch` -> the user stands on
  another ticket's branch; this ticket gets its own branch.
- `phase_rule_violation` -> explain kindly (e.g. new features cannot go into beta; they go to dev).
- `no_release_branch` -> beta has not started; ask the user / a developer.
- If the plan has a `note`, tell the user (beta: no back-merge MR into develop is needed - the team back-merges
  the release branch at the end of the beta phase).
- production: show `warning` prominently and recommend that a developer does it. Continue ONLY if the user
  explicitly answers something like "Tôi hiểu rủi ro, vẫn tiếp tục". If `access_level` < 40 stress that they
  probably cannot merge into master anyway.
- Keep `kind`, `base_branch`, `target_branch` (always equal to `base_branch`), `naming_type`.

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
- Warnings: `local_commits_not_carried` means the current branch has commits that are on no GitLab branch
  (usually never pushed; commits this skill pushed earlier are not counted, even after GitLab deleted the merged
  branch) and the new ticket branch will NOT contain them (they stay safe on the old branch). Explain this;
  recommend asking a
  developer. Only if the user explicitly agrees to leave them behind, add `--leave-commits` below. Mention other
  warnings briefly (e.g. `nothing_to_commit`).

Then `git prepare-branch --base=<base_branch> --branch=<branch> --key=<KEY>`. It records the base in the
repo-local git config (`branch.<branch>.mps-base`), so later steps can enforce "merge back into the same branch".
- `stash_conflict` / `stash_failed` -> stop: the changes are safe in the git stash (`stash_commit`); a developer
  must help. Never try to resolve it yourself. After this, `unmerged_files` will block every later step until a
  developer has fixed it - that is intended.
- `base_mismatch` -> this ticket branch was made from `recorded_base` and must go back into it, not into the
  base you asked for. Explain; do not continue with a different base (ask a developer if the user insists).
- `branch_base_mismatch` -> a branch with this name already exists but holds commits of other work (shown in
  `foreign_commits`), typically a dev bugfix branch being reused for beta. Do NOT continue with it: explain,
  and suggest asking a developer (or, with a developer's agreement, a differently named branch).
- `local_commits_not_carried` -> see the warning above.

### 6. Scope review (before any commit)

Only what was intentionally changed for this ticket gets committed. Anything else (Unity-regenerated
`ProjectSettings`/`.meta` files, lock files, someone else's edits, IDE files) stays on the user's machine,
untouched, and is NOT committed - so it cannot affect other people.

1. `git diff-for-review --base=<base_branch> --to-file` -> `bundle_path` (inside `.git`, never committed) and
   `bundle_id`. The bundle is a snapshot: its header carries `Bundle-ID`, and the script remembers the exact
   content of every file in it. Section 0 lists the files to classify (`files_to_classify` = uncommitted
   changes, `already_committed_files` = earlier commits on this branch). `.env` files appear only as
   "[content hidden]". Do not edit any project file between this step and the commit; if anything must change
   (e.g. trimming a mixed file), make the change and start again from this step.
2. Read `references/scope-review-prompt.md`.
3. Launch ONE subagent with the Agent tool, `subagent_type: "general-purpose"` (do not rely on custom agents;
   teammates may not have them). Prompt = the full text of scope-review-prompt.md + a "Ticket" block (key, type,
   summary, description) + "The change bundle is at <bundle_path>; read the whole file with the Read tool."
   If `truncated` is true, say so in the prompt. The reply must contain `BUNDLE: <id>` with the bundle's id.
4. Save the reviewer's full reply (as received, never edited by you) to `<tmp_dir>/review.txt` and run
   `review classify --base=<base_branch> --result-file=<tmp_dir>/review.txt`. It only accepts a reply for the
   latest bundle while nothing has changed since that bundle, then saves the decisions with the fingerprints
   the reviewer saw in `<tmp_dir>/scope.json`. `git commit` only accepts files approved there whose content is
   still exactly what was reviewed. Any edit to a file, or a new commit, means starting step 6 again.
   - `review_stale` (`reason`: reply for an older bundle, reply without the `BUNDLE:` line, files / branch /
     HEAD changed since the bundle) -> run `git diff-for-review` again and get a fresh review of the new bundle.
     Never reuse an old reply and never add the `BUNDLE:` line yourself.
   - `complete: false` (`unclassified_files`, `unknown_paths`, `duplicate_paths`, missing verdict) or
     `review_unparsable` -> ask the reviewer (same subagent via SendMessage, or a new one) to fix its reply for
     the same bundle; never guess. Until the classification is complete, `git commit` refuses with
     `scope_incomplete` (also for `--include-out-of-scope`). `unclassified_files` are never committed.
   - Default commit set = `commit_files`: in_scope files, plus concern files when the verdict is PASS.
     `excluded_files` (out_of_scope) are left out.
   - `needs_decision` (concern files under a FAIL verdict) and `concern_files`: show each concern and ask the
     user per file whether to commit it.
   - `mixed_files`: show what part is in / out of scope and ask the user to choose for each file: include the
     whole file, exclude the whole file, or let you remove the out-of-scope part (first show exactly what will
     be removed, edit only after the user agrees, then run the review + classify again). Never include a mixed
     file silently.
   - `committed_out_of_scope`: out-of-scope work is already in an earlier commit of this branch; it cannot be
     left out any more - tell the user and suggest a developer.
   - If YOU (the main agent) made out-of-scope changes earlier in this conversation, offer to move them back
     into scope instead.

### 7. Confirm

Show a short summary and ask for an explicit "yes":
- ticket (key + link), type, phase
- branches: "tách từ `<base_branch>` -> nhánh `<branch>` -> merge vào `<base_branch>`"
- the commit message
- **Sẽ commit:** the exact file list
- **Không commit (ngoài phạm vi — giữ nguyên trên máy):** every excluded / unclassified file
- the reviewer verdict and any concerns

Tell the user they can force-include any excluded file by naming it. Add a file that is not in `commit_files`
(out-of-scope, mixed kept whole, or a `needs_decision` concern) ONLY if the user explicitly named that specific
file, and then pass it in both `--files` and `--include-out-of-scope`. Never add files to
`--include-out-of-scope` on your own. No commit and no push before the user agrees.

### 8. Commit, push, merge request

1. `git commit --message="<commit_message>" --files <agreed files> [--include-out-of-scope <files the user named>]`
   - always the explicit agreed list of exact file paths.
   - `scope_review_required` (no review, or the branch/HEAD changed since) / `changed_since_review` (a file was
     edited after the reviewer saw it) / `scope_incomplete` -> run step 6 again. `not_in_scope` -> the file was
     not approved; ask the user.
   - `explicit_files_required`: a folder, `.` or a path that is not a changed file was passed; list the
     individual changed files instead (`changed_files_inside`).
   - `nothing_to_commit` is fine when resuming an earlier run: either nothing is changed, or the requested files
     are already committed on this branch (`already_committed`) while other files stay uncommitted.
   - `env_file` / `secret_detected`: nothing was committed; explain and stop.
   - A successful commit consumes the review; a later commit needs a new review.
   - Keep `left_uncommitted` (changed files still not committed) for the final report. Relay
     `unstaged_other_files` if non-empty (files staged earlier that were left out; still changed on disk).
2. `git push --branch=<branch> --base=<base_branch>`. It refuses `env_file` / `secret_detected` found in any
   commit about to be published, and `base_mismatch` if the base differs from the recorded one.
   `push_rejected` -> explain; never force. Auth errors -> troubleshooting.
3. `mr ensure --source=<branch> --target=<base_branch> --title="<mr_title>" --description="<mr_description>"
   --key=<KEY> --type=<story|bug>`. The target is ALWAYS the base the branch was made from, and the phase rules
   are checked again for it (`phase_rule_violation`: a Story never goes into release/* or master).
   - `existed: true` means the MR was already there.
   - `target_mismatch_recorded_base` / `target_mismatch_inferred_base` / `target_ambiguous` (no recorded base and
     several possible bases; only develop is accepted then) / `branch_base_mismatch` / `mr_target_mismatch` ->
     stop and ask a developer; do not create or change MRs yourself.
   - `invalid_base` (target is not develop/master/release/*), `base_not_found` (origin/<target> missing),
     `branch_not_found` (the source branch is neither local nor pushed) -> re-check the plan from step 3; push
     first if the branch was not pushed.

### 9. Jira follow-up (non-fatal)

GitLab's Jira integration links/closes the ticket through "Close KEY" in the MR description; this works for any
project on the same Jira instance (e.g. ART-12 as well as MPS-123). Verify anyway: `jira get KEY`, then
story -> `jira transition KEY --to=done`, bug -> `jira transition KEY --to=resolved` (`skipped: true` = already
there). Write the comment text to a file in `tmp_dir` and run `jira comment KEY --body-file=<file>` (or
`--body="Merge request: <web_url>"`). If anything fails here (`no_transition`, `transition_failed`, ...), tell
the user what to do by hand on Jira; do not undo the push or the MR.

### 10. Final report

Ticket link, branch ("tách từ X -> merge vào X"), MR link, Jira status, and the files left uncommitted
(`left_uncommitted` from step 8 - still changed on the user's machine, not part of this MR), plus anything the
user still needs to do by hand.

### Resuming

Every step is safe to repeat: `prepare-branch` returns `already_on_branch`, `flow plan` detects the phase from
the ticket branch's recorded base, `mr ensure` returns the existing MR, `jira transition` is skipped when
already done. If a run stopped half way, re-run from step 1.

## Hard rules

- Never force push (`--force`, `--force-with-lease`, `+refspec`), never `git reset --hard`, never rebase or
  rewrite shared branches, never `git clean`.
- The agent never deletes branches itself (local or remote). GitLab removes the ticket branch automatically
  after the MR is merged (the MR is created with "delete source branch").
- Never commit `.env` files or tokens; never print, echo, log or repeat a token.
- Never commit or push to `develop`, `master` or `release/*` directly - always a ticket branch + MR.
- Commit only the explicit agreed file list, approved by the latest scope review. Out-of-scope, mixed (unless the
  user chose), `needs_decision` and unclassified files are never committed; such a file is included (via
  `--include-out-of-scope`) only when the user names that file explicitly.
- The MR always targets the branch the work was based on; never move changes to another phase's branch.
- Never add, change or suggest `MPS_GENERATED_PATTERNS` (or any other setting) to get around `phase_conflict`;
  `env set` refuses that key on purpose - only the user edits it in `.env`.
- Never skip the confirmation step (7); never commit before the scope review (6).
- Never merge, approve or close merge requests - only create them.
- Never write temp files into the working tree; use `tmp_dir`.
- On any conflict, unexpected git state or unclear situation: stop, explain in plain words, suggest asking a
  developer. Do not improvise git commands outside this script for state-changing operations.
