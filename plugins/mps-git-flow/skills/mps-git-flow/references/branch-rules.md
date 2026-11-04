# MPS branch rules

These rules are enforced by `mps.py flow plan` and `mps.py naming build`. Branch names come from `.env`
(`MPS_BRANCH_DEV`, `MPS_BRANCH_BETA_PREFIX`, `MPS_BRANCH_PROD`); defaults shown below.

## Phases

| Phase | When | Allowed ticket types | Kind | Branch from (base) | MR target |
|---|---|---|---|---|---|
| dev | normal development | Story, Bug | Story -> `feature`, Bug -> `bugfix` | `develop` | `develop` |
| beta | testing a release | Bug only | `bugfix` | latest `release/*` | the same `release/*` |
| production | urgent fix on live | Bug only | `hotfix` | `master` | `master` |

- Only two Jira issue types exist in this team: **Story** and **Bug**. Anything else is rejected
  (`unsupported_type`).
- **beta**: a Story is rejected (`phase_rule_violation`) - new features always go through dev. The "latest"
  release branch is chosen by version number (`release/1.10.0` > `release/1.9.2`); if any release branch name
  has no digits, the newest commit date decides instead. **No back-merge MR into develop is created**: the team
  back-merges the release branch into develop once at the end of the beta phase.
- **production (hotfix)**: not forbidden, but risky. The plan always carries a `warning` and
  `requires_explicit_confirmation: true`. Recommendation: a developer should do hotfixes; members should not.
  Proceed only after the user explicitly confirms they understand the risk. If the user's GitLab access level is
  below Maintainer (40) - Developer is 30 - the warning is stronger: they very likely cannot merge into master.

## Naming

| Kind (naming type) | Branch | Commit message | MR title | MR description |
|---|---|---|---|---|
| story | `feature/{KEY}-{slug}` | `feat: {KEY} {Title}` | `{KEY} {Title}` | `Close {KEY}` |
| bug | `bugfix/{KEY}-{slug}` | `fix: {KEY} {Title}` | `{KEY} {Title}` | `Close {KEY}` |
| hotfix | `hotfix/{KEY}-{slug}` | `fix: {KEY} {Title}` | `{KEY} {Title}` | `Close {KEY}` |

- `{Title}` = the Jira summary as written (whitespace collapsed). `{KEY}` stays upper case.
- MR title = commit message without the leading `feat: ` / `fix: `.
- MR description is exactly `Close {KEY}` (GitLab's Jira integration links / closes the ticket from it).
- `{slug}`: Vietnamese letters folded to ASCII (accents removed, `đ`/`Đ` -> `d`), lower case, every run of other
  characters -> `-`, no leading/trailing dashes, at most 50 characters, cut at a dash so words are not split.
- The commit message is used exactly as built - nothing is appended.

## Examples

| Ticket | Phase | Branch | Commit message |
|---|---|---|---|
| Story MPS-123 "Thêm màn hình Đăng nhập bằng Google" | dev | `feature/MPS-123-them-man-hinh-dang-nhap-bang-google` | `feat: MPS-123 Thêm màn hình Đăng nhập bằng Google` |
| Bug MPS-7 "Sửa lỗi đăng nhập Đặc biệt!" | dev | `bugfix/MPS-7-sua-loi-dang-nhap-dac-biet` | `fix: MPS-7 Sửa lỗi đăng nhập Đặc biệt!` |
| Bug MPS-88 "Lỗi hiển thị giá" | beta (latest `release/2.3.0`) | `bugfix/MPS-88-loi-hien-thi-gia` from and into `release/2.3.0` | `fix: MPS-88 Lỗi hiển thị giá` |
| Bug MPS-90 "Lỗi thanh toán" | production | `hotfix/MPS-90-loi-thanh-toan` from and into `master` | `fix: MPS-90 Lỗi thanh toán` |

For MPS-123 the MR title is `MPS-123 Thêm màn hình Đăng nhập bằng Google` and the description `Close MPS-123`.

## Same ticket in two phases

A dev bugfix and a beta bugfix for the same ticket get the same branch name (`bugfix/{KEY}-{slug}`). An existing
branch is only reused when every commit it has on top of the base mentions the ticket key; otherwise
`git prepare-branch` stops with `branch_base_mismatch` (reusing a develop-based branch for a release MR would
ship unreleased develop work). A developer then decides how to name the release-fix branch. Likewise
`mr ensure` refuses (`mr_target_mismatch`) when the branch already has an open MR into a different target.

## Protected branches

`develop`, `master` and every `release/*` branch are never committed to or pushed to directly by this skill:
`git commit` and `git push` refuse them, and `git preflight` blocks when local commits sit on one of them
unpushed (a developer must move those commits to a ticket branch).
