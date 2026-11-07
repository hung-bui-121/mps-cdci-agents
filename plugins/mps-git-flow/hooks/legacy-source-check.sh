#!/usr/bin/env bash
# SessionStart hook of mps-git-flow. Prints nothing (and never fails the session) unless this machine still
# installs the plugin from the old personal repo. Then it tells the user how to switch to the shared repo and tells
# Claude not to start the git flow until they did. The hard stop is in scripts/mps.py (error plugin_source_legacy);
# keep the repo names here in sync with LEGACY_MARKETPLACE_REPOS / MARKETPLACE_REPO there.
# Messages must not contain double quotes or backslashes: they are written into JSON as they are.

legacy_repo="hung-bui-121/mps-cdci-agents"
shared_repo="madpoly-studio/mps-cicd-agent-flow"

# Only a real source counts (a github "repo" or a git URL), like points_to_legacy_repo in mps.py.
pattern='("repo"[[:space:]]*:[[:space:]]*"|github\.com[/:])'"$legacy_repo"'(\.git)?"'

plugins_dir="${CLAUDE_CODE_PLUGIN_CACHE_DIR:-${CLAUDE_CONFIG_DIR:-$HOME/.claude}/plugins}"
known="$plugins_dir/known_marketplaces.json"
[ -f "$known" ] && grep -Eqi "$pattern" "$known" 2>/dev/null || exit 0

# The project settings live at the git root, as mps.py reads them, even when Claude Code started in a subfolder.
project_dir="${CLAUDE_PROJECT_DIR:-.}"
root=$(git -C "$project_dir" rev-parse --show-toplevel 2>/dev/null) || root="$project_dir"
settings="$root/.claude/settings.json"
if [ -f "$settings" ] && grep -Eqi "$pattern" "$settings" 2>/dev/null; then
  user_msg="mps-git-flow: team đã thống nhất đưa plugin về repo dùng chung của tổ chức ($shared_repo). Project này vẫn khai báo repo cá nhân cũ của hungbt ($legacy_repo): nhờ lead nói 'tích hợp plugin vào project' rồi commit .claude/settings.json để cả team tự chuyển sang nhé."
  claude_ctx="The project .claude/settings.json still declares the mps-cdci-agents marketplace from the legacy repo $legacy_repo. The git flow still works; if the user is the project lead, suggest the mps-project-setup skill (project setup) to move it to $shared_repo."
else
  user_msg="mps-git-flow: team đã thống nhất đưa plugin về repo dùng chung của tổ chức ($shared_repo), nên bạn cần gỡ bản cài từ repo cá nhân của hungbt ($legacy_repo) thì mới dùng tiếp được nhé. Gõ lần lượt: /plugin marketplace remove mps-cdci-agents, /plugin marketplace add $shared_repo, /plugin install mps-git-flow@mps-cdci-agents, rồi /reload-plugins. Cảm ơn bạn!"
  claude_ctx="This machine installs the mps-git-flow plugin from the legacy repo $legacy_repo; every mps.py command except project setup fails with plugin_source_legacy until it is removed. Before starting the mps git flow, tell the user in friendly Vietnamese that the team moved the plugin to the shared repo $shared_repo and offer to run, with their consent: claude plugin marketplace remove mps-cdci-agents, then claude plugin marketplace add $shared_repo, then claude plugin install mps-git-flow@mps-cdci-agents; then ask them to type /reload-plugins. If a command fails, give the user the matching /plugin commands to type."
fi

printf '{"systemMessage": "%s", "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "%s"}}\n' \
  "$user_msg" "$claude_ctx"
exit 0
