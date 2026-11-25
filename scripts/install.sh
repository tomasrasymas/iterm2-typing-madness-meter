#!/bin/sh
# Install the Typing Madness Meter as an iTerm2 AutoLaunch script.
# Writes a small launcher into iTerm2's AutoLaunch folder that runs the code
# from this checkout, so `git pull` updates it. Nothing else is touched.
set -eu

root=$(cd "$(dirname "$0")/.." && pwd)
dir="$HOME/Library/Application Support/iTerm2/Scripts/AutoLaunch"
launcher="$dir/typing_madness_meter.py"

if [ ! -d /Applications/iTerm.app ] && [ ! -d "$HOME/Applications/iTerm.app" ]; then
  echo "iTerm2 not found in /Applications" >&2
  exit 1
fi

mkdir -p "$dir"
cat > "$launcher" <<PY
# Typing Madness Meter launcher, written by $root/scripts/install.sh
# Remove with: sh "$root/scripts/uninstall.sh"
import sys

sys.path.insert(0, "$root")

from tmm.daemon import run

run()
PY

echo "installed $launcher"

# Start it now instead of waiting for the next iTerm2 launch.
if pgrep -f "AutoLaunch/typing_madness_meter.py" >/dev/null 2>&1; then
  echo "already running (restart it in Scripts › Manage to pick up changes)"
elif osascript -e 'tell application "iTerm2" to launch API script named "AutoLaunch/typing_madness_meter.py"' >/dev/null 2>&1; then
  echo "started"
else
  echo "could not start it: use Scripts › AutoLaunch › typing_madness_meter.py"
fi

echo
echo "Next:"
echo "  1. If nothing happens: iTerm2 › Settings › General › Magic › enable the Python API,"
echo "     and accept iTerm2's offer to install its Python runtime."
echo "  2. Turn the meter on from any iTerm2 session:"
echo "       osascript -e 'tell application \"iTerm2\" to invoke API expression \"tmm_toggle()\"'"
echo "  3. Better: bind tmm_toggle() to a key: Settings › Keys › Key Bindings › + ›"
echo "     Action: Invoke Script Function, Function: tmm_toggle()"
