# Desktop Agent - Quick Start

## Installation

```bash
cd /home/mal/AI/desktop-agent
./install.sh
```

## Verify

```bash
desktop-agent --help
desktop-agent windows
```

## Framework Compatibility

Works with **all** AI coding frameworks:

| Framework | Status | Usage |
|-----------|--------|-------|
| **Quetzacodetl** | ✅ | `quetzacodetl` → `desktop-agent <cmd>` |
| **OpenCode** | ✅ | `opencode` → `desktop-agent <cmd>` |
| **Claude-Code** | ✅ | `claude` → `desktop-agent <cmd>` |

## Common Commands

```bash
# Window management
desktop-agent windows                    # List all windows
desktop-agent focus Firefox             # Focus a window
desktop-agent active                    # Get active window

# Snapshots
desktop-agent snapshot                  # Full UI snapshot
desktop-agent snapshot -i              # Interactive snapshot with elements

# Input
desktop-agent click 100 200            # Click coordinates
desktop-agent click @e1                # Click element ref
desktop-agent type "Hello World"       # Type text
desktop-agent key Ctrl+c               # Press key combo

# Tasks
desktop-agent tasks                    # List saved tasks
desktop-agent tasks search "firefox"   # Search tasks
desktop-agent replay --run task-name   # Execute task

# Recording
desktop-agent record                   # Start recording
# ... do steps ...
desktop-agent save-task my-task --description "..." --purpose "..."
```

## Architecture

- **Modular Design** - Code split into logical modules
- **Framework Agnostic** - Works anywhere via PYTHONPATH
- **Source-based** - Edits reflected immediately
- **System Python** - Uses `/usr/bin/python3` for AT-SPI

## File Locations

| What | Where |
|------|-------|
| **Source Code** | `/home/mal/AI/desktop-agent/modular/` |
| **Entry Point** | `/home/mal/AI/desktop-agent/desktop-agent.py` |
| **Installed Wrapper** | `~/.local/bin/desktop-agent` |
| **Task Database** | `~/.cache/desktop-agent/tasks.db` |
| **Recordings** | `~/.cache/desktop-agent/recording.json` |

## Development

```bash
cd /home/mal/AI/desktop-agent

# Edit any module
vim modular/cli.py

# Test immediately (no reinstall needed!)
desktop-agent --help
```

## Documentation

| Document | Purpose |
|----------|---------|
| `README.md` | Overview and features |
| `INSTALLATION.md` | Detailed installation guide |
| `MODULAR_MIGRATION.md` | Migration details |
| `COMPLETE_HANDOFF.md` | Full technical handoff |
| `QUICKSTART.md` | This file |

## Support

- **Help:** `desktop-agent --help`
- **Issues:** Check INSTALLATION.md troubleshooting
- **Code:** `/home/mal/AI/desktop-agent/modular/`

---

**Version:** 2.1 (Modular)  
**Last Updated:** 2026-04-17  
**Status:** Production Ready ✅
