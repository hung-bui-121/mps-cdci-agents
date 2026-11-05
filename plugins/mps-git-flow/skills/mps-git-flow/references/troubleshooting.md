# Troubleshooting

Each script failure has an `error` code, a Vietnamese `message` and often `service` (jira | gitlab),
`details` or `stderr`. Explain the problem to the user in plain words; never show or ask for tokens.

## Configuration

| error | Meaning | What to do |
|---|---|---|
| `not_git_repo` | Not inside a git project | Ask the user to open Claude Code in the project folder |
| `env_missing` | No `.env` at the project root | `env init --open`, then let the user fill tokens |
| `missing_config` | Keys in `missing_keys` are empty | User fills them in `.env` (tokens) or `env set` (non-secret) |
| `secret_key_refused` | `env set` on a `*_PAT` key | Tokens are only typed by the user into `.env` with an editor |
| `unknown_key` | Typo in `env set` | Use one of `allowed_keys` |
| `insecure_url` | URL is not https | Fix `MPS_JIRA_URL` / `MPS_GITLAB_URL` to `https://...` |
| `gitlab_project_unknown` | Origin is not on the MPS GitLab host | Ask for the project path, `env set MPS_GITLAB_PROJECT group/project` |
| `gitlab_project_not_found` | Wrong path or no access | Check the path in the GitLab web UI; ask a maintainer for access |
| `jira_project_not_found` | Wrong `MPS_JIRA_PROJECT_KEY` (the default board for new tickets; it may differ from the GitLab project) | Pick from `available_projects`, `env set MPS_JIRA_PROJECT_KEY KEY` |

`.env` is read only from the project root. Real environment variables are ignored on purpose (one project's
token is never picked up for another). If `env_tracked` appears in `warnings`, `.env` was committed in the past:
a developer must remove it from git (`git rm --cached .env`) and the tokens must be replaced.

## Tokens, network, certificates

| error | Typical cause | What to do |
|---|---|---|
| `auth_failed` (401) | Token wrong, expired or revoked | Create a new token (Jira: Profile > Personal Access Tokens; GitLab: Edit profile > Access Tokens, scopes `api` + `write_repository`) and update `.env` |
| `forbidden` (403) | Token lacks a scope, or the account lacks permission | GitLab: recreate the token with `api` + `write_repository`; ask a maintainer for project access |
| `network_unreachable` | VPN off, DNS failure, no network | Turn on the company VPN, check internet, retry |
| `timeout` | Slow / blocked connection | Check VPN, retry |
| `ssl_error` | Company TLS certificate not trusted by Python/git | Get the company CA file (`.pem`/`.crt`) from IT, set `env set MPS_CA_BUNDLE <path>` |
| `invalid_response` | Got an HTML page (login/proxy) instead of JSON | Check the URL in `.env`; token may be invalid; VPN/proxy |
| `unexpected_redirect` (3xx) | The server redirected (wrong URL/scheme, SSO login page); redirects are never followed so tokens cannot leak to another host | Check `MPS_JIRA_URL` / `MPS_GITLAB_URL` (exact `https://` host, no extra path); check the token |
| `server_error` (5xx) | Jira/GitLab is having problems | Retry later |

`MPS_CA_BUNDLE` is used for the Jira/GitLab API calls and is also passed to git (`http.sslCAInfo`) for fetch/push.

## Git

