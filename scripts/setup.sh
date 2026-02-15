#!/bin/bash
# PlanOpticon setup script
set -e

# Detect operating system
if [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="linux"
else
    echo "Unsupported operating system: $OSTYPE"
    exit 1
fi

# Detect architecture
ARCH=$(uname -m)
if [[ "$ARCH" == "arm64" ]] || [[ "$ARCH" == "aarch64" ]]; then
    ARCH="arm64"
elif [[ "$ARCH" == "x86_64" ]]; then
    ARCH="x86_64"
else
    echo "Unsupported architecture: $ARCH"
    exit 1
fi

echo "Setting up PlanOpticon on $OS ($ARCH)..."

# Check for Python
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is required but not found."
    if [[ "$OS" == "macos" ]]; then
        echo "Please install Python 3 using Homebrew or from python.org."
        echo "  brew install python"
    elif [[ "$OS" == "linux" ]]; then
        echo "Please install Python 3 using your package manager."
        echo "  Ubuntu/Debian: sudo apt install python3 python3-pip python3-venv"
        echo "  Fedora: sudo dnf install python3 python3-pip"
    fi
    exit 1
fi

# Check Python version
PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$(echo $PY_VERSION | cut -d. -f1)
PY_MINOR=$(echo $PY_VERSION | cut -d. -f2)

if [[ "$PY_MAJOR" -lt 3 ]] || [[ "$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 9 ]]; then
    echo "Python 3.9 or higher is required, but found $PY_VERSION."
    echo "Please upgrade your Python installation."
    exit 1
fi

echo "Using Python $PY_VERSION"

# Check for FFmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo "FFmpeg is required but not found."
    if [[ "$OS" == "macos" ]]; then
        echo "Please install FFmpeg using Homebrew:"
        echo "  brew install ffmpeg"
    elif [[ "$OS" == "linux" ]]; then
        echo "Please install FFmpeg using your package manager:"
        echo "  Ubuntu/Debian: sudo apt install ffmpeg"
        echo "  Fedora: sudo dnf install ffmpeg"
    fi
    exit 1
fi

echo "FFmpeg found"

# Create and activate virtual environment
if [[ -d "venv" ]]; then
    echo "Virtual environment already exists"
else
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Determine activate script path
if [[ "$OS" == "macos" ]] || [[ "$OS" == "linux" ]]; then
    ACTIVATE="venv/bin/activate"
fi

echo "Activating virtual environment..."
source "$ACTIVATE"

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "Installing dependencies..."
pip install -e .

# Install optional GPU dependencies if available
if [[ "$OS" == "macos" && "$ARCH" == "arm64" ]]; then
    echo "Installing optional ARM-specific packages for macOS..."
    pip install -r requirements-apple.txt 2>/dev/null || echo "No ARM-specific packages found or could not install them."
elif [[ "$ARCH" == "x86_64" ]]; then
    # Check for NVIDIA GPU
    if [[ "$OS" == "linux" ]] && command -v nvidia-smi &> /dev/null; then
        echo "NVIDIA GPU detected, installing GPU dependencies..."
        pip install -r requirements-gpu.txt 2>/dev/null || echo "Could not install GPU packages."
    fi
fi

# Create example .env file if it doesn't exist
if [[ ! -f ".env" ]]; then
    echo "Creating example .env file..."
    cp .env.example .env
    echo "Please edit the .env file to add your API keys."
fi

echo "Setup complete! PlanOpticon is ready to use."
echo ""
echo "To activate the virtual environment, run:"
echo "  source \"$ACTIVATE\""
echo ""
echo "To run PlanOpticon, use:"
echo "  planopticon --help" 