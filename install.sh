#!/bin/bash
# Install the SN-progenitor monitor as a daily macOS LaunchAgent.
#
# The package is installed into $PYTHON and the monitor.py shim is copied into
# $SN_MONITOR_DIR because macOS privacy controls block launchd jobs from reading
# ~/Desktop, ~/Documents and ~/Downloads. Override the interpreter with $PYTHON.
set -euo pipefail

SN_MONITOR_DIR="${SN_MONITOR_DIR:-$HOME/.sn-progenitor-monitor}"
PYTHON="${PYTHON:-$(command -v python3)}"
LABEL="io.github.sn-progenitor-monitor"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
HERE="$(cd "$(dirname "$0")" && pwd)"

mkdir -p "$SN_MONITOR_DIR" "$HOME/Library/LaunchAgents"
"$PYTHON" -m pip install --quiet "$HERE[archives]"
cp "$HERE/monitor.py" "$SN_MONITOR_DIR/monitor.py"

cat > "$SN_MONITOR_DIR/run.sh" <<RUN
#!/bin/bash
set -e
cd "$SN_MONITOR_DIR"
echo "==== \$(date -u +%Y-%m-%dT%H:%M:%SZ) ====" >> cron.log
SN_MONITOR_DIR="$SN_MONITOR_DIR" "$PYTHON" -u monitor.py run >> cron.log 2>&1
echo "" >> cron.log
RUN
chmod +x "$SN_MONITOR_DIR/run.sh"

sed -e "s#__DIR__#$SN_MONITOR_DIR#g" -e "s#__HOME__#$HOME#g" -e "s#__LABEL__#$LABEL#g" \
    -e "s#__PYBIN__#$(dirname "$PYTHON")#g" "$HERE/launchagent.plist.template" > "$PLIST"

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
launchctl list | grep -q "$LABEL" && echo "LaunchAgent $LABEL loaded (runs daily; logs in $SN_MONITOR_DIR/cron.log)"
launchctl start "$LABEL"