| error | Meaning | What to do |
|---|---|---|
| `operation_in_progress` | A merge/rebase/cherry-pick is half done | Stop. A developer must finish or abort it |
| `unmerged_files` (preflight blocker) | Conflict markers not resolved | Stop. A developer must help |
| `stash_conflict` | Branch switched, but the user's changes conflict with the newest code (or restoring them after a failed switch failed) | Changes are safe in the stash (`stash_commit`, message `mps-auto`). Do NOT resolve, reset or drop. A developer must help (`git stash list`, resolve, then `git stash drop` only after verifying). Until then `unmerged_files` blocks prepare-branch, commit and preflight on purpose |
| `stash_failed` | `git stash push` failed | If `stash_commit` is present, part of the changes is in the stash. A developer must help |
| `branch_base_mismatch` | The ticket branch already exists and contains commits of other work vs the base (`foreign_commits`), e.g. a dev bugfix branch reused for beta | Do not reuse it. A developer decides (usually a separate branch for the release fix) |
| `local_commits_not_carried` | The current branch has unpushed commits that the new ticket branch would not contain | They stay safe on the old branch. Ask a developer; pass `--leave-commits` only after the user explicitly agrees |
| `missing_git_identity` (preflight blocker) | git has no `user.name` / `user.email` | With consent: `git set-identity --name="..." --email="..."` (repo-local) |
| `env_file_in_commits` (preflight blocker) | An unpushed commit contains a `.env` file | Stop. A developer must rewrite those commits; the token must be replaced |
| `env_file` / `secret_detected` (commit, push) | `.env` or a token/private key would be committed or published | Nothing was committed / pushed. Remove the secret; for already-made commits a developer must help |
| `add_failed` | A path given to `--files` does not exist or is ignored | Use root-relative paths from `git preflight` |
| `mr_target_mismatch` | An open MR from this branch targets a different branch | Stop; a developer decides (close/retarget the old MR or use another branch) |
| `base_mismatch` (prepare-branch, push) | The ticket branch was made from `recorded_base` and must merge back into it | Use the recorded base. Moving the work to another branch/phase needs a developer |
| `target_mismatch_recorded_base` (mr ensure) | MR target differs from the branch's recorded base | Use `--target=<recorded_base>`; otherwise ask a developer |
| `phase_conflict` (flow plan) | The chosen phase differs from the branch that holds the work (changes / unpushed commits on it, or this ticket's own branch) | Explain: changes go back into the branch they were made on; moving them to another phase needs a developer |
| `phase_required` (flow plan) | Nothing pins the phase (clean tree, personal branch, another ticket's branch) | Ask the user: dev, beta or production; re-run with `--phase=` |
| `not_latest_release` (flow plan warning) | The user works on an older `release/*` branch that still exists on GitLab | Allowed (the MR goes into that branch) - confirm with the user that this is intended |
| `explicit_files_required` (commit) | A folder (even a deleted one), `.` or a path that is not a changed file was passed to `--files` | Pass the individual changed files (`changed_files_inside` lists those under the given path) |
| `scope_review_required` (commit) | No scope review yet, or the branch / HEAD changed since the review | Run the scope review + `review classify` again (SKILL step 6) |
| `not_in_scope` (commit) | A requested file is not in the review's `commit_files` (out-of-scope, mixed, needs_decision, unclassified) | Leave it out, or - only if the user named that file - pass it in `--include-out-of-scope` too |
| `changed_since_review` (commit) | A file was edited (or appeared) after the review | Run the review + `review classify` again |
| `invalid_include` (commit) | `--include-out-of-scope` names a file that is not in `--files` | List the file in both |
| `invalid_base` (prepare-branch, push, mr ensure) | Base / target is not develop, master or a release/* branch | Use the base from `flow plan` |
| `target_mismatch_inferred_base` (mr ensure) | No recorded base; the source branch is closest to another protected branch (`inferred_bases`, `commit_counts`) | Ask a developer which branch it really came from |
| `base_not_found` (mr ensure) | `origin/<target>` does not exist locally (wrong target or never fetched) | Re-check the plan; run `git prepare-branch` (fetches) |
| `branch_not_found` (mr ensure) | The source branch is neither local nor on origin | Push the branch first (`git push`) |
| `release_branch_gone` (flow plan) | The release branch the work sits on was deleted on GitLab | Stop; a developer must move the work |
| `recorded_base_gone` (flow plan) | The ticket branch's recorded base was deleted on GitLab. Warning on a clean tree (branch not reused); error with work in progress | Error: a developer must move the work |
| `detached_head` (flow plan) | Changes exist but HEAD is on no branch (and not exactly on develop/master/release/*) | Stop; a developer must help |
| `review_unparsable` (review classify) | The reviewer reply has no `FILES:` block | Ask the reviewer to answer in the required format, save it again, re-run |
| `switch_failed` | git refused to switch branches | Changes are untouched; show `stderr`; ask a developer |
| `base_not_found` | `origin/<base>` does not exist | Wrong base branch name or phase; check with the user/developer |
| `protected_branch` | Tried to commit/push on develop/master/release/* | Use `git prepare-branch` to move to the ticket branch first |
| `nothing_to_commit` | No changes | Fine if the branch already contains the commits (resume) |
| `commit_failed` | A git hook or config rejected the commit | Show `stderr`; ask a developer |
| `push_rejected` | The remote branch has commits you do not have | Never force. A developer (or a careful `git pull --no-rebase origin <branch>` with the user's consent) must bring them in first |
| `push_denied` | Protected branch / no permission | Ask a maintainer about permissions |
| `auth_failed` (git) | git credentials rejected | The script already retried once with `MPS_GITLAB_PAT` (https remotes on the MPS GitLab host only). Check the token has `write_repository`. For SSH remotes, the user's SSH key must be set up in GitLab |
| `git_not_found` | git is not installed / not on PATH | Install Git (Windows: `winget install -e --id Git.Git`) after asking permission |

The token retry passes the PAT to git via environment variables (`GIT_CONFIG_COUNT` /
`http.<MPS_GITLAB_URL>/.extraHeader`, so the header is only sent to the MPS GitLab host), never in the command
line or the remote URL, and only when both the fetch and push URLs of `origin` are https on that host.
Submodules are not fetched/pushed by these commands. This needs git 2.31 or newer; older git ignores it (the
retry then fails with the same auth error - update git). All git calls run with `LC_ALL=C` / `LANGUAGE=C` so
error messages can be recognised on Vietnamese-language systems.

## Jira

| error | Meaning | What to do |
|---|---|---|
| `ticket_not_found` | Wrong key or no permission | Re-check the key with the user. Tickets from any board (MPS-…, ART-…) are accepted |
| `jira_project_not_found` (create `--project`) | The chosen board does not exist or is not visible | Pick from `available_projects` (`jira projects`) |
| `invalid_project_key` | `--project` / `MPS_JIRA_PROJECT_KEY` is not a project key (e.g. `ART-12` instead of `ART`) | Use the project key only |
| `unsupported_type` | Ticket is not a Story or Bug | Use/create a Story or Bug ticket |
| `issue_type_not_found` | The Jira project has no Story/Bug type | Check `available_types`; ask the project admin |
| `missing_required_fields` | The create screen requires more fields | Ask the user for each field in `fields` (offer `allowed_values`), retry with `--field "<id or name>=<value>"` |
| `unknown_field` / `invalid_field_value` | `--field` name or value not accepted | Use a name from `available_fields` / a value from `allowed_values`; complex values may be given as JSON |
| `jira_create_failed` | Jira rejected the create | Read `details` / `field_errors`, fix and retry |
| `no_transition` | No Done/Resolve transition available from the current status (for `--to resolved` the Done transitions are tried too, for workflows without a Resolve step) | Non-fatal. Show `available_transitions`; the user moves the ticket by hand on Jira |
| `transition_failed` | The transition screen needs more data (e.g. a required resolution other than Fixed/Done - the script never picks values such as "Won't Fix") | Non-fatal. The user moves the ticket by hand |

## Python

`python_too_old` means the script ran on Python 2 / < 3.8: use the Python 3 command from step 0
(`references/setup-python.md`).
