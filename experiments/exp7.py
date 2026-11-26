import sys, colorsys
from lib import *
exec(open("exp2.py").read().split("kb = KB()")[0].split("from lib import *")[1])
DUR = float(sys.argv[1]) if len(sys.argv) > 1 else 10.0
orig = bytes.fromhex(open("orig_state.hex").read())
kb = KB(); cur = kb.state()
restore = bytearray(cur); restore[9:17] = orig[9:17]
def grad(k):                      # k=0 start (green) .. k=9 end (red), via yellow/orange
    h = (120 * (1 - min(1.0, (k / 9) / 0.6))) / 360   # red from 60% on
    return tuple(int(c * 255) for c in colorsys.hsv_to_rgb(h, 1, 1))
try:
    s = bytearray(cur); s[9] = 5; s[10] = 100; kb.write_state(s); time.sleep(0.3)
    t0 = time.monotonic()
    while True:
        p = min(1.0, (time.monotonic() - t0) / DUR)
        recs = []
        for base_led in (84, 94):                       # both bars, synced
            for k in range(10):
                level = max(0.0, min(1.0, p * 10 - k))  # leading LED fades in
                led = base_led + (9 - k)                # reversed order
                recs.append((led, *[int(c * level) for c in grad(k)]))
        d8(kb, recs)
        if p >= 1.0: break
        time.sleep(0.15)
    a, b = kb.side_leds(); print("final L", a); print("final R", b == a, b[:2])
    print("left on as is")
except BaseException:
    kb.write_state(restore); print('error -> restored'); raise
finally:
    kb.close()
