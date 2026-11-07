<#
.SYNOPSIS
  Prepares git and Python 3.8+ for the mps-git-flow skill on Windows.

.DESCRIPTION
  Prints exactly ONE line of JSON on stdout and exits 0 when everything is ready, 1 otherwise.
  -DetectOnly only reports what is missing. The default mode also installs the missing items with winget (user
  scope first, so no admin dialog is needed) and then detects again. All installs share one time budget, so the
  JSON line is printed well inside the agent's 10-minute command timeout.
  Installs nothing but git and Python, never prompts, never changes system settings or PATH. Installer output
  goes to %TEMP%\mps-bootstrap.log, never to stdout.

  Compatibility: Windows PowerShell 5.1 (no PowerShell 6+ operators or variables).
  Keep this file UTF-8 WITH BOM: PowerShell 5.1 decodes BOM-less files as ANSI and would garble the Vietnamese
  texts. stdout uses the OEM code page, so every character above U+007E is escaped in the JSON.
  PATH entries are untrusted (missing drives, invalid characters): they are only handled with .NET calls inside
  try/catch, never with Join-Path / Test-Path / Get-Command, which throw on such entries.
#>
[CmdletBinding()]
param([switch]$DetectOnly)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$MIN_PYTHON = [version]'3.8'
$MIN_GIT = [version]'2.23'
$TOKEN_FALLBACK_GIT = [version]'2.31'
$PROBE_TIMEOUT_MS = 20000
# One budget for every winget call together, well below the agent's 10-minute command timeout.
$INSTALL_BUDGET_MS = 500000
# Below this much remaining budget no new install is started.
$MIN_INSTALL_MS = 30000
# APPINSTALLER_CLI_ERROR_INVALID_CL_ARGUMENTS (0x8A150002): an older winget without --disable-interactivity.
$WINGET_INVALID_ARGUMENTS = -1978335230
$PYTHON_WINGET_ID = 'Python.Python.3.12'
$GIT_WINGET_ID = 'Git.Git'
$PYTHON_URL = 'https://www.python.org/downloads/'
$GIT_URL = 'https://git-scm.com/downloads'
$PYTHON_PROBE = "import sys, ssl, json, subprocess, urllib.request; print('%d.%d.%d|%s' % (sys.version_info[:3] + (sys.executable,)))"
$BACKSLASH = [string][char]92
$RESTART_HINT = 'Hãy tắt hẳn Claude Code VÀ cửa sổ VS Code / Terminal đang chạy nó, mở lại trong thư mục project rồi nói "tiếp tục".'

$script:Mode = 'install'
if ($DetectOnly) { $script:Mode = 'detect' }
$script:Clock = [System.Diagnostics.Stopwatch]::StartNew()
$script:LogPath = [System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), 'mps-bootstrap.log')
# mps.py calls git by name, so what counts is the PATH Claude Code passed to this process.
$script:InheritedPath = $env:Path
$script:Warnings = New-Object System.Collections.ArrayList
$script:ManualSteps = New-Object System.Collections.ArrayList
$script:StillRunning = New-Object System.Collections.ArrayList

# ---------------------------------------------------------------------------- output

function ConvertTo-AsciiJsonString([string]$Text) {
    $builder = New-Object System.Text.StringBuilder
    [void]$builder.Append('"')
    foreach ($ch in $Text.ToCharArray()) {
        $code = [int]$ch
        if ($code -eq 34 -or $code -eq 92) {
            [void]$builder.Append($BACKSLASH).Append($ch)
        } elseif ($code -lt 32 -or $code -gt 126) {
            [void]$builder.Append($BACKSLASH).Append('u').Append($code.ToString('x4'))
        } else {
            [void]$builder.Append($ch)
        }
    }
    [void]$builder.Append('"')
    return $builder.ToString()
}

