#!/bin/bash

# Install email-client as a systemd user service

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="email-client.service"
SYSTEMD_DIR="$HOME/.config/systemd/user"

echo "Installing $SERVICE_NAME..."

# Create systemd user directory if it doesn't exist
mkdir -p "$SYSTEMD_DIR"

# Copy service file
cp "$SCRIPT_DIR/$SERVICE_NAME" "$SYSTEMD_DIR/$SERVICE_NAME"
echo "Copied service file to $SYSTEMD_DIR/$SERVICE_NAME"

# Reload systemd daemon
systemctl --user daemon-reload
echo "Reloaded systemd daemon"

# Enable and start the service
systemctl --user enable --now "$SERVICE_NAME"
echo "Enabled and started $SERVICE_NAME"

# Show status
echo ""
echo "Service status:"
systemctl --user status "$SERVICE_NAME" --no-pager

echo ""
echo "Installation complete!"
echo "Useful commands:"
echo "  systemctl --user status $SERVICE_NAME    # Check status"
echo "  systemctl --user restart $SERVICE_NAME   # Restart"
echo "  systemctl --user stop $SERVICE_NAME      # Stop"
echo "  journalctl --user -u $SERVICE_NAME       # View logs"
