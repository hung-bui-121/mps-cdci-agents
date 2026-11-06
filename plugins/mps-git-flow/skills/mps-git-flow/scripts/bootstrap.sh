#!/bin/sh
# Prepares git and Python 3.8+ for the mps-git-flow skill on macOS and Linux.
#
# Prints exactly ONE line of JSON on stdout and exits 0 when everything is ready, 1 otherwise.
# --detect-only only reports what is missing. The default mode also installs the missing items (Homebrew or the
# Xcode Command Line Tools dialog on macOS; the system package manager on Linux, only as root or with
# password-less sudo) and then detects again. All installs share one time budget (needs `date +%s`; without it
# there is no budget). Never prompts, never asks for a password, installs nothing but git and Python.
# Installer output goes to ${TMPDIR:-/tmp}/mps-bootstrap.<uid>.log, never to stdout.
#
# POSIX sh only (no bash features). Keep this file UTF-8 without BOM and LF-only (see .gitattributes).

MIN_PY_MAJOR=3
MIN_PY_MINOR=8
MIN_GIT_MAJOR=2
MIN_GIT_MINOR=23
TOKEN_FALLBACK_GIT_MINOR=31
# One budget for every install command together, well below the agent's 10-minute command timeout.
INSTALL_BUDGET_SECONDS=500
# Below this much remaining budget no new install is started.
MIN_INSTALL_SECONDS=30
PY_PROBE='import sys, ssl, json, subprocess, urllib.request; print("%d.%d.%d|%s" % (sys.version_info[:3] + (sys.executable,)))'
PYTHON_URL='https://www.python.org/downloads/'
GIT_URL='https://git-scm.com/downloads'
BREW_PYTHON='python@3.12'
BREW_BIN_DIRS='/opt/homebrew/bin /usr/local/bin'
RESTART_HINT='tắt hẳn Claude Code VÀ cửa sổ Terminal / VS Code đang chạy nó, mở lại trong thư mục project rồi nói "tiếp tục"'

MODE=install
for arg in "$@"; do
    case "$arg" in
        --detect-only) MODE=detect ;;
    esac
done

now_seconds() {
    _now=$(date +%s 2>/dev/null)
    case "$_now" in ''|*[!0-9]*) echo 0 ;; *) echo "$_now" ;; esac
}
START_SECONDS=$(now_seconds)

# Per-user log name; a symlink planted in a shared temp folder is removed, never written through.
tmp_root=${TMPDIR:-/tmp}
LOG_PATH="${tmp_root%/}/mps-bootstrap.$(id -u 2>/dev/null).log"
if [ -L "$LOG_PATH" ]; then rm -f "$LOG_PATH" 2>/dev/null; fi
if [ -L "$LOG_PATH" ] || ! printf 'mps bootstrap mode=%s\n' "$MODE" 2>/dev/null > "$LOG_PATH"; then
    LOG_PATH=/dev/null
fi

WARNINGS=''
WARNING_KEYS=''
MANUAL=''
MANUAL_CODES=''
STILL_RUNNING=''

# ---------------------------------------------------------------------------- output

log() {
    printf '%s\n' "$*" >> "$LOG_PATH" 2>/dev/null
}

# A JSON string: backslash and quote escaped, tab/CR turned into spaces, other control characters dropped,
# newlines written as \n.
json_str() {
    printf '"'
    printf '%s' "$1" | LC_ALL=C tr '\011\015' '  ' | LC_ALL=C tr -d '\000-\010\013-\037' \
        | LC_ALL=C sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' \
        | LC_ALL=C awk 'NR > 1 { printf "%s", "\\n" } { printf "%s", $0 }'
    printf '"'
}

json_or_null() {
    if [ -n "$1" ]; then json_str "$1"; else printf 'null'; fi
}

json_list() {
    printf '['
    _jl_sep=''
    for _jl_item in $1; do
        printf '%s' "$_jl_sep"
        json_str "$_jl_item"
        _jl_sep=','
    done
    printf ']'
}