function ConvertTo-AsciiJson($Value) {
    if ($null -eq $Value) { return 'null' }
    if ($Value -is [bool]) {
        if ($Value) { return 'true' }
        return 'false'
    }
    if ($Value -is [int] -or $Value -is [long]) { return [string]$Value }
    if ($Value -is [string]) { return (ConvertTo-AsciiJsonString $Value) }
    $parts = New-Object System.Collections.Generic.List[string]
    if ($Value -is [System.Collections.IDictionary]) {
        foreach ($key in $Value.Keys) {
            $parts.Add((ConvertTo-AsciiJsonString ([string]$key)) + ':' + (ConvertTo-AsciiJson $Value[$key]))
        }
        return '{' + ($parts -join ',') + '}'
    }
    if ($Value -is [System.Collections.IEnumerable]) {
        foreach ($item in $Value) { $parts.Add((ConvertTo-AsciiJson $item)) }
        return '[' + ($parts -join ',') + ']'
    }
    return (ConvertTo-AsciiJsonString ([string]$Value))
}

function Write-Log([string]$Text) {
    try { Add-Content -LiteralPath $script:LogPath -Value $Text -Encoding UTF8 } catch { }
}

function Add-Warning([string]$Code, [string]$Message, [string]$Item) {
    foreach ($existing in $script:Warnings) {
        if ($existing['code'] -eq $Code -and [string]$existing['item'] -eq [string]$Item) { return }
    }
    $warning = [ordered]@{ code = $Code; message = $Message }
    if ($Item) { $warning['item'] = $Item }
    [void]$script:Warnings.Add($warning)
}

function Add-ManualStep([string]$Code, [string]$Message, [string]$Url) {
    foreach ($existing in $script:ManualSteps) {
        if ($existing['code'] -eq $Code) { return }
    }
    $step = [ordered]@{ code = $Code; message = $Message }
    if ($Url) { $step['url'] = $Url }
    [void]$script:ManualSteps.Add($step)
}

function Add-PythonManualStep {
    Add-ManualStep 'install_python_manual' 'Tải và cài Python 3 từ trang python.org. Khi cài trên Windows nhớ tích ô "Add python.exe to PATH".' $PYTHON_URL
}

function Add-GitManualStep {
    Add-ManualStep 'install_git_manual' 'Tải và cài Git từ trang git-scm.com (giữ các lựa chọn mặc định).' $GIT_URL
}

# ---------------------------------------------------------------------------- safe paths

function Join-PathSafe([string]$Base, [string]$Child) {
    if (-not $Base) { return $null }
    try { return [System.IO.Path]::Combine($Base, $Child) } catch { return $null }
}

function Test-FileSafe([string]$Path) {
    if (-not $Path) { return $false }
    try { return [System.IO.File]::Exists($Path) } catch { return $false }
}

function Get-FullPathSafe([string]$Path) {
    try { return [System.IO.Path]::GetFullPath($Path).ToLowerInvariant() } catch { return ([string]$Path).ToLowerInvariant() }
}

# The first existing <dir>\<ExeName> along a PATH string. Entries that cannot be combined (invalid characters)
# are logged and skipped; missing drives simply do not exist.
function Find-OnPathText([string]$PathText, [string]$ExeName) {
    foreach ($dir in ([string]$PathText -split ';')) {
        $clean = $dir.Trim().Trim('"')
        if (-not $clean) { continue }
        $candidate = Join-PathSafe $clean $ExeName
        if (-not $candidate) {
            Write-Log ('skipped PATH entry: ' + $clean)
            continue
        }
        if (Test-FileSafe $candidate) { return $candidate }
    }
    return $null
}

# PATH as stored in the registry (Machine + User): what a freshly started Claude Code will see.
function Get-RegistryPath {
    $parts = @()
    foreach ($scope in @('Machine', 'User')) {
        try {
            $value = [Environment]::GetEnvironmentVariable('Path', $scope)
            if ($value) { $parts += [Environment]::ExpandEnvironmentVariables($value) }
        } catch {
            Write-Log ('cannot get the ' + $scope + ' PATH: ' + $_.Exception.Message)
        }
    }
    return ($parts -join ';')
}

# ---------------------------------------------------------------------------- processes

function Get-RemainingMs {
    return [int]($INSTALL_BUDGET_MS - $script:Clock.ElapsedMilliseconds)
}

