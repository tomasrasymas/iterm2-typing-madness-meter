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
echo
echo "Next:"
echo "  1. iTerm2 › Settings › General › Magic: enable the Python API."
echo "  2. Start it now with Scripts › AutoLaunch › typing_madness_meter.py"
echo "     (iTerm2 offers to install its Python runtime the first time)."
echo "  3. Bind tmm_toggle() to a key: Settings › Keys › Key Bindings › + ›"
echo "     Action: Invoke Script Function, Function: tmm_toggle()"