add_warning() {  # code message [item]
    case " $WARNING_KEYS " in *" $1:$3 "*) return 0 ;; esac
    WARNING_KEYS="$WARNING_KEYS $1:$3"
    _w="{\"code\":$(json_str "$1"),\"message\":$(json_str "$2")"
    if [ -n "$3" ]; then _w="$_w,\"item\":$(json_str "$3")"; fi
    WARNINGS="$WARNINGS${WARNINGS:+,}$_w}"
}

add_manual() {  # code message [command] [url]
    case " $MANUAL_CODES " in *" $1 "*) return 0 ;; esac
    MANUAL_CODES="$MANUAL_CODES $1"
    _m="{\"code\":$(json_str "$1"),\"message\":$(json_str "$2")"
    if [ -n "$3" ]; then _m="$_m,\"command\":$(json_str "$3")"; fi
    if [ -n "$4" ]; then _m="$_m,\"url\":$(json_str "$4")"; fi
    MANUAL="$MANUAL${MANUAL:+,}$_m}"
}

add_python_manual() {
    add_manual install_python_manual "Tải và cài Python 3 từ trang python.org. Khi cài trên Windows nhớ tích ô \"Add python.exe to PATH\"." '' "$PYTHON_URL"
}

add_git_manual() {
    add_manual install_git_manual 'Tải và cài Git từ trang git-scm.com (giữ các lựa chọn mặc định).' '' "$GIT_URL"
}

is_still_running() {  # item
    case " $STILL_RUNNING " in *" $1 "*) return 0 ;; esac
    return 1
}

# ok: nothing to do; timeout: the installer may still finish, so no manual download; otherwise a manual step.
install_outcome() {  # item status
    case "$2" in
        ok) ;;
        timeout)
            add_warning install_still_running "Trình cài $1 vẫn đang chạy (lâu hơn thời gian chờ). Đợi vài phút cho cài xong rồi báo mình để kiểm tra lại; chưa cần tự tải về cài." "$1"
            STILL_RUNNING="$STILL_RUNNING $1"
            ;;
        *)
            add_warning install_failed "Cài $1 tự động không thành công (xem log: $LOG_PATH)." "$1"
            if [ "$1" = python ]; then add_python_manual; else add_git_manual; fi
            ;;
    esac
}

emit() {  # error message
    if [ -z "$1" ]; then _ok=true; else _ok=false; fi
    printf '{"ok":%s,"os":%s,"mode":%s,"python_cmd":%s,"python_version":%s,"git_cmd":%s,"git_version":%s,"git_on_path":%s,"missing":%s,"installed":%s,"manual_steps":[%s],"warnings":[%s],"log_path":%s,"error":%s,"message":%s}\n' \
        "$_ok" "$(json_str "$OS")" "$(json_str "$MODE")" "$(json_or_null "$PYTHON_CMD")" \
        "$(json_or_null "$PYTHON_VERSION")" "$(json_or_null "$GIT_CMD")" "$(json_or_null "$GIT_VERSION")" \
        "$GIT_ON_PATH" "$(json_list "$MISSING")" "$(json_list "$INSTALLED")" "$MANUAL" "$WARNINGS" \
        "$(json_str "$LOG_PATH")" "$(json_or_null "$1")" "$(json_str "$2")"
    if [ "$_ok" = true ]; then exit 0; fi
    exit 1
}

# ---------------------------------------------------------------------------- detection

version_ge() {  # major minor wanted_major wanted_minor
    [ "$1" -gt "$3" ] || { [ "$1" -eq "$3" ] && [ "$2" -ge "$4" ]; }
}

# On macOS /usr/bin/git and /usr/bin/python3 are shims that open the Command Line Tools install dialog when the
# tools are missing: they are only called once xcode-select reports the tools as installed.
clt_ready() {
    [ "$OS" != macos ] || xcode-select -p >/dev/null 2>&1
}

