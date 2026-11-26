#!/usr/bin/env python3
"""Countdown timer on the NuPhy Air75 V3 side light bars (USB, wired mode).

Both bars fill in sync, green -> yellow -> orange -> red, over the given time.
Run again while a timer runs to cancel it. Lights are restored at the end.

    bar_timer.py 10        # 10 second timer (toggle: run again to cancel)
    bar_timer.py 25m       # also accepts 90s / 25m / 1h
    bar_timer.py restore   # put the saved side-light settings back

Protocol notes (stock firmware 2.0.0.7, verified by readback):
  0xD5/0xD6  read/write the 17-byte lighting state; byte 9 = side effect,
             side effect 5 = "custom", which renders the per-LED table.
  0xD8       per-LED table, records (index, R, G, B); side LEDs: 84-93 and 94-103.
  Writes use a per-transaction session key (0x55 0xEE handshake).
"""
import colorsys
import os
import secrets
import signal
import sys
import time
from pathlib import Path

import hid

VID, PID = 0x19F5, 0x1028
STATE_DIR = Path.home() / ".local/state/bar-timer"
PID_FILE = STATE_DIR / "pid"
SIDE_FILE = STATE_DIR / "side.hex"          # saved side-light settings (8 bytes)
DEFAULT_SIDE = bytes([2, 100, 4, 0, 0, 252, 22, 22])   # static red, used if nothing saved
RED_FROM = 0.6                              # last 40% of each bar is solid red
BLINK_GAP = 0.4                             # seconds: on, off, and pause before restore
BARS = (84, 94)                             # first LED index of each bar (10 LEDs each)


def frame(cmd, length, addr=0, key=0, payload=b""):
    out = bytearray(64)
    out[:2] = bytes([0x55, cmd])
    out[4:8] = bytes(x ^ key for x in (length, addr & 255, addr >> 8, 0))
    out[8:8 + len(payload)] = bytes(x ^ key for x in payload)
    out[3] = sum(out[4:]) & 255
    return out


class Keyboard:
    def __init__(self):
        found = [d for d in hid.enumerate(VID, PID) if d["usage_page"] == 1 and d["usage"] == 0]
        if len(found) != 1:
            raise SystemExit("Air75 V3 not found over USB (plug in and use wired mode)")
        self.dev = hid.device()
        self.dev.open_path(found[0]["path"])

    def _ex(self, pkt):
        self.dev.write(b"\x00" + bytes(pkt))
        end = time.monotonic() + 1.5
        while time.monotonic() < end:
            r = bytes(self.dev.read(64, 100))
            if r[:2] == bytes([0xAA, pkt[1]]):
                return r
        raise RuntimeError("keyboard did not answer")

    def _session(self):
        h = bytearray(64)
        h[:2] = b"\x55\xee"
        h[8:] = secrets.token_bytes(56)
        key = h[28] or 0xAA
        h[28] = key
        h[3] = sum(h[4:]) & 255
        self._ex(h)
        return key

    def txn(self, cmd, length, payload=b""):
        key = self._session()
        r = self._ex(frame(cmd, length, 0, key, payload))
        return bytes(x ^ key for x in r[8:8 + length])

    def state(self):
        return self.txn(0xD5, 17)

    def write_state(self, s):
        self.txn(0xD6, 17, bytes(s))

    def set_leds(self, recs):
        """recs: [(led, r, g, b)], sent in frames of 14 (no reply expected)."""
        for i in range(0, len(recs), 14):
            data = bytes(x for rec in recs[i:i + 14] for x in rec)
            key = self._session()
            self.dev.write(b"\x00" + bytes(frame(0xD8, len(data), 0, key, data)))
            time.sleep(0.05)
            while self.dev.read(64, 20):    # drain any reply
                pass

    def close(self):
        self.dev.close()


def grad(k):
    """Color of LED k (0 = start/green ... 9 = end/red)."""
    hue = 120 * (1 - min(1.0, (k / 9) / RED_FROM)) / 360
    return tuple(int(c * 255) for c in colorsys.hsv_to_rgb(hue, 1, 1))


def frame_for(p, color_fn=grad):
    """LED records for fill fraction p (0..1); reversed LED order, leading LED fades in."""
    recs = []
    for first in BARS:
        for k in range(10):
            level = max(0.0, min(1.0, p * 10 - k))
            recs.append((first + 9 - k, *[int(c * level) for c in color_fn(k)]))
    return recs


def parse_duration(text):
    mult = {"s": 1, "m": 60, "h": 3600}
    return float(text[:-1]) * mult[text[-1]] if text[-1] in mult else float(text)


def saved_side():
    return bytes.fromhex(SIDE_FILE.read_text()) if SIDE_FILE.exists() else DEFAULT_SIDE


def restore(kb):
    s = bytearray(kb.state())
    s[9:17] = saved_side()
    kb.write_state(s)


def running_pid():
    try:
        pid = int(PID_FILE.read_text())
        os.kill(pid, 0)
        return pid
    except (FileNotFoundError, ValueError, ProcessLookupError, PermissionError):
        return None


def run_timer(seconds):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    kb = Keyboard()
    cur = bytearray(kb.state())
    if cur[9] != 5:                               # remember the user's real side-light setting
        SIDE_FILE.write_text(bytes(cur[9:17]).hex())
    PID_FILE.write_text(str(os.getpid()))

    def stop(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        cur[9], cur[10] = 5, 100                  # custom side mode, full brightness
        kb.write_state(cur)
        t0 = time.monotonic()
        while True:
            p = min(1.0, (time.monotonic() - t0) / seconds)
            kb.set_leds(frame_for(p))
            if p >= 1.0:
                break
            time.sleep(min(0.25, max(0.05, seconds / 200)))
        for _ in range(3):                        # done: blink all red three times
            time.sleep(BLINK_GAP)
            kb.set_leds(frame_for(1.0, lambda k: (255, 0, 0)))
            time.sleep(BLINK_GAP)
            kb.set_leds(frame_for(0.0))
        time.sleep(BLINK_GAP)                     # same pause before the static color resumes
        print("timer done")
    except KeyboardInterrupt:
        print("timer cancelled")
    finally:
        try:
            restore(kb)
        finally:
            PID_FILE.unlink(missing_ok=True)
            kb.close()


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "10"
    if arg == "restore":
        kb = Keyboard()
        restore(kb)
        kb.close()
        print("restored side lights")
        return
    pid = running_pid()
    if pid:                                       # second press cancels the running timer
        os.kill(pid, signal.SIGTERM)
        return
    run_timer(parse_duration(arg))


if __name__ == "__main__":
    main()
