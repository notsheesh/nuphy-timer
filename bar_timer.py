#!/usr/bin/env python3
"""Countdown timer on the NuPhy Air75 V3 side light bars (USB, wired mode).

Flow (driven by skhd, see ~/.skhdrc):
  green key (F13) -> skhd enters mode "timer" -> `enter` starts the listener
  listener: both bars blink BLUE while it waits for you to type e.g. 30s / 30m / 1h + Enter
    valid   -> one GREEN blink, then both bars fill green->yellow->orange->red
    invalid -> one RED blink, then your static color returns
    Esc / 20 s idle -> cancel
  Press the green key again while a timer runs (or while typing) to cancel.
  When a timer ends the bars blink red three times, then your static color returns.

Commands:
    bar_timer.py enter       # what skhd runs on F13 (start, or cancel if already running)
    bar_timer.py key <name>  # skhd forwards typed keys to the listener
    bar_timer.py cancel
    bar_timer.py run 10      # run a timer directly, no typing (for testing)
    bar_timer.py restore     # put the saved side-light settings back

Protocol notes (stock firmware 2.0.0.7, verified by readback):
  0xD5/0xD6  read/write the 17-byte lighting state; byte 9 = side effect,
             side effect 5 = "custom", which renders the per-LED table.
  0xD8       per-LED table, records (index, R, G, B); side LEDs: 84-93 and 94-103.
  Writes use a per-transaction session key (0x55 0xEE handshake).
"""
import colorsys
import os
import re
import secrets
import selectors
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import hid

VID, PID = 0x19F5, 0x1028
STATE_DIR = Path.home() / ".local/state/bar-timer"
PID_FILE = STATE_DIR / "pid"
SIDE_FILE = STATE_DIR / "side.hex"          # saved side-light settings (8 bytes)
SOCK_FILE = STATE_DIR / "sock"
DEFAULT_SIDE = bytes([2, 100, 4, 0, 0, 252, 22, 22])   # static red, used if nothing saved
SKHD = "/opt/homebrew/bin/skhd"
LEAVE_MODE_KEY = "f19"                      # skhd: `timer < f19 ; default`
RED_FROM = 0.6                              # last 40% of each bar is solid red
BLINK_GAP = 0.4                             # seconds: on, off, and pause before restore
IDLE_TIMEOUT = 20.0                         # seconds of no typing before input is cancelled
MAX_SECONDS = 24 * 3600
BARS = (84, 94)                             # first LED index of each bar (10 LEDs each)
OFF = (0, 0, 0)
BLUE, GREEN, RED = (0, 0, 110), (0, 255, 0), (255, 0, 0)   # BLUE is deliberately deeper/dimmer


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


# ---------- LED patterns ----------

def grad(k):
    """Color of LED k (0 = start/green ... 9 = end/red)."""
    hue = 120 * (1 - min(1.0, (k / 9) / RED_FROM)) / 360
    return tuple(int(c * 255) for c in colorsys.hsv_to_rgb(hue, 1, 1))


def fill_frame(p, color_fn=grad):
    """LED records for fill fraction p (0..1); reversed LED order, leading LED fades in."""
    recs = []
    for k in range(10):                       # bars interleaved so both update together
        level = max(0.0, min(1.0, p * 10 - k))
        for first in BARS:
            recs.append((first + 9 - k, *[int(c * level) for c in color_fn(k)]))
    return recs


def solid(color):
    return [(first + k, *color) for k in range(10) for first in BARS]


def sleep_until(t):
    time.sleep(max(0.0, t - time.monotonic()))


def blinks(kb, color, n=1):
    """n blinks with equal spacing: dark gap, then (lit, dark gap) n times; each BLINK_GAP long.

    Steps are scheduled start-to-start, so slow HID writes do not stretch any step."""
    t = time.monotonic()
    kb.set_leds(solid(OFF))
    t += BLINK_GAP
    sleep_until(t)
    for _ in range(n):
        kb.set_leds(solid(color))
        t += BLINK_GAP
        sleep_until(t)
        kb.set_leds(solid(OFF))
        t += BLINK_GAP
        sleep_until(t)


