# Desktop Agent Installation Guide

## Quick Install (Recommended)

```bash
cd /home/mal/AI/desktop-agent
./install.sh
```

This installs a wrapper script that works with:
- **Quetzacodetl**
- **OpenCode** 
- **Claude-Code**

## Verify Installation

```bash
desktop-agent --help
desktop-agent windows
```

## Installation Methods

### Method 1: Wrapper Script (Current)

The `install.sh` script creates a wrapper at `~/.local/bin/desktop-agent` that:
- Sets `PYTHONPATH` to include the modular package
- Uses system Python for AT-SPI access
- Works across all AI frameworks

**Location:** `~/.local/bin/desktop-agent`  
**Source:** `/home/mal/AI/desktop-agent`

### Method 2: Python Package (Optional)

Install as an editable package:

```bash
cd /home/mal/AI/desktop-agent
pip install -e .
```

This creates a `desktop-agent` command using the `[project.scripts]` entry in `pyproject.toml`.

### Method 3: Direct Module Invocation

You can also run directly:

```bash
cd /home/mal/AI/desktop-agent
python3 -m modular.cli --help
```

Or:

```bash
python3 desktop-agent.py --help
```

## Architecture

```
/home/mal/AI/desktop-agent/
├── desktop-agent.py          # Entry point (imports modular.cli)
├── install.sh                # Installation script
├── pyproject.toml            # Python package metadata
├── modular/                  # Modular package
│   ├── __init__.py
│   ├── cli.py               # Main CLI logic
│   ├── input.py             # Input handling
│   ├── window.py            # Window management
│   ├── atspi.py             # AT-SPI element detection
│   ├── ocr.py               # OCR text finding
│   ├── snapshot.py          # UI snapshot generation
│   ├── task_system.py       # Task recording/playback
│   └── config.py            # Configuration
└── ~/.local/bin/
    └── desktop-agent        # Wrapper script (installed)
```

## Dependencies

### System Requirements (Linux)

```bash
# AT-SPI for element detection
sudo apt install python3-pyatspi

# Tesseract for OCR
sudo apt install tesseract-ocr

# xdotool for input automation
sudo apt install xdotool

# scrot for screenshots
sudo apt install scrot
```

### Python Dependencies

```bash
pip install pillow pytesseract requests
```

Or install with optional dev dependencies:

```bash
pip install -e ".[dev]"
```

## Framework Compatibility

The wrapper script is designed to work seamlessly with:

### Claude-Code
```bash
# Just use desktop-agent in Claude Code
desktop-agent snapshot -i
```

### OpenCode
```bash
# Works the same way
desktop-agent windows
```

### Quetzacodetl
```bash
# No special setup needed
desktop-agent --help
```

## Uninstall

```bash
rm ~/.local/bin/desktop-agent
rm ~/.local/bin/desktop-agent.py  # Old monolithic version
rm -rf ~/.cache/desktop-agent     # Task database (optional)
```

## Updating

To update to the latest version:

```bash
cd /home/mal/AI/desktop-agent
git pull  # If using git
./install.sh
```

## Troubleshooting

### Import errors

If you see `ModuleNotFoundError: No module named 'modular'`:

1. Check that `/home/mal/AI/desktop-agent` exists
2. Reinstall: `./install.sh`
3. Verify PYTHONPATH: `echo $PYTHONPATH` (should include the desktop-agent directory)

### AT-SPI not available

```bash
sudo apt install python3-pyatspi
```

### OCR not working

```bash
sudo apt install tesseract-ocr
pip install pytesseract
```

### Permission errors

```bash
chmod +x ~/.local/bin/desktop-agent
```

## Development

For active development:

```bash
cd /home/mal/AI/desktop-agent

# Edit files in modular/
vim modular/cli.py

# Test changes immediately (no reinstall needed)
desktop-agent --help
```

The wrapper script loads from the source directory, so changes are immediately available.

## Notes

- **System Python Required:** Uses `/usr/bin/python3` for AT-SPI access (not venv)
- **Task Database:** Stored in `~/.cache/desktop-agent/tasks.db`
- **Embeddings:** Requires local embedding server at `http://localhost:9086`
- **Modular Design:** All core functionality is in the `modular/` package
