# PlanOpticon installer for Windows (PowerShell)
# Usage: irm https://planopticon.dev/install.ps1 | iex

$ErrorActionPreference = "Stop"

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor White }
function Write-Ok($msg)   { Write-Host "[ok]    $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "[warn]  $msg" -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host "[error] $msg" -ForegroundColor Red }
function Write-Info($msg) { Write-Host "[info]  $msg" -ForegroundColor Blue }

function Test-Command($cmd) {
    try { Get-Command $cmd -ErrorAction Stop | Out-Null; return $true }
    catch { return $false }
}

# --- Header ------------------------------------------------------------------

Write-Host "`nPlanOpticon Installer" -ForegroundColor White
Write-Host "=====================================" -ForegroundColor White

# --- Python ------------------------------------------------------------------

Write-Step "Checking Python"

$python = $null
foreach ($cmd in @("python", "python3", "py")) {
    if (Test-Command $cmd) {
        $ver = & $cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if ($ver) {
            $parts = $ver.Split(".")
            if ([int]$parts[0] -ge 3 -and [int]$parts[1] -ge 10) {
                $python = $cmd
                Write-Ok "Python $ver found ($cmd)"
                break
            }
        }
    }
}

if (-not $python) {
    Write-Warn "Python 3.10+ not found"
    if (Test-Command "winget") {
        Write-Info "Installing Python via winget..."
        winget install Python.Python.3.12 --accept-source-agreements --accept-package-agreements
        $python = "python"
    } elseif (Test-Command "choco") {
        Write-Info "Installing Python via Chocolatey..."
        choco install python312 -y
        $python = "python"
    } else {
        Write-Err "Please install Python 3.10+ from https://www.python.org/downloads/"
        exit 1
    }
    # Refresh PATH
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    Write-Ok "Python installed"
}

# --- FFmpeg ------------------------------------------------------------------

Write-Step "Checking FFmpeg"

if (Test-Command "ffmpeg") {
    Write-Ok "FFmpeg found"
} else {
    Write-Warn "FFmpeg not found"
    if (Test-Command "winget") {
        Write-Info "Installing FFmpeg via winget..."
        winget install Gyan.FFmpeg --accept-source-agreements --accept-package-agreements
    } elseif (Test-Command "choco") {
        Write-Info "Installing FFmpeg via Chocolatey..."
        choco install ffmpeg -y
    } else {
        Write-Err "Please install FFmpeg from https://ffmpeg.org/download.html"
        exit 1
    }
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    Write-Ok "FFmpeg installed"
}

# --- Extras ------------------------------------------------------------------

Write-Step "Choose extras"
Write-Host "  1) core     - just the basics (default)"
Write-Host "  2) cloud    - Google Drive, Dropbox, S3"
Write-Host "  3) pdf      - PDF document ingestion"
Write-Host "  4) sources  - YouTube, RSS, web scraping"
Write-Host "  5) all      - everything"
Write-Host ""

$choice = Read-Host "Choose extras [1-5, default=1]"
$extras = switch ($choice) {
    "2" { "[cloud]" }
    "3" { "[pdf]" }
    "4" { "[sources]" }
    "5" { "[all]" }
    default { "" }
}

# --- Install PlanOpticon -----------------------------------------------------

Write-Step "Installing PlanOpticon"

$target = "planopticon$extras"
Write-Info "Installing: $target"

try {
    & $python -m pip install --upgrade $target
    Write-Ok "PlanOpticon installed"
} catch {
    Write-Warn "pip install failed, trying with --user"
    & $python -m pip install --user --upgrade $target
    Write-Ok "PlanOpticon installed (user)"
}

# --- API key setup -----------------------------------------------------------

Write-Step "API key setup"

$envFile = ".env"
if (Test-Path $envFile) {
    Write-Ok "Found existing .env file"
} else {
    Write-Host "`nPlanOpticon needs at least one AI provider API key."
    Write-Host "  1) OpenAI     (OPENAI_API_KEY)"
    Write-Host "  2) Anthropic  (ANTHROPIC_API_KEY)"
    Write-Host "  3) Google     (GEMINI_API_KEY)"
    Write-Host "  4) Ollama     (local, no key needed)"
    Write-Host "  5) Skip for now"
    Write-Host ""

    $providerChoice = Read-Host "Choose provider [1-5]"
    switch ($providerChoice) {
        "1" {
            $key = Read-Host "Enter your OpenAI API key"
            if ($key) { "OPENAI_API_KEY=$key" | Out-File $envFile -Encoding utf8; Write-Ok "Saved to .env" }
        }
        "2" {
            $key = Read-Host "Enter your Anthropic API key"
            if ($key) { "ANTHROPIC_API_KEY=$key" | Out-File $envFile -Encoding utf8; Write-Ok "Saved to .env" }
        }
        "3" {
            $key = Read-Host "Enter your Google/Gemini API key"
            if ($key) { "GEMINI_API_KEY=$key" | Out-File $envFile -Encoding utf8; Write-Ok "Saved to .env" }
        }
        "4" {
            "OLLAMA_HOST=http://localhost:11434" | Out-File $envFile -Encoding utf8
            Write-Info "Using Ollama - no API key needed"
        }
        default { Write-Warn "Skipping API key setup. Add keys to .env later." }
    }
}

# --- Verify ------------------------------------------------------------------

Write-Step "Verifying installation"

if (Test-Command "planopticon") {
    try {
        $version = & planopticon --version 2>$null
        Write-Ok "planopticon CLI ready ($version)"
    } catch {
        Write-Ok "planopticon CLI ready"
    }
} else {
    Write-Warn "planopticon not in PATH - restart your terminal"
}

# --- Done --------------------------------------------------------------------

Write-Host "`nInstallation complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Quick start:"
Write-Host "  planopticon process video.mp4        # Analyze a video"
Write-Host "  planopticon companion                # Start AI companion"
Write-Host "  planopticon list-models              # Check available models"
Write-Host ""
Write-Host "Docs: https://planopticon.dev"
Write-Host ""
