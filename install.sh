#!/usr/bin/env bash
# BookLinker — macOS local install script
# Run: bash install.sh

set -e

echo "📚 BookLinker — macOS Setup"
echo "----------------------------"

# Check Python
if ! command -v python3 &>/dev/null; then
  echo "❌  Python 3 is required. Install it from https://python.org or via Homebrew: brew install python3"
  exit 1
fi

PYTHON=$(command -v python3)
echo "✓  Python: $($PYTHON --version)"

# Create and activate virtual environment
if [ ! -d ".venv" ]; then
  echo "→  Creating virtual environment..."
  $PYTHON -m venv .venv
fi

source .venv/bin/activate
echo "✓  Virtual environment active"

# Install dependencies
echo "→  Installing dependencies..."
pip install -q -r requirements.txt
echo "✓  Dependencies installed"

# Initialise database
echo "→  Initialising database..."
python3 -c "import app; app.init_db()"
echo "✓  Database ready"

echo ""
echo "✅  Setup complete!"
echo ""
echo "To start BookLinker, run:"
echo "  source .venv/bin/activate && python app.py"
echo ""
echo "Then open: http://localhost:5000"