# Sets _gv_ver/_gv_ok for one git binary; returns 1 when it does not run or does not print a version.
git_version_of() {  # path
    if [ "$1" = /usr/bin/git ] && ! clt_ready; then
        log "skipped /usr/bin/git: Command Line Tools are not installed"
        return 1
    fi
    _out=$("$1" --version 2>>"$LOG_PATH" </dev/null) || return 1
    _gv_ver=$(printf '%s\n' "$_out" | sed -n 's/^git version \([0-9][0-9.]*\).*/\1/p' | head -n 1)
    _gv_ver=${_gv_ver%.}
    case "$_gv_ver" in [0-9]*.[0-9]*) ;; *) return 1 ;; esac
    _maj=${_gv_ver%%.*}
    _rest=${_gv_ver#*.}
    _min=${_rest%%.*}
    if version_ge "$_maj" "$_min" "$MIN_GIT_MAJOR" "$MIN_GIT_MINOR"; then _gv_ok=yes; else _gv_ok=no; fi
    return 0
}

# The git on PATH first, then the Homebrew folders (not on PATH). The first one new enough wins; otherwise the
# first one that runs is reported as too old.
detect_git() {
    GIT_CMD=''
    GIT_VERSION=''
    GIT_STATE=missing
    GIT_ON_PATH=false
    _on_path=$(command -v git 2>/dev/null)
    for _g in "$_on_path" $BREW_BIN_DIRS; do
        if [ -z "$_g" ]; then continue; fi
        _is_path=false
        if [ "$_g" = "$_on_path" ]; then _is_path=true; else _g="$_g/git"; fi
        if [ ! -x "$_g" ] || { [ "$_is_path" = false ] && [ "$_g" = "$_on_path" ]; }; then continue; fi
        git_version_of "$_g" || continue
        if [ "$_gv_ok" = yes ]; then
            GIT_CMD=$_g
            GIT_VERSION=$_gv_ver
            GIT_STATE=ok
            GIT_ON_PATH=$_is_path
            return 0
        fi
        if [ "$GIT_STATE" = missing ]; then
            GIT_CMD=$_g
            GIT_VERSION=$_gv_ver
            GIT_STATE=old
            GIT_ON_PATH=$_is_path
        fi
    done
}

probe_python() {  # candidate
    _out=$(PYTHONIOENCODING=utf-8 "$1" -c "$PY_PROBE" 2>>"$LOG_PATH" </dev/null) || return 1
    _line=$(printf '%s\n' "$_out" | tr -d '\015' | tail -n 1)
    _ver=${_line%%|*}
    _exe=${_line#*|}
    case "$_ver" in [0-9]*.[0-9]*.[0-9]*) ;; *) return 1 ;; esac
    if [ -z "$_exe" ] || [ "$_exe" = "$_line" ]; then return 1; fi
    _maj=${_ver%%.*}
    _rest=${_ver#*.}
    _min=${_rest%%.*}
    version_ge "$_maj" "$_min" "$MIN_PY_MAJOR" "$MIN_PY_MINOR" || return 1
    PYTHON_CMD=$_exe
    PYTHON_VERSION=$_ver
    return 0
}

# python_cmd is absolute, so a Python outside PATH (Homebrew, python.org framework) is fine.
detect_python() {
    PYTHON_CMD=''
    PYTHON_VERSION=''
    _fw=''
    _fw_minor=-1
    for _d in /Library/Frameworks/Python.framework/Versions/3.*; do
        [ -x "$_d/bin/python3" ] || continue
        _m=${_d##*/3.}
        case "$_m" in ''|*[!0-9]*) continue ;; esac
        if [ "$_m" -gt "$_fw_minor" ]; then
            _fw_minor=$_m
            _fw="$_d/bin/python3"
        fi
    done
    for _c in "$(command -v python3 2>/dev/null)" "$(command -v python 2>/dev/null)" /opt/homebrew/bin/python3 \
              /usr/local/bin/python3 "$_fw" /usr/bin/python3; do
        if [ -z "$_c" ] || [ ! -x "$_c" ]; then continue; fi
        if [ "$_c" = /usr/bin/python3 ] && ! clt_ready; then continue; fi
        if probe_python "$_c"; then return 0; fi
    done
    return 1
}

