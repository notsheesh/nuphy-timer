import sys
from lib import *
exec(open("exp2.py").read().split("kb = KB()")[0].split("from lib import *")[1])
DUR = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
LEFT_END, RIGHT_END = 1.0, 0.6          # final fill fraction of each bar
orig = bytes.fromhex(open("orig_state.hex").read())   # your original lighting
kb = KB(); cur = kb.state()
restore = bytearray(cur); restore[9:17] = orig[9:17]   # keep live main color, restore side settings
try:
    s = bytearray(cur); s[9] = 5; s[10] = 100; kb.write_state(s); time.sleep(0.3)
    t0 = time.monotonic()
    while True:
        p = min(1.0, (time.monotonic() - t0) / DUR)
        recs = []
        for base_led, color, end in ((84, (255, 0, 0), LEFT_END), (94, (0, 255, 0), RIGHT_END)):
            f = p * end * 10                         # LEDs worth of fill
            for k in range(10):
                level = max(0.0, min(1.0, f - k))    # leading LED partially lit
                led = base_led + (9 - k)             # REVERSED order
                recs.append((led, *[int(c * level) for c in color]))
        d8(kb, recs)
        if p >= 1.0: break
        time.sleep(0.25)
    a, b = kb.side_leds(); print("final L", a); print("final R", b)
    time.sleep(8)   # hold so you can look
finally:
    kb.write_state(restore); time.sleep(0.3); print("restored:", kb.state().hex()); kb.close()
