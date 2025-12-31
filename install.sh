#!/bin/bash
# esp-remote installation script
# Sets up aliases and bash completions

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHELL_RC=""
MARKER_START="# >>> esp-remote >>>"
MARKER_END="# <<< esp-remote <<<"

# Detect shell
detect_shell() {
    if [[ -n "$ZSH_VERSION" ]] || [[ "$SHELL" == *"zsh"* ]]; then
        SHELL_RC="$HOME/.zshrc"
        SHELL_NAME="zsh"
    elif [[ -n "$BASH_VERSION" ]] || [[ "$SHELL" == *"bash"* ]]; then
        SHELL_RC="$HOME/.bashrc"
        SHELL_NAME="bash"
    else
        echo "Unsupported shell. Please use bash or zsh."
        exit 1
    fi
}

# Uninstall
if [[ "$1" == "uninstall" ]]; then
    detect_shell
    echo "Uninstalling esp-remote..."

    if grep -q "$MARKER_START" "$SHELL_RC" 2>/dev/null; then
        sed -i "/$MARKER_START/,/$MARKER_END/d" "$SHELL_RC"
        echo "Removed configuration from $SHELL_RC"
    fi

    if [[ -d "$HOME/.esp-remote/completions" ]]; then
        rm -rf "$HOME/.esp-remote/completions"
        echo "Removed completions"
    fi

    echo ""
    echo "Uninstalled. Registry preserved at ~/.esp-remote/registry/"
    echo "Run 'source $SHELL_RC' or restart terminal."
    exit 0
fi

# Main install
detect_shell

echo "Installing esp-remote..."
echo "  Project: $SCRIPT_DIR"
echo "  Shell:   $SHELL_NAME ($SHELL_RC)"

# Install/sync dependencies
echo ""
echo "Installing dependencies..."
cd "$SCRIPT_DIR"
uv sync

# Create completions directory
COMPLETIONS_DIR="$HOME/.esp-remote/completions"
mkdir -p "$COMPLETIONS_DIR"

# Generate bash/zsh completions using Click's built-in support
echo "Generating completions..."
if [[ "$SHELL_NAME" == "bash" ]]; then
    _ESP_REMOTE_COMPLETE=bash_source uv run esp-remote > "$COMPLETIONS_DIR/esp-remote.bash"
    COMPLETION_SOURCE="source $COMPLETIONS_DIR/esp-remote.bash"
else
    _ESP_REMOTE_COMPLETE=zsh_source uv run esp-remote > "$COMPLETIONS_DIR/esp-remote.zsh"
    COMPLETION_SOURCE="source $COMPLETIONS_DIR/esp-remote.zsh"
fi

# Shell config block
CONFIG_BLOCK="$MARKER_START
# Installed by esp-remote install.sh
export ESP_REMOTE_HOME=\"$SCRIPT_DIR\"

# esp-remote command (runs via uv)
esp-remote() {
    uv run --project \"\$ESP_REMOTE_HOME\" esp-remote \"\$@\"
}

# Tab completions
$COMPLETION_SOURCE
$MARKER_END"

# Check if already installed
if grep -q "$MARKER_START" "$SHELL_RC" 2>/dev/null; then
    echo ""
    echo "Updating existing configuration in $SHELL_RC..."
    # Remove old block and add new one
    sed -i "/$MARKER_START/,/$MARKER_END/d" "$SHELL_RC"
fi

# Add to shell rc
echo "" >> "$SHELL_RC"
echo "$CONFIG_BLOCK" >> "$SHELL_RC"

echo ""
echo "Installation complete!"
echo ""
echo "Run this to activate now:"
echo "  source $SHELL_RC"
echo ""
echo "Or start a new terminal, then:"
echo "  esp-remote --help"
echo "  esp-remote status"