# ---------- helpers ----------

def parse_duration(text):
    """'30s' / '30m' / '1h' -> seconds, or None if invalid. A unit is required."""
    m = re.fullmatch(r"(\d{1,5})([smh])", text.strip().lower())
    if not m:
        return None
    seconds = int(m.group(1)) * {"s": 1, "m": 60, "h": 3600}[m.group(2)]
    return seconds if 0 < seconds <= MAX_SECONDS else None


def saved_side():
    return bytes.fromhex(SIDE_FILE.read_text()) if SIDE_FILE.exists() else DEFAULT_SIDE


def restore(kb):
    s = bytearray(kb.state())
    s[9:17] = saved_side()
    kb.write_state(s)


def safe_restore(kb):
    """Restore the saved side-light settings; on failure retry on a fresh connection."""
    try:
        restore(kb)
        return
    except (Exception, SystemExit) as e:
        print(f"restore failed ({e!r}), retrying", flush=True)
    for _ in range(4):
        time.sleep(0.5)
        try:
            k2 = Keyboard()
            try:
                restore(k2)
            finally:
                k2.close()
            return
        except (Exception, SystemExit):
            continue
    print("RESTORE FAILED: run `bar_timer.py restore`", flush=True)


def pid_is_ours(pid):
    """True only if pid is a live bar_timer.py process (guards against pid reuse)."""
    try:
        out = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True,
                             text=True, timeout=2).stdout
    except Exception:
        return False
    return "bar_timer.py" in out


def running_pid():
    try:
        pid = int(PID_FILE.read_text())
    except (FileNotFoundError, ValueError):
        return None
    if pid_is_ours(pid):
        return pid
    PID_FILE.unlink(missing_ok=True)              # stale file from a crash or reboot
    return None