detect_all() {
    hash -r 2>/dev/null
    detect_python
    detect_git
}

# ---------------------------------------------------------------------------- installation

remaining_seconds() {
    echo $((INSTALL_BUDGET_SECONDS - ($(now_seconds) - START_SECONDS)))
}

# Runs one install command within the shared budget; sets INSTALL_STATUS to ok, failed, timeout (still running,
# not killed) or skipped (no budget left). The command runs in a subshell owned by this user, so `kill -0` works
# even when the command itself runs through sudo.
run_install() {
    _left=$(remaining_seconds)
    if [ "$_left" -lt "$MIN_INSTALL_SECONDS" ]; then
        log "no time left for: $*"
        INSTALL_STATUS=skipped
        return 1
    fi
    log "> $* (wait up to ${_left}s)"
    # The redirections belong to the subshell itself: a still-running installer must not keep the caller's stdout
    # pipe open after the JSON line is printed.
    ( "$@"; exit $? ) >>"$LOG_PATH" 2>&1 </dev/null &
    _pid=$!
    while kill -0 "$_pid" 2>/dev/null; do
        if [ "$(remaining_seconds)" -le 0 ]; then
            log "still running after the time budget: pid $_pid"
            INSTALL_STATUS=timeout
            return 1
        fi
        sleep 1
    done
    wait "$_pid"
    _rc=$?
    log "exit code: $_rc"
    if [ "$_rc" -eq 0 ]; then INSTALL_STATUS=ok; return 0; fi
    INSTALL_STATUS=failed
    return 1
}

install_macos() {
    _brew=$(command -v brew 2>/dev/null)
    for _b in $BREW_BIN_DIRS; do
        if [ -z "$_brew" ] && [ -x "$_b/brew" ]; then _brew="$_b/brew"; fi
    done
    if [ -n "$_brew" ]; then
        if [ "$NEED_PYTHON" = yes ]; then
            run_install env NONINTERACTIVE=1 HOMEBREW_NO_ENV_HINTS=1 HOMEBREW_NO_AUTO_UPDATE=1 "$_brew" install "$BREW_PYTHON"
            install_outcome python "$INSTALL_STATUS"
        fi
        if [ "$NEED_GIT" = yes ]; then
            run_install env NONINTERACTIVE=1 HOMEBREW_NO_ENV_HINTS=1 HOMEBREW_NO_AUTO_UPDATE=1 "$_brew" install git
            install_outcome git "$INSTALL_STATUS"
        fi
    elif ! clt_ready; then
        # Homebrew is never installed here (its installer needs the password). The Command Line Tools bring git
        # and Python 3: this opens the system dialog and returns at once; the user clicks Install.
        run_install xcode-select --install
        add_manual xcode_clt_install 'Máy Mac vừa hiện hộp thoại cài "Command Line Developer Tools" (có sẵn Git và Python). Bấm "Install", đợi cài xong (vài phút) rồi báo mình.'
    else
        if [ "$NEED_PYTHON" = yes ]; then add_python_manual; fi
        if [ "$NEED_GIT" = yes ]; then add_git_manual; fi
    fi
}

linux_outcome() {  # status, applied to every needed item
    if [ "$NEED_PYTHON" = yes ]; then install_outcome python "$1"; fi
    if [ "$NEED_GIT" = yes ]; then install_outcome git "$1"; fi
}