# Runs a program without a console prompt: stdin closed, stdout/stderr captured. Code is $null when the program
# cannot start; TimedOut is set when it did not finish in time (it is killed only when asked).
function Invoke-Captured([string]$File, [string]$Arguments, [int]$TimeoutMs, [bool]$KillOnTimeout) {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $File
    $psi.Arguments = $Arguments
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardInput = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8
    # Python prints sys.executable; a non-ASCII user folder must not break the probe.
    $psi.EnvironmentVariables['PYTHONIOENCODING'] = 'utf-8'
    try {
        $process = [System.Diagnostics.Process]::Start($psi)
    } catch {
        return @{ Code = $null; Out = ''; Err = $_.Exception.Message; TimedOut = $false }
    }
    $process.StandardInput.Close()
    $outTask = $process.StandardOutput.ReadToEndAsync()
    $errTask = $process.StandardError.ReadToEndAsync()
    if (-not $process.WaitForExit($TimeoutMs)) {
        if ($KillOnTimeout) {
            try { $process.Kill() } catch { }
        }
        return @{ Code = $null; Out = ''; Err = ('timed out after ' + $TimeoutMs + ' ms'); TimedOut = $true }
    }
    return @{ Code = $process.ExitCode; Out = $outTask.Result; Err = $errTask.Result; TimedOut = $false }
}

# Long-running installers. Started through cmd.exe with ShellExecute, so the installer inherits NO handle: with
# redirected output (.NET Framework) it would inherit this script's stdout and keep the agent's pipe open after the
# JSON line when it outlives the time budget. cmd appends the installer output to the log itself. Code is the
# installer's exit code; TimedOut means it is still running (it is never killed).
function Invoke-Detached([string]$File, [string]$Arguments, [int]$TimeoutMs) {
    Write-Log ('> ' + $File + ' ' + $Arguments + ' (wait up to ' + $TimeoutMs + ' ms)')
    $shell = $env:ComSpec
    if (-not $shell) { $shell = [System.IO.Path]::Combine([Environment]::SystemDirectory, 'cmd.exe') }
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $shell
    # cmd /c drops the outer quotes and keeps the quoted program and log paths.
    $psi.Arguments = '/d /c ""' + $File + '" ' + $Arguments + ' >> "' + $script:LogPath + '" 2>&1"'
    $psi.UseShellExecute = $true
    $psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
    try {
        $process = [System.Diagnostics.Process]::Start($psi)
    } catch {
        Write-Log ('cannot start: ' + $_.Exception.Message)
        return @{ Code = $null; TimedOut = $false }
    }
    if (-not $process.WaitForExit($TimeoutMs)) {
        Write-Log ('still running after ' + $TimeoutMs + ' ms')
        return @{ Code = $null; TimedOut = $true }
    }
    $code = $process.ExitCode
    Write-Log ('exit code: ' + $code)
    return @{ Code = $code; TimedOut = $false }
}

# ---------------------------------------------------------------------------- detection

function Get-GitInfo([string]$Path, [bool]$OnPath) {
    $run = Invoke-Captured $Path '--version' $PROBE_TIMEOUT_MS $true
    if ($run.Code -ne 0) { return $null }
    $match = [regex]::Match([string]$run.Out, 'git version (\d+)\.(\d+)(?:\.(\d+))?')
    if (-not $match.Success) { return $null }
    $text = $match.Groups[1].Value + '.' + $match.Groups[2].Value
    if ($match.Groups[3].Success) { $text = $text + '.' + $match.Groups[3].Value }
    return @{ Cmd = $Path; Version = $text; Parsed = [version]$text; OnPath = $OnPath }
}

# The first git that runs and is new enough wins; otherwise the first one that runs (reported as too old).
function Find-Git {
    $inherited = Find-OnPathText $script:InheritedPath 'git.exe'
    $candidates = New-Object System.Collections.ArrayList
    [void]$candidates.Add($inherited)
    [void]$candidates.Add((Find-OnPathText $env:Path 'git.exe'))
    foreach ($base in @($env:ProgramFiles, ${env:ProgramFiles(x86)})) {
        [void]$candidates.Add((Join-PathSafe $base 'Git\cmd\git.exe'))
    }
    [void]$candidates.Add((Join-PathSafe $env:LOCALAPPDATA 'Programs\Git\cmd\git.exe'))
    $inheritedKey = $null
    if ($inherited) { $inheritedKey = Get-FullPathSafe $inherited }
    $seen = @{}
    $fallback = $null
    foreach ($path in $candidates) {
        if (-not (Test-FileSafe $path)) { continue }
        $key = Get-FullPathSafe $path
        if ($seen.ContainsKey($key)) { continue }
        $seen[$key] = $true
        $info = Get-GitInfo $path ([bool]($key -eq $inheritedKey))
        if ($null -eq $info) { continue }
        if ($info.Parsed -ge $MIN_GIT) { return $info }
        if ($null -eq $fallback) { $fallback = $info }
    }
    return $fallback
}

