from lib import *
exec(open("exp2.py").read().split("kb = KB()")[0].split("from lib import *")[1])  # reuse d8()
kb = KB(); base = kb.state(); print("baseline:", base.hex())
try:
    # A: main effect stays Static(3); side effect=5; does custom table render on sides?
    s = bytearray(base); s[9] = 5; s[10] = 100; kb.write_state(s); time.sleep(0.3)
    d8(kb, [(i, 255, 0, 0) for i in range(84, 94)] + [(i, 0, 255, 0) for i in range(94, 104)]); time.sleep(0.4)
    show(kb, "A) main=static(3), side=5, D8 red/green")
    # B: partial fill: left bar 4 of 10 LEDs lit, right bar 7 of 10 lit, rest off
    s = bytearray(kb.state()); s[0] = 21; s[4] = 0; kb.write_state(s); time.sleep(0.3)
    recs = [(84+i, 255, 0, 0) if i < 4 else (84+i, 0, 0, 0) for i in range(10)] + \
           [(94+i, 0, 255, 0) if i < 7 else (94+i, 0, 0, 0) for i in range(10)]
    d8(kb, recs); time.sleep(0.4)
    show(kb, "B) main=21, left 4/10 red, right 7/10 green")
finally:
    kb.write_state(base); time.sleep(0.3); print("\nrestored:", kb.state().hex()); kb.close()
