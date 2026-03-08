#!/usr/bin/env bash
# PlanOpticon installer — cross-platform one-command setup
# Usage: curl -fsSL https://planopticon.dev/install.sh | bash
#
# Supports: macOS (Homebrew), Ubuntu/Debian (apt), Fedora/RHEL (dnf), Arch (pacman)
# Idempotent — safe to re-run.

set -euo pipefail

# --- Colors & helpers --------------------------------------------------------

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

info()  { printf "${BLUE}[info]${NC}  %s\n" "$*"; }
ok()    { printf "${GREEN}[ok]${NC}    %s\n" "$*"; }
warn()  { printf "${YELLOW}[warn]${NC}  %s\n" "$*"; }
err()   { printf "${RED}[error]${NC} %s\n" "$*" >&2; }
step()  { printf "\n${BOLD}==> %s${NC}\n" "$*"; }

command_exists() { command -v "$1" >/dev/null 2>&1; }

# --- Detect OS & package manager ---------------------------------------------

detect_os() {
    case "$(uname -s)" in
        Darwin) OS="macos" ;;
        Linux)
            if [ -f /etc/os-release ]; then
                . /etc/os-release
                case "$ID" in
                    ubuntu|debian|pop|linuxmint|elementary) OS="debian" ;;
                    fedora|rhel|centos|rocky|alma) OS="fedora" ;;
                    arch|manjaro|endeavouros) OS="arch" ;;
                    *) OS="linux-unknown" ;;
                esac
            else
                OS="linux-unknown"
            fi
            ;;
        MINGW*|MSYS*|CYGWIN*)
            err "Windows detected. Please use install.ps1 instead:"
            err "  irm https://planopticon.dev/install.ps1 | iex"
            exit 1
            ;;
        *)
            err "Unsupported OS: $(uname -s)"
            exit 1
            ;;
    esac
}

# --- Python ------------------------------------------------------------------

MIN_PYTHON_MAJOR=3
MIN_PYTHON_MINOR=10

find_python() {
    for cmd in python3 python; do
        if command_exists "$cmd"; then
            local ver
            ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null) || continue
            local major minor
            major=$(echo "$ver" | cut -d. -f1)
            minor=$(echo "$ver" | cut -d. -f2)
            if [ "$major" -ge "$MIN_PYTHON_MAJOR" ] && [ "$minor" -ge "$MIN_PYTHON_MINOR" ]; then
                PYTHON="$cmd"
                PYTHON_VERSION="$ver"
                return 0
            fi
        fi
    done
    return 1
}

install_python() {
    step "Installing Python 3.10+"
    case "$OS" in
        macos)
            if command_exists brew; then
                brew install python@3.12
            else
                err "Homebrew not found. Install it first: https://brew.sh"
                exit 1
            fi
            ;;
        debian)
            sudo apt-get update -qq
            sudo apt-get install -y -qq python3 python3-pip python3-venv
            ;;
        fedora)
            sudo dnf install -y -q python3 python3-pip
            ;;
        arch)
            sudo pacman -S --noconfirm python python-pip
            ;;
        *)
            err "Cannot auto-install Python on this OS."
            err "Please install Python ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}+ manually."
            exit 1
            ;;
    esac
}

# --- FFmpeg ------------------------------------------------------------------

install_ffmpeg() {
    step "Installing FFmpeg"
    case "$OS" in
        macos)
            if command_exists brew; then
                brew install ffmpeg
            else
                err "Homebrew not found. Install it first: https://brew.sh"
                exit 1
            fi
            ;;
        debian)
            sudo apt-get update -qq
            sudo apt-get install -y -qq ffmpeg
            ;;
        fedora)
            sudo dnf install -y -q ffmpeg-free || {
                warn "ffmpeg-free not available, trying RPM Fusion..."
                sudo dnf install -y -q \
                    "https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-$(rpm -E %fedora).noarch.rpm" 2>/dev/null || true
                sudo dnf install -y -q ffmpeg
            }
            ;;
        arch)
            sudo pacman -S --noconfirm ffmpeg
            ;;
        *)
            err "Cannot auto-install FFmpeg on this OS."
            err "Please install FFmpeg manually: https://ffmpeg.org/download.html"
            exit 1
            ;;
    esac
}

# --- Ollama (optional) -------------------------------------------------------

install_ollama() {
    step "Installing Ollama"
    if command_exists ollama; then
        ok "Ollama already installed"
        return 0
    fi
    case "$OS" in
        macos)
            if command_exists brew; then
                brew install ollama
            else
                curl -fsSL https://ollama.com/install.sh | sh
            fi
            ;;
        debian|fedora|arch|linux-unknown)
            curl -fsSL https://ollama.com/install.sh | sh
            ;;
    esac
}

pull_ollama_models() {
    info "Pulling recommended local models..."
    ollama pull llama3.2 2>/dev/null || warn "Failed to pull llama3.2"
    ollama pull llava 2>/dev/null || warn "Failed to pull llava (vision model)"
    ok "Ollama models ready"
}

# --- Extras selection --------------------------------------------------------

select_extras() {
    EXTRAS=""
    printf "\n${BOLD}Optional extras:${NC}\n"
    echo "  1) core     — just the basics (default)"
    echo "  2) cloud    — Google Drive, Dropbox, S3 integrations"
    echo "  3) pdf      — PDF document ingestion"
    echo "  4) sources  — YouTube, RSS, web scraping"
    echo "  5) all      — everything"
    echo ""
    printf "Choose extras [1-5, default=1]: "

    if [ -t 0 ]; then
        read -r choice
    else
        choice="1"
        echo "1 (non-interactive, using default)"
    fi

    case "${choice:-1}" in
        2) EXTRAS="[cloud]" ;;
        3) EXTRAS="[pdf]" ;;
        4) EXTRAS="[sources]" ;;
        5) EXTRAS="[all]" ;;
        *) EXTRAS="" ;;
    esac
}