install_linux() {
    _python_pkg=python3
    if command -v apt-get >/dev/null 2>&1; then
        _tool='apt-get install -y'
    elif command -v dnf >/dev/null 2>&1; then
        _tool='dnf install -y'
    elif command -v yum >/dev/null 2>&1; then
        _tool='yum install -y'
    elif command -v zypper >/dev/null 2>&1; then
        _tool='zypper --non-interactive install'
    elif command -v pacman >/dev/null 2>&1; then
        _tool='pacman -S --noconfirm'
        _python_pkg=python
    else
        if [ "$NEED_PYTHON" = yes ]; then add_python_manual; fi
        if [ "$NEED_GIT" = yes ]; then add_git_manual; fi
        return 0
    fi
    _pkgs=''
    if [ "$NEED_PYTHON" = yes ]; then _pkgs=$_python_pkg; fi
    if [ "$NEED_GIT" = yes ]; then _pkgs="$_pkgs${_pkgs:+ }git"; fi
    case "$_tool" in apt-get*) _apt=yes ;; *) _apt=no ;; esac
    if [ "$(id -u)" = 0 ]; then
        _sudo=''
    elif sudo -n true >/dev/null 2>&1; then
        _sudo='sudo -n'
    else
        # The password is typed by the user in their own terminal, never in the chat.
        _cmd="sudo $_tool $_pkgs"
        if [ "$_apt" = yes ]; then _cmd="sudo apt-get update && $_cmd"; fi
        add_manual run_in_terminal "Mở cửa sổ Terminal của máy và chạy lệnh sau (máy sẽ hỏi mật khẩu đăng nhập của bạn; gõ trong Terminal, KHÔNG gửi mật khẩu vào khung chat): $_cmd" "$_cmd"
        return 0
    fi
    if [ "$_apt" = yes ]; then
        run_install $_sudo env DEBIAN_FRONTEND=noninteractive apt-get update
        # A still-running update holds the package lock: the install would only fail.
        if [ "$INSTALL_STATUS" = timeout ] || [ "$INSTALL_STATUS" = skipped ]; then
            linux_outcome "$INSTALL_STATUS"
            return 0
        fi
    fi
    run_install $_sudo env DEBIAN_FRONTEND=noninteractive $_tool $_pkgs
    linux_outcome "$INSTALL_STATUS"
}

# ---------------------------------------------------------------------------- PATH diagnosis

