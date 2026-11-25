# Typing Madness Meter for iTerm2

An iTerm2 add-on that measures how mad your typing gets and turns it into a game. It's the iTerm2 version of [herdr-typing-madness-meter](https://github.com/tomasrasymas/herdr-typing-madness-meter): same game, same scoring, built on iTerm2's Python API.

- **Typing Madness Meter:** a small pane under the session you type in shows live WPM, combo, multiplier, accuracy, XP and level. Sparks fly after the text, and the meter shakes harder the faster you type.
- **Speed colors:** the tab of the session you're typing in turns green, then yellow, orange and red as your WPM climbs, and that session's background warms up with your speed. The color always matches the meter's WPM number. When you slow down or stop, your WPM falls over about 10 seconds and the colors cool down with it: red, orange, yellow, green, then off.
- **Milestones:** every 25-key combo, level-up, new WPM record and achievement flashes the background, shows a shaking badge (`COMBO 150!`) and gives the window a little shake. Level-ups, records and achievements also post a notification.
- **Status bar:** an optional status bar component shows `⌨ 87 wpm · 120 combo · LV 7`. Click it for your stats.
- **Stats:** levels, ranks, achievements, daily totals and a streak, kept between sessions.

Try `tmm_demo()` (see [Use](#use)) for a 35-second self-running demo of every effect.

## Requirements

- macOS and a recent iTerm2 (built and tested on 3.7.9)
- iTerm2's Python API enabled: Settings › General › Magic › **Enable Python API**
- iTerm2's Python runtime. iTerm2 offers to install it the first time you run a script, or use Scripts › Manage › Install Python Runtime.

Nothing else: no Node, no compiled helper, no pip packages, and **no Input Monitoring permission**. The meter reads keys through iTerm2's own API, so only keys typed into iTerm2 count.

## Install

```sh
git clone https://github.com/tomasrasymas/iterm2-typing-madness-meter
cd iterm2-typing-madness-meter
sh scripts/install.sh
```

`install.sh` writes a small launcher into `~/Library/Application Support/iTerm2/Scripts/AutoLaunch/`, so iTerm2 starts the meter service on every launch. The launcher runs the code from your clone, so `git pull` updates it (restart the script afterwards in Scripts › Manage).

`install.sh` also starts the service right away. If it didn't (for example, the Python API is off), start it from **Scripts › AutoLaunch › typing_madness_meter.py**.

Then turn the meter on. Bind a key (below), or run this from any iTerm2 session:

```sh
osascript -e 'tell application "iTerm2" to invoke API expression "tmm_toggle()"'
```

### Keyboard shortcuts (recommended)

In iTerm2 › Settings › Keys › Key Bindings, click **+** for each:

| Shortcut (example) | Action | Function |
|---|---|---|
| ⌥⌘T | Invoke Script Function | `tmm_toggle()` |
| ⌥⌘S | Invoke Script Function | `tmm_stats()` |

### Status bar component (optional)

1. Settings › Profiles › Session: enable **Status bar enabled** and click **Configure Status Bar**.
2. Drag **Typing Madness Meter** into the active components.

You can also put the live text in a tab or window title. The variable `\(user.typingMadness)` holds `87 wpm · 120 combo` while you type and is empty otherwise.

### Uninstall

```sh
sh scripts/uninstall.sh
```

Your stats and config are kept.

## Use

| Script function | What it does |
|---|---|
| `tmm_toggle()` | Opens the Typing Madness Meter pane under the active session, or closes it. Keys count and effects run only while it's open. |
| `tmm_stats()` | Opens a split with your level, bests, streak, a 14-day chart and achievements. Any key closes it. |
| `tmm_reset()` | Clears all stats. |
| `tmm_demo()` | Plays a 35-second demo in a new tab. A fake editor types by itself while a demo meter shows every effect. It uses throwaway stats, never touches your real ones, and returns you to your session when it ends. |

Bind them to keys as above, or run them from any key binding, trigger or the status bar.

- Keys count toward whichever session is active. Keys typed while the meter pane itself is active don't count.
- Press `q` in the meter pane to close it.
- **The meter follows you.** When you start typing in another session, it moves under that session without taking focus. That works across splits, tabs and windows. It moves when you type, not when you switch, so clicking around doesn't rearrange anything.
- Closing the session the meter sits under closes the meter too. Closing the whole tab or window moves the meter under the session you land in.
- The meter remembers whether it was on. If it was on when iTerm2 quit, it comes back on the next launch (`autoOpen`).

## Levels and ranks

You earn XP for every character you type. Your level comes from total XP: reaching level *n* takes **100 × n²** XP. There is no maximum level, and your rank changes at these levels:

| Rank | From level | Total XP | ≈ characters at a ×3 multiplier |
|---|---:|---:|---:|
| Hunt & Peck | 0 | 0 | 0 |
| Home Row Hero | 3 | 900 | 300 |
| Keyboard Warrior | 6 | 3,600 | 1,200 |
| Combo Crusher | 10 | 10,000 | 3,300 |
| Terminal Speedster | 15 | 22,500 | 7,500 |
| Clackmaster | 22 | 48,400 | 16,100 |
| Keyboard Demon | 30 | 90,000 | 30,000 |

## Scoring

- **WPM:** (characters ÷ 5) per minute over a rolling 10-second window. Enter counts as a character. A WPM counts toward records only with at least 25 characters in the window, so short bursts don't set fake records.
- **Combo:** characters typed with gaps shorter than 1.2 seconds. A longer pause breaks it. Backspace doesn't break the combo but lowers accuracy. Arrows, Ctrl shortcuts and other keys keep a combo alive without adding to it. Cmd shortcuts aren't counted at all. Holding a key down counts once.
- **Multiplier:** starts at ×1. Every 25 combo keys add ×0.5, up to ×5 (×1.5 at 25, ×3 at 100, ×5 at 200).
- **XP per character:** multiplier × accuracy, where accuracy is the share of your last 200 keys that weren't Backspace. Fast, clean, unbroken typing levels up quickest.
- **Milestones:** every 25 combo, each level-up and each new best WPM (in steps of 5) trigger the flash, badge and shake.

### Achievements

| Achievement | How to unlock |
|---|---|
| First Steps | Type 100 characters |
| Cruising | Reach 60 WPM |
| Ton Up | Reach 100 WPM |
| Ludicrous Speed | Reach 140 WPM |
| Combo Starter | Hit a 100 combo |
| Unbroken | Hit a 500 combo |
| Flow State | Hit a 1000 combo |
| Marathon | Type 10,000 characters in one day |
| Habit Forming | Type 500+ characters 7 days in a row |
| Night Owl | Type 200 characters between 2 and 5 AM |

## Configuration

All settings are optional. Create `~/.config/typing-madness-meter/config.json`. Settings are read when the service starts: restart it in Scripts › Manage after changing them. Leave out any key to keep its default.

### Speed colors

```json
{
  "tierWpm": [25, 45, 65, 85],
  "tierColors": ["#5fd787", "#ffd75f", "#ff8700", "#ff3030"],
  "tabColor": true,
  "tint": true,
  "cooldownMs": 2000
}
```

| Key | Default | Meaning |
|---|---|---|
| `tierWpm` | `[25, 45, 65, 85]` | Minimum WPM for each of the four speed tiers. Must be four increasing numbers. Lower them to see colors sooner, raise them to make red harder to reach. |
| `tierColors` | green, yellow, orange, red | Hex colors (`#rrggbb`) for those four tiers. Used for the tab color, the background tint and the meter's WPM number, blended smoothly between tiers. Below the first tier, the WPM number is gray and the tint is a faint green that fades out. |
| `tabColor` | `true` | Color the tab of the session you're typing in. |
| `tint` | `true` | Tint the typed session's background toward the tier color. It gets stronger the faster you type. |
| `cooldownMs` | `2000` | Extra easing on the way down. The colors follow your WPM, which falls to zero over about 10 seconds after you stop, so the cooldown always takes about that long. Raise this to make the fade softer and a little slower, lower it to track the WPM more tightly. The warm-up while typing is always quick. |

### Score

| Key | Default | Meaning |
|---|---|---|
| `comboGapMs` | `1200` | Longest pause, in milliseconds, before the combo breaks. Raise it for a more forgiving combo. |
| `comboStep` | `25` | Combo keys needed for each extra ×0.5 on the multiplier. Lower it to earn XP faster. |
| `maxMultiplier` | `5` | Highest the multiplier can go. |
| `comboMilestone` | `25` | A combo milestone (flash, badge, shake) fires every this many keys. |

Changing the scoring rules doesn't recalculate XP you've already earned.

### Effects and behavior

| Key | Default | Meaning |
|---|---|---|
| `flash` | `true` | Flash the background on milestones. |
| `milestoneBadge` | `true` | Show a shaking badge (`COMBO 150!`) on milestones. |
| `shake` | `true` | Shake the window on milestones. Does nothing in full screen. |
| `shakePoints` | `6` | How far the window shakes, in points. |
| `statusBar` | `true` | Provide the status bar component and the `user.typingMadness` variable. |
| `toasts` | `true` | Notify on level-ups, records and achievements. |
| `follow` | `true` | Move the meter under whichever session you start typing in. |
| `hudHeight` | `6` | Meter pane height in rows. |
| `autoOpen` | `true` | If the meter was on when iTerm2 quit, turn it back on at the next launch. |
| `statsFile` | unset | Path to the stats file. Point it at the herdr plugin's `stats.json` to share XP between the two (same format). Don't run both at the same time with a shared file: each would overwrite the other's progress. |

## How the effects work, and what they touch

- **Tab color, tint, flash and badge** change only the live session's colors and badge, never your saved profile. When typing moves to another session, the previous one goes back to how it was. Turning the meter off restores everything.
- **Crash safety:** every session the meter changes gets the variable `user.tmmTouched`. If the service dies mid-tint, the next start restores those sessions from their saved profile.
- **Shake** nudges the window frame a few points back and forth for about 160ms, then puts it back exactly. No pane is resized.
- **The meter pane** is an ordinary split running `tmm/viewer.py`, which draws what the service sends it over a unix socket in `~/.local/state/typing-madness-meter/`. The service tags its panes with `user.tmmRole`, so a restarted service finds and reuses them.
- **Notifications** come from the meter pane printing an OSC 9 escape sequence, so iTerm2 posts them under its own name. They follow your iTerm2 notification settings.

## Troubleshooting

- **Nothing happens on `tmm_toggle()`:** check the service is running (Scripts › Manage should list `typing_madness_meter.py`). If it isn't, start it from Scripts › AutoLaunch.
- **The meter turned itself off:** `~/.local/state/typing-madness-meter/meter.log` records when the meter turns on and off, and why: `q` pressed in the meter pane, the meter pane closed, the session above it closed, or a toggle. Errors also go there and to Scripts › Manage › Console.

## Privacy

- The service sees keystrokes only through iTerm2's API. Each key is reduced to one of `char`, `backspace`, `enter` or `other` in `tmm/classify.py`, and the characters are dropped there. Nothing else ever sees them.
- Cmd shortcuts are ignored, and keys typed into other apps never reach it.
- Stats stay on your machine, in `~/.local/state/typing-madness-meter/stats.json`. Nothing is sent anywhere.

## Limitations

- Keys count for the active session of the frontmost iTerm2 window, including hotkey windows.
- Paste doesn't count, and neither does anything a program types for you. Only real key presses do.
- Older iTerm2 versions without advanced key notifications count held-key autorepeat as typing, and ones that can't move sessions reopen the meter pane instead of moving it when it follows you.

## Development

```sh
python3 -m unittest      # stdlib only, no iTerm2 needed
```

During development, run the service from a terminal instead of AutoLaunch (stop the AutoLaunch copy first; a second copy exits if one is already running):

```sh
"$HOME/Library/Application Support/iTerm2/uv/venvs/3.12/bin/python" -c 'import sys; sys.path.insert(0, "."); from tmm.daemon import run; run()'
```

Set `TMM_STATE_DIR` and `TMM_CONFIG_DIR` to keep test runs away from your real stats.

| File | Role |
|---|---|
| `tmm/daemon.py` | The service: keystroke and session monitors, script functions, status bar, frame loop |
| `tmm/meter.py` | One meter: game events → notices, effects and the view the pane shows |
| `tmm/effects.py` | Session-local tab color, tint, flash, badge and window shake, plus restore |
| `tmm/panes.py` | Opening, moving, sizing and closing the meter, demo and stats panes |
| `tmm/feed.py` | The unix socket between the service and its panes |
| `tmm/viewer.py`, `tmm/stats_pane.py`, `tmm/demo_typer.py` | Stdlib-only programs that run inside the panes |
| `tmm/game.py`, `tmm/tiers.py`, `tmm/render.py`, `tmm/stats_view.py`, `tmm/classify.py` | Pure logic, unit-tested |

## License

MIT. See [LICENSE](LICENSE).