function Get-GitState($Git) {
    if ($null -eq $Git) { return 'missing' }
    if ($Git.Parsed -lt $MIN_GIT) { return 'old' }
    return 'ok'
}

function Test-PythonCandidate([string]$File, [string]$Prefix) {
    $arguments = ($Prefix + ' -c "' + $PYTHON_PROBE + '"').Trim()
    $run = Invoke-Captured $File $arguments $PROBE_TIMEOUT_MS $true
    if ($run.Code -ne 0) {
        Write-Log ('python probe failed: ' + $File + ' ' + $Prefix + ' (' + $run.Code + ') ' + $run.Err)
        return $null
    }
    $lines = @(([string]$run.Out -split "`r?`n") | Where-Object { $_.Trim() })
    if ($lines.Count -eq 0) { return $null }
    $match = [regex]::Match($lines[$lines.Count - 1].Trim(), '^(\d+)\.(\d+)\.(\d+)\|(.+)$')
    if (-not $match.Success) { return $null }
    $version = $match.Groups[1].Value + '.' + $match.Groups[2].Value + '.' + $match.Groups[3].Value
    if ([version]$version -lt $MIN_PYTHON) { return $null }
    return @{ Cmd = $match.Groups[4].Value.Trim(); Version = $version }
}

# python.exe in the per-user and machine install folders, newest Python3<minor> folder first.
function Get-PythonFolderCandidates {
    $files = New-Object System.Collections.ArrayList
    foreach ($root in @((Join-PathSafe $env:LOCALAPPDATA 'Programs\Python'), $env:ProgramFiles)) {
        if (-not $root) { continue }
        try {
            $folders = [System.IO.Directory]::GetDirectories($root, 'Python3*')
        } catch {
            continue
        }
        $sorted = $folders | Sort-Object -Descending -Property @{ Expression = {
            $minor = [regex]::Match([System.IO.Path]::GetFileName($_), '^Python3(\d+)')
            if ($minor.Success) { [int]$minor.Groups[1].Value } else { -1 }
        } }
        foreach ($folder in $sorted) {
            $exe = Join-PathSafe $folder 'python.exe'
            if (Test-FileSafe $exe) { [void]$files.Add($exe) }
        }
    }
    return $files
}

function Find-Python {
    $candidates = New-Object System.Collections.ArrayList
    $launcher = Find-OnPathText $env:Path 'py.exe'
    if ($launcher) { [void]$candidates.Add(@{ File = $launcher; Prefix = '-3' }) }
    foreach ($name in @('python3.exe', 'python.exe')) {
        $path = Find-OnPathText $env:Path $name
        if ($path) { [void]$candidates.Add(@{ File = $path; Prefix = '' }) }
    }
    foreach ($path in (Get-PythonFolderCandidates)) { [void]$candidates.Add(@{ File = $path; Prefix = '' }) }
    foreach ($candidate in $candidates) {
        $found = Test-PythonCandidate $candidate.File $candidate.Prefix
        if ($found) { return $found }
        # An App execution alias: the Store stub (or a broken Store Python); never use it.
        if ($candidate.File -like '*\Microsoft\WindowsApps\*') {
            Add-Warning 'store_stub_detected' 'Lệnh python trên máy là lối tắt tới Microsoft Store, không phải Python thật; đã bỏ qua nó.' ''
        }
    }
    return $null
}

# ---------------------------------------------------------------------------- installation