# A usable git outside the PATH this script inherited. On macOS a new Terminal gets the folders listed in
# /etc/paths and /etc/paths.d, so only then does a restart help; otherwise the folder must be added to PATH.
report_git_off_path() {
    _dir=${GIT_CMD%/*}
    if [ "$OS" = macos ] && cat /etc/paths /etc/paths.d/* 2>/dev/null | grep -qx "$_dir"; then
        add_manual restart_claude_code 'Tắt hẳn Claude Code và cả cửa sổ Terminal / VS Code đang chạy nó, rồi mở lại trong thư mục project để nhận công cụ vừa cài.'
        emit restart_required "Git đã có trên máy nhưng Claude Code chưa nhận được. Hãy $RESTART_HINT."
    fi
    _cmd=''
    if [ -x "$_dir/brew" ]; then _cmd="echo 'eval \"\$($_dir/brew shellenv)\"' >> ~/.zprofile"; fi
    add_manual git_not_on_path "Git đã có ở thư mục $_dir nhưng thư mục này chưa nằm trong PATH. Thêm $_dir vào PATH (với Homebrew: chạy lệnh bên dưới trong Terminal), rồi $RESTART_HINT." "$_cmd"
    emit git_not_on_path "Git đã có trên máy ($_dir) nhưng chưa nằm trong PATH nên công cụ không gọi được. Làm theo hướng dẫn bên dưới."
}

# ---------------------------------------------------------------------------- main

item_names() {
    _names=''
    for _item in $MISSING; do
        if [ "$_item" = python ]; then
            _name='Python 3'
        elif [ "$GIT_STATE" = old ]; then
            _name='Git (bản mới hơn)'
        else
            _name='Git'
        fi
        _names="$_names${_names:+, }$_name"
    done
    printf '%s' "$_names"
}

PYTHON_CMD=''
PYTHON_VERSION=''
GIT_CMD=''
GIT_VERSION=''
GIT_ON_PATH=false
MISSING=''
INSTALLED=''

case "$(uname -s 2>/dev/null)" in
    Darwin) OS=macos ;;
    Linux) OS=linux ;;
    MINGW*|MSYS*|CYGWIN*) OS=windows ;;
    *) OS=linux ;;
esac

if [ "$OS" = windows ]; then
    emit use_powershell 'Trên Windows hãy chạy bootstrap.ps1 bằng PowerShell, không chạy bản .sh.'
fi

detect_all
NEED_PYTHON=no
NEED_GIT=no
if [ -z "$PYTHON_CMD" ]; then NEED_PYTHON=yes; fi
if [ "$GIT_STATE" != ok ]; then NEED_GIT=yes; fi

if [ "$MODE" = install ] && { [ "$NEED_PYTHON" = yes ] || [ "$NEED_GIT" = yes ]; }; then
    if [ "$OS" = macos ]; then install_macos; else install_linux; fi
    detect_all
    if [ "$NEED_PYTHON" = yes ] && [ -n "$PYTHON_CMD" ]; then INSTALLED='python'; fi
    if [ "$NEED_GIT" = yes ] && [ "$GIT_STATE" = ok ]; then INSTALLED="$INSTALLED${INSTALLED:+ }git"; fi
fi

if [ -z "$PYTHON_CMD" ]; then MISSING='python'; fi
if [ "$GIT_STATE" != ok ]; then MISSING="$MISSING${MISSING:+ }git"; fi
if [ "$GIT_STATE" = ok ]; then
    _rest=${GIT_VERSION#*.}
    if [ "${GIT_VERSION%%.*}" -eq "$MIN_GIT_MAJOR" ] && [ "${_rest%%.*}" -lt "$TOKEN_FALLBACK_GIT_MINOR" ]; then
        add_warning git_old_for_token_fallback "Git $GIT_VERSION dùng được, nhưng bản 2.31 trở lên mới tự thử lại bằng token GitLab khi đăng nhập lỗi."
    fi
fi

if [ -n "$MISSING" ] && [ "$MODE" = detect ]; then
    # Nothing was attempted yet: the agent announces the items and runs the install mode.
    if [ -z "$PYTHON_CMD" ]; then _error=python_missing
    elif [ "$GIT_STATE" = old ]; then _error=git_too_old
    else _error=git_missing
    fi
    emit "$_error" "Máy chưa có: $(item_names). Trợ lý sẽ cài tự động."
fi

_waiting=yes
for _item in $MISSING; do
    if ! is_still_running "$_item"; then _waiting=no; fi
done
if [ -n "$MISSING" ] && [ "$_waiting" = yes ]; then
    # Every missing item still has its installer running: wait instead of downloading by hand.
    if [ -z "$PYTHON_CMD" ]; then _error=python_missing; else _error=git_missing; fi
    emit "$_error" "Trình cài${STILL_RUNNING} vẫn đang chạy. Đợi vài phút rồi báo mình để kiểm tra lại."
fi

# The generic download steps are only added when no more specific step (CLT dialog, sudo command) guides the user
# and the item's installer is not still running.
case " $MANUAL_CODES " in
    *" xcode_clt_install "*|*" run_in_terminal "*) SPECIFIC_STEP=yes ;;
    *) SPECIFIC_STEP=no ;;
esac
if [ -z "$PYTHON_CMD" ]; then
    if [ "$SPECIFIC_STEP" = no ] && ! is_still_running python; then add_python_manual; fi
    emit python_missing 'Chưa cài được Python 3 tự động. Làm theo hướng dẫn bên dưới rồi báo mình để kiểm tra lại.'
fi
if [ "$GIT_STATE" = missing ]; then
    if [ "$SPECIFIC_STEP" = no ] && ! is_still_running git; then add_git_manual; fi
    emit git_missing 'Chưa cài được Git tự động. Làm theo hướng dẫn bên dưới rồi báo mình để kiểm tra lại.'
fi
if [ "$GIT_STATE" = old ]; then
    if [ "$SPECIFIC_STEP" = no ] && ! is_still_running git; then add_git_manual; fi
    emit git_too_old "Git trên máy quá cũ ($GIT_VERSION; cần 2.23 trở lên) và chưa cập nhật được tự động. Làm theo hướng dẫn bên dưới."
fi
if [ "$GIT_ON_PATH" = false ]; then
    report_git_off_path
fi
emit '' "Đã sẵn sàng: Python $PYTHON_VERSION, git $GIT_VERSION."