def leave_mode():
    """Ask skhd to leave typing mode (it handles a synthesized F19 via `timer < f19 ; default`)."""
    try:
        subprocess.run([SKHD, "-k", LEAVE_MODE_KEY], check=False, timeout=5,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


class Cancelled(Exception):
    pass


def _raise_cancel(*_):
    raise Cancelled


# ---------- phases ----------

def fill_timer(kb, seconds):
    cur = bytearray(kb.state())
    cur[9], cur[10] = 5, 100                  # custom side mode, full brightness
    kb.write_state(cur)
    t0 = time.monotonic()
    while True:
        p = min(1.0, (time.monotonic() - t0) / seconds)
        kb.set_leds(fill_frame(p))
        if p >= 1.0:
            break
        time.sleep(min(0.25, max(0.05, seconds / 200)))
    blinks(kb, RED, 3)                        # done: three red blinks, equal gaps all around
    print("timer done", flush=True)


def open_socket():
    """Bound before the slow keyboard setup, so keys typed right away queue instead of getting lost."""
    SOCK_FILE.unlink(missing_ok=True)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(str(SOCK_FILE))
    srv.listen(16)
    srv.setblocking(False)
    return srv


def listen_for_input(kb, srv):
    """Blink blue while collecting typed keys. Returns the typed text, or None if cancelled."""
    cur = bytearray(kb.state())
    cur[9], cur[10] = 5, 100
    kb.write_state(cur)
    sel = selectors.DefaultSelector()
    sel.register(srv, selectors.EVENT_READ)
    buf, lit = "", False
    next_toggle = time.monotonic()
    deadline = time.monotonic() + IDLE_TIMEOUT
    try:
        while time.monotonic() < deadline:
            now = time.monotonic()
            if now >= next_toggle:            # blue blink while waiting, equal on/off
                lit = not lit
                kb.set_leds(solid(BLUE if lit else OFF))
                next_toggle += BLINK_GAP
            for key, _ in sel.select(timeout=0.05):
                conn, _ = key.fileobj.accept()
                conn.settimeout(0.5)
                try:
                    name = conn.recv(64).decode().strip()
                finally:
                    conn.close()
                deadline = time.monotonic() + IDLE_TIMEOUT
                if name == "return":
                    return buf
                if name == "escape":
                    return None
                if name == "backspace":
                    buf = buf[:-1]
                elif len(name) == 1 and name in "0123456789smh" and len(buf) < 8:
                    buf += name
        return None                           # idle timeout
    finally:
        sel.close()


def session(direct_seconds=None):
    """One full session: [listen ->] timer. Owns the keyboard until done.

    Whatever goes wrong, the finally block restores the lights and, if the typing
    mode is still active, leaves it (a stuck capture mode would swallow all typing)."""
    in_input_phase = direct_seconds is None
    kb = srv = None
    signal.signal(signal.SIGTERM, _raise_cancel)      # handlers first: no unprotected window
    signal.signal(signal.SIGINT, _raise_cancel)
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text(str(os.getpid()))
        if in_input_phase:
            srv = open_socket()
        kb = Keyboard()
        cur = kb.state()
        if cur[9] != 5:                       # remember the user's real side-light setting
            SIDE_FILE.write_text(bytes(cur[9:17]).hex())
        seconds = direct_seconds
        if in_input_phase:
            typed = listen_for_input(kb, srv)
            if typed is None:
                print("input cancelled", flush=True)
                return
            seconds = parse_duration(typed)
            if seconds is None:
                print(f"invalid input {typed!r}", flush=True)
                blinks(kb, RED)               # invalid: one red blink, then static color
                return
            print(f"accepted {typed!r} = {seconds}s", flush=True)
            blinks(kb, GREEN)                 # valid: one green blink, then the timer starts
            leave_mode()
            in_input_phase = False            # only after the mode is really left
        fill_timer(kb, seconds)
    except Cancelled:
        print("cancelled", flush=True)
    except (Exception, SystemExit) as e:
        print(f"error: {e!r}", flush=True)
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)  # cleanup must not be interrupted
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        try:
            if kb is not None:
                safe_restore(kb)
        finally:
            if srv is not None:
                srv.close()
            SOCK_FILE.unlink(missing_ok=True)
            PID_FILE.unlink(missing_ok=True)
            if kb is not None:
                kb.close()
            if in_input_phase:
                leave_mode()


def cmd_enter():
    """Runs on F13 (skhd enters mode `timer` first)."""
    pid = running_pid()
    if pid:                                   # a timer is running: this press cancels it
        os.kill(pid, signal.SIGTERM)
        leave_mode()
        return
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        log = open(STATE_DIR / "listener.log", "a")
        subprocess.Popen([sys.executable, os.path.abspath(__file__), "listen"],
                         stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)
    except Exception:
        leave_mode()                          # could not start: do not stay in typing mode
        raise


def cmd_key(name):
    """Forward a typed key to the listener. If no listener answers, leave typing mode."""
    for _ in range(20):                       # the listener may still be starting: retry ~2 s
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(0.5)
            s.connect(str(SOCK_FILE))
            s.sendall(name.encode())
            s.close()
            return
        except OSError:
            time.sleep(0.1)
    leave_mode()                              # nobody is listening: do not trap the keyboard


def cmd_cancel():
    pid = running_pid()
    if pid:
        os.kill(pid, signal.SIGTERM)          # the session leaves the mode itself
    else:
        leave_mode()                          # nothing to cancel: just get out of typing mode


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    if cmd == "enter":
        cmd_enter()
    elif cmd == "listen":
        session()
    elif cmd == "key":
        cmd_key(sys.argv[2])
    elif cmd == "cancel":
        cmd_cancel()
    elif cmd == "restore":
        kb = Keyboard()
        restore(kb)
        kb.close()
        print("restored side lights")
    elif cmd == "run":
        seconds = parse_duration(sys.argv[2]) if len(sys.argv) > 2 else 10
        if seconds is None:
            raise SystemExit("usage: bar_timer.py run 30s|30m|1h")
        session(seconds)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
