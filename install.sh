#!/bin/bash
# Desktop Agent Installation Script
# Works with Quetzacodetl, OpenCode, and Claude-Code frameworks

set -e

INSTALL_DIR="$HOME/.local/bin"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing Desktop Agent from $PROJECT_DIR"

# Create install directory if it doesn't exist
mkdir -p "$INSTALL_DIR"

# Backup existing installation
if [ -f "$INSTALL_DIR/desktop-agent" ]; then
    echo "Backing up existing installation..."
    cp "$INSTALL_DIR/desktop-agent" "$INSTALL_DIR/desktop-agent.backup-$(date +%Y%m%d-%H%M%S)"
fi

if [ -f "$INSTALL_DIR/desktop-agent.py" ]; then
    echo "Backing up existing desktop-agent.py..."
    cp "$INSTALL_DIR/desktop-agent.py" "$INSTALL_DIR/desktop-agent.py.backup-$(date +%Y%m%d-%H%M%S)"
fi

# Create the wrapper script
cat > "$INSTALL_DIR/desktop-agent" << 'EOF'
#!/bin/bash
# Desktop Agent - Multi-framework compatible wrapper
# Works with Quetzacodetl, OpenCode, and Claude-Code

# Point to the modular version
DESKTOP_AGENT_DIR="$HOME/AI/desktop-agent"
DESKTOP_AGENT_ENTRY="$DESKTOP_AGENT_DIR/desktop-agent.py"

if [ ! -d "$DESKTOP_AGENT_DIR" ]; then
    echo "Error: Desktop Agent not found at $DESKTOP_AGENT_DIR"
    exit 1
fi

if [ ! -f "$DESKTOP_AGENT_ENTRY" ]; then
    echo "Error: Desktop Agent entry point not found at $DESKTOP_AGENT_ENTRY"
    exit 1
fi

# Add the project directory to PYTHONPATH so modular package can be imported
export PYTHONPATH="$DESKTOP_AGENT_DIR:$PYTHONPATH"

# Use system Python for AT-SPI access
exec /usr/bin/python3 "$DESKTOP_AGENT_ENTRY" "$@"
EOF

chmod +x "$INSTALL_DIR/desktop-agent"

echo ""
echo "✓ Desktop Agent installed successfully!"
echo "✓ Location: $INSTALL_DIR/desktop-agent"
echo "✓ Source: $PROJECT_DIR"
echo ""
echo "Test with: desktop-agent --help"
echo ""
echo "The modular version is now active and works with:"
echo "  • Quetzacodetl"
echo "  • OpenCode"
echo "  • Claude-Code"