# Returns 'ok', 'failed', 'timeout' (the installer is still running) or 'skipped' (no budget left).
function Invoke-Winget([string]$Winget, [string]$Verb, [string]$Id, [bool]$UserScope) {
    $flags = @($Verb, '-e', '--id', $Id, '--source', 'winget')
    if ($UserScope) { $flags += @('--scope', 'user') }
    $flags += @('--silent', '--accept-package-agreements', '--accept-source-agreements')
    $arguments = (@($flags) + @('--disable-interactivity')) -join ' '
    for ($attempt = 0; $attempt -lt 2; $attempt++) {
        $remaining = Get-RemainingMs
        if ($remaining -lt $MIN_INSTALL_MS) {
            Write-Log ('no time left for: winget ' + $arguments)
            return 'skipped'
        }
        $run = Invoke-Detached $Winget $arguments $remaining
        if ($run.TimedOut) { return 'timeout' }
        if ($run.Code -eq 0) { return 'ok' }
        if ($run.Code -ne $WINGET_INVALID_ARGUMENTS) { return 'failed' }
        $arguments = $flags -join ' '
    }
    return 'failed'
}

# User scope first (no admin dialog), then machine scope (Windows may ask for permission).
function Install-WithWinget([string]$Winget, [string]$Id) {
    $status = Invoke-Winget $Winget 'install' $Id $true
    if ($status -ne 'failed') { return $status }
    Add-Warning 'uac_prompt_possible' 'Windows có thể hiện hộp thoại hỏi quyền cài đặt; hãy bấm Có (Yes).' ''
    return (Invoke-Winget $Winget 'install' $Id $false)
}

function Register-InstallOutcome([string]$Item, [string]$Status) {
    if ($Status -eq 'ok') { return }
    if ($Status -eq 'timeout') {
        # No manual download while the installer may still finish on its own.
        Add-Warning 'install_still_running' ('Trình cài ' + $Item + ' vẫn đang chạy (lâu hơn thời gian chờ). Đợi vài phút cho cài xong rồi báo mình để kiểm tra lại; chưa cần tự tải về cài.') $Item
        [void]$script:StillRunning.Add($Item)
        return
    }
    Add-Warning 'install_failed' ('Cài ' + $Item + ' tự động không thành công (xem log: ' + $script:LogPath + ').') $Item
    if ($Item -eq 'python') { Add-PythonManualStep } else { Add-GitManualStep }
}

function Find-Winget {
    $winget = Find-OnPathText $env:Path 'winget.exe'
    if ($winget) { return $winget }
    $alias = Join-PathSafe $env:LOCALAPPDATA 'Microsoft\WindowsApps\winget.exe'
    if (Test-FileSafe $alias) { return $alias }
    return $null
}

function Install-Missing($NeedPython, $GitState) {
    $winget = Find-Winget
    if (-not $winget) {
        Add-Warning 'winget_missing' 'Máy chưa có winget (App Installer) nên không cài tự động được.' ''
        if ($NeedPython) { Add-PythonManualStep }
        if ($GitState -ne 'ok') { Add-GitManualStep }
        return
    }
    if ($NeedPython) {
        Register-InstallOutcome 'python' (Install-WithWinget $winget $PYTHON_WINGET_ID)
    }
    if ($GitState -eq 'missing') {
        Register-InstallOutcome 'git' (Install-WithWinget $winget $GIT_WINGET_ID)
    } elseif ($GitState -eq 'old') {
        # An upgrade keeps the existing install's scope; a git winget does not know gets a fresh install.
        $status = Invoke-Winget $winget 'upgrade' $GIT_WINGET_ID $false
        if ($status -eq 'failed') { $status = Install-WithWinget $winget $GIT_WINGET_ID }
        Register-InstallOutcome 'git' $status
    }
}

# ---------------------------------------------------------------------------- PATH diagnosis

function Get-ParentFolder([string]$Path) {
    try { return [System.IO.Path]::GetDirectoryName($Path) } catch { return $Path }
}

