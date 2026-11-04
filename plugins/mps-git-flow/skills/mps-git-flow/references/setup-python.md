# Setting up Python 3 (>= 3.8)

The skill's helper script needs Python 3.8 or newer (standard library only, nothing else to install).

## 1. Detect

Try, in this order, and keep the first that reports `Python 3.8` or newer:

| Command | Notes |
|---|---|
| `py -3 --version` | Windows Python launcher; the most reliable on Windows |
| `python3 --version` | macOS / Linux. On Windows this may be the Microsoft Store stub (prints nothing, opens the Store, or hangs) - treat as not found |
| `python --version` | May be Python 2.x (reject) or the Store stub on Windows (reject) |

On Windows also check the usual install folder if the commands fail right after an install:
`%LOCALAPPDATA%\Programs\Python\Python312\python.exe` (Git Bash: `"$LOCALAPPDATA/Programs/Python/Python312/python.exe"`).
Use the full path as the Python command if needed.

## 2. Explain and ask permission

Tell the user in plain words, for example:
"Để tự động hoá việc đẩy code, mình cần Python 3 (một công cụ miễn phí, an toàn). Máy bạn chưa có. Mình cài
giúp bạn nhé? Việc cài mất khoảng 1-2 phút."
Install ONLY after the user agrees.

## 3. Install

| OS | Command |
|---|---|
| Windows | `winget install -e --id Python.Python.3.12` (add `--scope user` if admin rights are missing) |
| macOS | `brew install python@3.12` (if Homebrew is missing, ask the user to install Python from https://www.python.org/downloads/ instead) |
| Debian / Ubuntu | `sudo apt-get install -y python3` (asks for the user's password - let them type it in their own terminal) |

If `winget` is not available, guide the user to https://www.python.org/downloads/ ; in the installer they
should tick "Add python.exe to PATH".

## 4. Re-detect

A fresh install is often not on PATH in the already-open terminal. Re-run the detection; if it still fails:
- Windows: try `py -3 --version` again, then the full path under `%LOCALAPPDATA%\Programs\Python\`.
- Otherwise ask the user to open a new terminal / restart Claude Code, then detect again.

## Microsoft Store stub (Windows)

If `python` opens the Microsoft Store, the user can turn the stub off: Settings > Apps > Advanced app settings
> App execution aliases > switch off "python.exe" and "python3.exe". Not required when `py -3` works.
