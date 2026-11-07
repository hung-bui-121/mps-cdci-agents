# Preparing the environment (step 0)

## What is needed and why

| Need | Why | Installed automatically? |
|---|---|---|
| git 2.23+ (2.31+ recommended) | every git operation; `git switch` needs 2.23; the GitLab token retry (`GIT_CONFIG_COUNT`) needs 2.31 | yes |
| Python 3.8+ with `ssl`, `json`, `subprocess`, `urllib.request` | runs `scripts/mps.py` (standard library only); `ssl` is needed for every Jira / GitLab call | yes |
| Company VPN | Jira and GitLab are only reachable through it | no - the user turns it on |
| Jira and GitLab tokens in `.env` | API access | no - the user creates them and types them into `.env` (step 1) |

git-lfs is not needed. Step 0 installs ONLY git and Python, without asking first: tell the user in one plain line
what is being installed and why. Never install anything else and never change system settings.

## The two scripts

| OS | Command |
|---|---|
| Windows | `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "<SKILL_DIR>/scripts/bootstrap.ps1" [-DetectOnly]` |
| macOS / Linux | `sh "<SKILL_DIR>/scripts/bootstrap.sh" [--detect-only]` |

- The Windows command works from Git Bash and from PowerShell. `-ExecutionPolicy Bypass` applies to this one
  process only; no system setting changes.
- Detect-only mode reports what is missing and installs nothing. Run it first.
- Install mode (no flag) detects, installs what is missing, then detects again. Give it a long timeout
  (10 minutes). All install commands share ONE budget of about 500 seconds: no new install starts with less than
  30 seconds left (`install_failed` + a manual step), and an installer still running when the budget ends is left
  to finish on its own (`install_still_running`, no manual download). Detection itself adds at most a few probes
  of 20 seconds each, so the JSON line comes well inside the 10 minutes. The macOS / Linux budget needs
  `date +%s` (present on macOS and every common Linux); without it the sh script waits for each install command.
- Neither script ever prompts or asks for a password. Installer output goes to the log file (`log_path`), never
  to the JSON line: `%TEMP%\mps-bootstrap.log` on Windows, `${TMPDIR:-/tmp}/mps-bootstrap.<uid>.log` on macOS /
  Linux (a symlink found there is removed, never written through). Exit code 0 = `ok: true`, 1 otherwise.
- No JSON line at all (blocked by policy, killed, timed out): check by hand with `py -3 --version` (Windows) or
  `python3 --version`, and `git --version`. Python 3.8+ and git 2.23+ are enough; otherwise use the manual
  fallback at the end of this page.

## Output (one JSON line)

```json
{"ok": true, "os": "windows", "mode": "install",
 "python_cmd": "C:\\Users\\an\\AppData\\Local\\Programs\\Python\\Python312\\python.exe", "python_version": "3.12.4",
 "git_cmd": "C:\\Program Files\\Git\\cmd\\git.exe", "git_version": "2.41.0", "git_on_path": true,
 "missing": [], "installed": ["python"], "manual_steps": [], "warnings": [],
 "log_path": "C:\\Users\\an\\AppData\\Local\\Temp\\mps-bootstrap.log", "error": null,
 "message": "Đã sẵn sàng: Python 3.12.4, git 2.41.0."}
```

- `python_cmd`: an absolute path that works without any PATH change. Use it as `PY`, always quoted:
  `"<python_cmd>" "<SKILL_DIR>/scripts/mps.py" ...`.
- `missing`: what is still missing after this run (`python`, `git`); a git older than 2.23 counts as missing.
- `installed`: what this run installed.
- `git_on_path`: whether `git` resolves through the PATH Claude Code started with. `mps.py` calls `git` by name,
  so a git outside that PATH is not usable yet. It is reported as `restart_required` only when a restart really
  helps: on Windows when the PATH stored in the registry (Machine + User, what a new Claude Code inherits)
  resolves `git` to a git that is new enough; on macOS when the git's folder is listed in `/etc/paths` or
  `/etc/paths.d`. If an older git comes first on that PATH it is `git_too_old`; otherwise `git_not_on_path`.
  So a restart is never asked for when it would not change anything.
- The Windows script escapes every non-ASCII character as `\uXXXX`, so the Vietnamese `message` reads correctly
  through both Git Bash and PowerShell.

## Error codes (`ok: false`, the first blocking problem)

In detect-only mode `error` names what is missing and nothing has been tried yet: announce the items in one
line and run the install mode.