# A usable git that is not on the PATH Claude Code started with. A restart only helps when the registry PATH
# (what a new Claude Code inherits) resolves "git" to a git that is new enough.
function Get-OffPathDiagnosis($Git, [bool]$InstalledNow) {
    $folder = Get-ParentFolder $Git.Cmd
    $registryGit = Find-OnPathText (Get-RegistryPath) 'git.exe'
    $first = $null
    if ($registryGit) { $first = Get-GitInfo $registryGit $false }
    if ($first -and $first.Parsed -ge $MIN_GIT) {
        Add-ManualStep 'restart_claude_code' 'Tắt hẳn Claude Code và cả cửa sổ VS Code / Terminal đang chạy nó, rồi mở lại trong thư mục project để nhận công cụ vừa cài.' ''
        if ($InstalledNow) {
            return @{ Error = 'restart_required'; Message = ('Đã cài xong Git, nhưng cần khởi động lại Claude Code để dùng được. ' + $RESTART_HINT) }
        }
        return @{ Error = 'restart_required'; Message = ('Git đã có trên máy nhưng Claude Code chưa nhận được. ' + $RESTART_HINT) }
    }
    if ($first) {
        $oldFolder = Get-ParentFolder $first.Cmd
        Add-ManualStep 'git_not_on_path' ('Trong PATH của Windows, Git cũ ' + $first.Version + ' ở thư mục ' + $oldFolder + ' đứng trước Git mới ở ' + $folder + '. Gỡ Git cũ (hoặc xoá thư mục ' + $oldFolder + ' khỏi PATH), rồi tắt hẳn Claude Code và cửa sổ VS Code / Terminal đang chạy nó và mở lại.') ''
        return @{ Error = 'git_too_old'; Message = ('Git trên máy quá cũ (' + $first.Version + '; cần 2.23 trở lên) và chưa cập nhật được tự động. Làm theo hướng dẫn bên dưới.') }
    }
    Add-ManualStep 'git_not_on_path' ('Git đã có ở thư mục ' + $folder + ' nhưng thư mục này chưa nằm trong PATH của Windows. Thêm ' + $folder + ' vào PATH (Settings > System > About > Advanced system settings > Environment Variables > Path), rồi tắt hẳn Claude Code và cửa sổ VS Code / Terminal đang chạy nó và mở lại.') ''
    return @{ Error = 'git_not_on_path'; Message = ('Git đã có trên máy (' + $folder + ') nhưng chưa nằm trong PATH nên công cụ không gọi được. Làm theo hướng dẫn bên dưới.') }
}

# ---------------------------------------------------------------------------- main

function Get-ItemNames($Missing, $GitState) {
    $names = @()
    foreach ($item in $Missing) {
        if ($item -eq 'python') { $names += 'Python 3' }
        elseif ($GitState -eq 'old') { $names += 'Git (bản mới hơn)' }
        else { $names += 'Git' }
    }
    return ($names -join ', ')
}

