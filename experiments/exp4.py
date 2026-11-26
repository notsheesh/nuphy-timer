from lib import *
exec(open("exp2.py").read().split("kb = KB()")[0].split("from lib import *")[1])
kb = KB(); base = kb.state(); print("baseline:", base.hex(), flush=True)
try:
    s = bytearray(base); s[9] = 5; s[10] = 100; kb.write_state(s); time.sleep(0.3)
    # demo: left bar (84-93) fills red one LED/sec; right bar (94-103) fills green at same time
    for n in range(0, 11):
        recs = [(84+i, 255, 0, 0) if i < n else (84+i, 0, 0, 0) for i in range(10)] + \
               [(94+i, 0, 255, 0) if i < n else (94+i, 0, 0, 0) for i in range(10)]
        d8(kb, recs); time.sleep(1.0)
    # hold: left 3/10 red, right 6/10 green; sample for 8 minutes
    recs = [(84+i, 255, 0, 0) if i < 3 else (84+i, 0, 0, 0) for i in range(10)] + \
           [(94+i, 0, 255, 0) if i < 6 else (94+i, 0, 0, 0) for i in range(10)]
    d8(kb, recs); print("HOLD start", time.strftime("%H:%M:%S"), flush=True)
    for t in range(17):
        time.sleep(30)
        a, b = kb.side_leds()
        print(f"t+{(t+1)*30:>3}s L lit={sum(1 for p in a if p!=(0,0,0))} R lit={sum(1 for p in b if p!=(0,0,0))} L0={a[0]} R0={b[0]}", flush=True)
finally:
    kb.write_state(base); time.sleep(0.3); print("restored:", kb.state().hex(), flush=True); kb.close()
