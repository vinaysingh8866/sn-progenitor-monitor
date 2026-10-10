#!/bin/bash
LABEL="io.github.sn-progenitor-monitor"
launchctl unload "$HOME/Library/LaunchAgents/$LABEL.plist" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
echo "Removed LaunchAgent. Data in \${SN_MONITOR_DIR:-~/.sn-progenitor-monitor} was left in place."