function Invoke-Main {
    try {
        Set-Content -LiteralPath $script:LogPath -Value ('mps bootstrap ' + (Get-Date -Format s) + ' mode=' + $script:Mode) -Encoding UTF8
    } catch { }
    $python = Find-Python
    $git = Find-Git
    $initialGitState = Get-GitState $git
    $installed = New-Object System.Collections.ArrayList
    if ((-not $DetectOnly) -and ((-not $python) -or $initialGitState -ne 'ok')) {
        Install-Missing (-not $python) $initialGitState
        # Installers update the registry PATH, not this process; the known folders cover a PATH that is still stale.
        $env:Path = Get-RegistryPath
        $hadPython = [bool]$python
        $python = Find-Python
        $git = Find-Git
        if ((-not $hadPython) -and $python) { [void]$installed.Add('python') }
        if ($initialGitState -ne 'ok' -and (Get-GitState $git) -eq 'ok') { [void]$installed.Add('git') }
    }
    $gitState = Get-GitState $git
    $missing = New-Object System.Collections.ArrayList
    if (-not $python) { [void]$missing.Add('python') }
    if ($gitState -ne 'ok') { [void]$missing.Add('git') }
    if ($gitState -eq 'ok' -and $git.Parsed -lt $TOKEN_FALLBACK_GIT) {
        Add-Warning 'git_old_for_token_fallback' ('Git ' + $git.Version + ' dùng được, nhưng bản 2.31 trở lên mới tự thử lại bằng token GitLab khi đăng nhập lỗi.') ''
    }

    $errorCode = $null
    $message = ''
    if ($missing.Count -gt 0 -and $DetectOnly) {
        # Nothing was attempted yet: the agent announces the items and runs the install mode.
        if (-not $python) { $errorCode = 'python_missing' }
        elseif ($gitState -eq 'old') { $errorCode = 'git_too_old' }
        else { $errorCode = 'git_missing' }
        $message = 'Máy chưa có: ' + (Get-ItemNames $missing $gitState) + '. Trợ lý sẽ cài tự động.'
    } elseif ($missing.Count -gt 0 -and @($missing | Where-Object { -not $script:StillRunning.Contains($_) }).Count -eq 0) {
        # Every missing item still has its installer running: wait instead of downloading by hand.
        $errorCode = 'python_missing'
        if ($python) { $errorCode = 'git_missing' }
        $message = 'Trình cài ' + ($script:StillRunning -join ', ') + ' vẫn đang chạy. Đợi vài phút rồi báo mình để kiểm tra lại.'
    } elseif (-not $python) {
        $errorCode = 'python_missing'
        if (-not $script:StillRunning.Contains('python')) { Add-PythonManualStep }
        $message = 'Chưa cài được Python 3 tự động. Làm theo hướng dẫn bên dưới rồi báo mình để kiểm tra lại.'
    } elseif ($gitState -eq 'missing') {
        $errorCode = 'git_missing'
        if (-not $script:StillRunning.Contains('git')) { Add-GitManualStep }
        $message = 'Chưa cài được Git tự động. Làm theo hướng dẫn bên dưới rồi báo mình để kiểm tra lại.'
    } elseif ($gitState -eq 'old') {
        $errorCode = 'git_too_old'
        if (-not $script:StillRunning.Contains('git')) { Add-GitManualStep }
        $message = 'Git trên máy quá cũ (' + $git.Version + '; cần 2.23 trở lên) và chưa cập nhật được tự động. Làm theo hướng dẫn bên dưới.'
    } elseif (-not $git.OnPath) {
        # mps.py calls "git" by name: a git outside the PATH Claude Code started with is not usable yet.
        $diagnosis = Get-OffPathDiagnosis $git ($installed.Contains('git'))
        $errorCode = $diagnosis.Error
        $message = $diagnosis.Message
    } else {
        $message = 'Đã sẵn sàng: Python ' + $python.Version + ', git ' + $git.Version + '.'
    }

    $result = [ordered]@{
        ok = ($null -eq $errorCode)
        os = 'windows'
        mode = $script:Mode
        python_cmd = $null
        python_version = $null
        git_cmd = $null
        git_version = $null
        git_on_path = $false
        missing = $missing
        installed = $installed
        manual_steps = $script:ManualSteps
        warnings = $script:Warnings
        log_path = $script:LogPath
        error = $errorCode
        message = $message
    }
    if ($python) {
        $result['python_cmd'] = $python.Cmd
        $result['python_version'] = $python.Version
    }
    if ($git) {
        $result['git_cmd'] = $git.Cmd
        $result['git_version'] = $git.Version
        $result['git_on_path'] = [bool]$git.OnPath
    }
    return $result
}

try {
    # A stray value written to the pipeline by any helper must never become a second output: the result is last.
    $outputs = @(Invoke-Main)
    $result = $outputs[$outputs.Count - 1]
} catch {
    Write-Log ('bootstrap failed: ' + $_.Exception.ToString())
    $result = [ordered]@{
        ok = $false
        os = 'windows'
        mode = $script:Mode
        python_cmd = $null
        python_version = $null
        git_cmd = $null
        git_version = $null
        git_on_path = $false
        missing = @()
        installed = @()
        manual_steps = @()
        warnings = @()
        log_path = $script:LogPath
        error = 'bootstrap_failed'
        message = ('Script chuẩn bị môi trường gặp lỗi không mong muốn. Xem chi tiết trong file log: ' + $script:LogPath + '.')
        details = $_.Exception.Message
    }
}
[Console]::Out.WriteLine((ConvertTo-AsciiJson $result))
if ($result['ok']) { exit 0 }
exit 1
