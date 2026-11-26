# nuphy-timer

A countdown timer on the two side light bars of a NuPhy Air75 V3.

Press one key, type `30s`, `30m` or `1h`, press Enter. Both bars fill in sync, green to red, then blink and go back to your normal color.

## How it works

- One key sends F13. [skhd](https://github.com/asmvik/skhd) catches it, enters a typing mode, and runs `bar_timer.py`.
- While it waits for typing, the bars blink blue.
- Valid input gives one green blink, then the timer starts. Invalid input gives one red blink, then your color returns.
- Esc, F13 again, or 20 idle seconds cancels. Shift+Esc always leaves typing mode, even if Python is broken.
- Each bar has 10 LEDs. The script sets each LED over USB HID, so the left and right bars can show different things.

## Setup

1. Plug the keyboard in by USB-C and switch it to wired mode. This does not work over Bluetooth or 2.4G.
2. Remap a key to F13. With [nuphyctl](https://github.com/fldc/nuphyctl):
   `nuphyctl keymap set --layer mac.base YELLOW F13`
3. `python3 -m venv .venv && .venv/bin/pip install hidapi`
4. Install skhd (`brew install asmvik/formulae/skhd`), give it Accessibility permission, copy `skhdrc.example` to `~/.skhdrc`, then `skhd --restart-service`.

Other commands: `bar_timer.py run 30s` runs a timer without typing. `bar_timer.py restore` puts the saved side light settings back.

## Caveats

- Tested only on an Air75 V3 with firmware 2.0.0.7. It uses commands that NuPhy does not document, so a firmware update can break it.
- The per-LED colors live in the keyboard's RAM. A reboot clears them, and the script has to keep running.
- Your original side light setting is saved on the first run and restored after each timer.

## experiments/

The scrappy scripts from working out the protocol, kept in the order they were written. Run them from inside that folder.

- `probe_read.py`, `probe_write.py`: read the lighting state, then write it back with one full 17 byte packet.
- `exp1.py` to `exp4.py`: side effect sweep, hidden per-LED table, partial fills, a hold test.
- `exp5.py` to `exp7.py`, `restore_lights.py`: fill demos.

## Credits

The packet format comes from reading these projects:
[nuphyctl](https://github.com/fldc/nuphyctl),
[nuphy-codex-sidelight](https://github.com/joe960913/nuphy-codex-sidelight),
[nuphykit](https://github.com/gig3m/nuphykit).