# --- API key setup -----------------------------------------------------------

setup_api_keys() {
    step "API key setup"
    local env_file=".env"

    if [ -f "$env_file" ]; then
        ok "Found existing .env file, skipping API key setup"
        return 0
    fi

    if [ ! -t 0 ]; then
        warn "Non-interactive mode — skipping API key setup"
        info "Create a .env file with at least one API key:"
        info "  OPENAI_API_KEY=sk-..."
        info "  ANTHROPIC_API_KEY=sk-ant-..."
        info "  GEMINI_API_KEY=..."
        return 0
    fi

    printf "\n${BOLD}PlanOpticon needs at least one AI provider API key.${NC}\n"
    echo "You can add more later in .env"
    echo ""
    echo "  1) OpenAI     (OPENAI_API_KEY)"
    echo "  2) Anthropic  (ANTHROPIC_API_KEY)"
    echo "  3) Google     (GEMINI_API_KEY)"
    echo "  4) Ollama     (local, no key needed)"
    echo "  5) Skip for now"
    echo ""
    printf "Choose provider [1-5]: "
    read -r provider_choice

    case "${provider_choice:-5}" in
        1)
            printf "Enter your OpenAI API key: "
            read -r api_key
            if [ -n "$api_key" ]; then
                echo "OPENAI_API_KEY=$api_key" > "$env_file"
                ok "Saved to .env"
            fi
            ;;
        2)
            printf "Enter your Anthropic API key: "
            read -r api_key
            if [ -n "$api_key" ]; then
                echo "ANTHROPIC_API_KEY=$api_key" > "$env_file"
                ok "Saved to .env"
            fi
            ;;
        3)
            printf "Enter your Google/Gemini API key: "
            read -r api_key
            if [ -n "$api_key" ]; then
                echo "GEMINI_API_KEY=$api_key" > "$env_file"
                ok "Saved to .env"
            fi
            ;;
        4)
            info "Using Ollama — no API key needed"
            echo "OLLAMA_HOST=http://localhost:11434" > "$env_file"
            ;;
        5)
            warn "Skipping API key setup. Add keys to .env later."
            ;;
    esac
}

# --- Main --------------------------------------------------------------------

main() {
    printf "\n${BOLD}PlanOpticon Installer${NC}\n"
    echo "====================================="
    echo ""

    detect_os
    info "Detected OS: $OS"

    # --- Python ---
    step "Checking Python"
    if find_python; then
        ok "Python $PYTHON_VERSION found ($PYTHON)"
    else
        warn "Python ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}+ not found"
        install_python
        if ! find_python; then
            err "Python installation failed. Please install Python ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}+ manually."
            exit 1
        fi
        ok "Python $PYTHON_VERSION installed"
    fi

    # --- FFmpeg ---
    step "Checking FFmpeg"
    if command_exists ffmpeg; then
        local ffmpeg_ver
        ffmpeg_ver=$(ffmpeg -version 2>/dev/null | head -1 | awk '{print $3}') || ffmpeg_ver="unknown"
        ok "FFmpeg found ($ffmpeg_ver)"
    else
        warn "FFmpeg not found"
        install_ffmpeg
        if command_exists ffmpeg; then
            ok "FFmpeg installed"
        else
            err "FFmpeg installation failed. Please install manually."
            exit 1
        fi
    fi

    # --- pip install planopticon ---
    step "Installing PlanOpticon"
    select_extras

    local pip_target="planopticon${EXTRAS}"
    info "Installing: $pip_target"

    if "$PYTHON" -m pip install --upgrade "$pip_target" 2>&1; then
        ok "PlanOpticon installed"
    else
        warn "pip install failed, trying with --user flag"
        "$PYTHON" -m pip install --user --upgrade "$pip_target"
        ok "PlanOpticon installed (user)"
    fi

    # --- Ollama (optional) ---
    if [ -t 0 ]; then
        printf "\n${BOLD}Would you like to install Ollama for local AI? [y/N]: ${NC}"
        read -r install_ollama_choice
        if [[ "${install_ollama_choice:-n}" =~ ^[Yy] ]]; then
            install_ollama
            if command_exists ollama; then
                printf "Pull recommended models? (llama3.2 + llava, ~6GB) [y/N]: "
                read -r pull_choice
                if [[ "${pull_choice:-n}" =~ ^[Yy] ]]; then
                    pull_ollama_models
                fi
            fi
        fi
    fi

    # --- API keys ---
    setup_api_keys

    # --- Verify ---
    step "Verifying installation"
    if command_exists planopticon; then
        local version
        version=$(planopticon --version 2>/dev/null || echo "installed")
        ok "planopticon CLI ready ($version)"
    else
        # Might need PATH update
        warn "planopticon not in PATH — you may need to restart your shell"
        info "Or run: $PYTHON -m video_processor.cli.commands --version"
    fi

    if planopticon list-models >/dev/null 2>&1; then
        ok "Provider check passed"
    else
        warn "No AI providers configured yet — add an API key to .env"
    fi

    # --- Done ---
    printf "\n${GREEN}${BOLD}Installation complete!${NC}\n"
    echo ""
    echo "Quick start:"
    echo "  planopticon process video.mp4        # Analyze a video"
    echo "  planopticon companion                # Start AI companion"
    echo "  planopticon list-models              # Check available models"
    echo ""
    echo "Docs: https://planopticon.dev"
    echo ""
}

main "$@"
