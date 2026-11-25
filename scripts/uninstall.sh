#!/bin/sh
# Remove the AutoLaunch launcher. Stats and config are kept in
# ~/.local/state/typing-madness-meter and ~/.config/typing-madness-meter.
set -eu

launcher="$HOME/Library/Application Support/iTerm2/Scripts/AutoLaunch/typing_madness_meter.py"
if [ -f "$launcher" ]; then
  rm "$launcher"
  echo "removed $launcher"
  echo "Restart iTerm2 (or stop the script in Scripts › Manage) to stop the running meter."
else
  echo "not installed"
fi