| error | Meaning | What to tell the user / do |
|---|---|---|
| `python_missing` | No usable Python 3.8+ (after the install attempt) | Explain `manual_steps` (download page or the Mac dialog), wait until the user says it is done, run step 0 again |
| `git_missing` | No git (after the install attempt) | Same as above |
| `git_too_old` | git older than 2.23 that could not be upgraded | Same as above (install a newer Git) |
| `git_too_old` (older git first on PATH) | A new git exists, but an older one (2.22 or below) comes first on the PATH a new Claude Code would get | Relay the `git_not_on_path` manual step: remove that old Git or its folder from PATH |
| `restart_required` | git was installed (or found) outside the PATH Claude Code started with, and a restart will pick it up | Ask the user to fully close Claude Code AND the VS Code / Terminal window running it, open it again in the project folder and say "tiếp tục"; then step 0 again |
| `git_not_on_path` | git is installed, but its folder is not on PATH (a restart would not help) | Relay the `git_not_on_path` manual step (it names the folder to add to PATH), wait, then step 0 again |
| `use_powershell` | `bootstrap.sh` was run on Windows (Git Bash) | Run `bootstrap.ps1` with the Windows command above |
| `bootstrap_failed` | Unexpected script error (`details`) | Tell the user to send the log file (`log_path`) to a developer |

## Manual steps (`manual_steps`)

Explain each one in plain words, show `command` / `url` when present, and wait for the user.

| code | Meaning |
|---|---|
| `install_python_manual` | Download Python 3 from `url` (https://www.python.org/downloads/). On Windows tick "Add python.exe to PATH" |
| `install_git_manual` | Download Git from `url` (https://git-scm.com/downloads), keep the default options |
| `run_in_terminal` | Linux without password-less sudo: the user runs `command` (it starts with `sudo`) in their OWN terminal and types their password there. Never ask for, accept or type a password in the chat |
| `xcode_clt_install` | macOS without Homebrew: the "Command Line Developer Tools" dialog was opened; the user clicks "Install" and waits a few minutes (git and Python 3 come with it) |
| `restart_claude_code` | Fully close Claude Code and the VS Code / Terminal window running it, then open it again in the project folder |
| `git_not_on_path` | Names the folder to add to PATH (Windows: Environment Variables > Path; macOS with Homebrew: `command` adds `brew shellenv` to `~/.zprofile`), or the folder of an old Git to remove; then fully close and reopen Claude Code |

## Warnings (`warnings`)

Relay them briefly.

| code | Meaning |
|---|---|
| `store_stub_detected` | Windows: `python` / `python3` is the Microsoft Store shortcut, not a real Python; it was skipped |
| `winget_missing` | Windows: no winget (App Installer), so nothing could be installed automatically; manual steps follow |
| `install_failed` (+ `item`) | Installing `item` failed (or was skipped because the time budget ran out); details in the log; a manual step follows |
| `install_still_running` (+ `item`) | The installer for `item` was still running when the time budget ended. No manual download: the user waits a few minutes, then step 0 again |
| `git_old_for_token_fallback` | git works, but only 2.31+ retries a failed GitLab login with the token from `.env` |
| `uac_prompt_possible` | Windows may show a permission dialog (UAC); the user clicks Yes |

## Per-OS notes

- **Windows**: installs use winget, user scope first (`--scope user`, no admin dialog), then machine scope
  (`uac_prompt_possible`). A too-old git is upgraded with `winget upgrade`. Python is found through `py -3`,
  `python3` / `python`, then `%LOCALAPPDATA%\Programs\Python\Python3*` and `%ProgramFiles%\Python3*`, so a fresh
  install works in the same run. The Microsoft Store stub (Settings > Apps > Advanced app settings > App execution
  aliases) is skipped automatically; the user does not need to change anything. A freshly installed git is often
  not on the PATH Claude Code started with: `restart_required` (see `git_on_path`). PATH entries that point to a
  missing drive or contain invalid characters are skipped (and logged), never fatal.
- **macOS**: `/usr/bin/git` and `/usr/bin/python3` open the Command Line Tools dialog when the tools are missing;
  the script only calls them once `xcode-select -p` succeeds, so detect-only never opens the dialog. With Homebrew
  it runs `brew install python@3.12` / `brew install git` non-interactively (`HOMEBREW_NO_AUTO_UPDATE=1`). git is
  also looked for in `/opt/homebrew/bin` and `/usr/local/bin` when it is not on PATH. Without Homebrew it opens the
  Command Line Tools dialog (`xcode_clt_install`); Homebrew itself is never installed (its installer needs the
  password).
- **Linux**: apt-get, dnf, yum, zypper or pacman, run directly as root or with password-less `sudo -n`. Otherwise
  the user gets `run_in_terminal` with the `sudo ...` command to type in their own terminal.

## Manual fallback

- Python: https://www.python.org/downloads/ (Windows: tick "Add python.exe to PATH").
- Git: https://git-scm.com/downloads (default options).

After a manual install, run step 0 again (the scripts also look in the standard install folders, so a new
terminal is usually not needed for Python).
