from lib import *
def d8(kb, recs):
    for i in range(0, len(recs), 14):
        data = bytes(x for r in recs[i:i+14] for x in r)
        h = bytearray(64); h[:2] = b"\x55\xee"; h[8:] = secrets.token_bytes(56)
        key = h[28] or 0xAA; h[28] = key; h[3] = sum(h[4:]) & 255
        kb.ex(h)
        kb.dev.write(b"\x00" + bytes(frame(0xD8, len(data), 0, key, data)))
        time.sleep(0.12)
        while True:   # drain any reply
            r = bytes(kb.dev.read(64, 50))
            if not r: break
kb = KB(); base = kb.state(); print("baseline:", base.hex())
try:
    s = bytearray(base); s[0] = 21; s[4] = 0; kb.write_state(s); time.sleep(0.3)
    print("state after effect=21:", kb.state().hex())
    recs = [(i, 255, 0, 0) for i in range(84, 94)] + [(i, 0, 255, 0) for i in range(94, 104)] + [(i, 0, 0, 255) for i in range(0, 5)]
    d8(kb, recs); time.sleep(0.4)
    show(kb, "custom table, side effect=blue static")
    k = kb.txn(0xD2, 15, 0); print("  keys 0-4:", [tuple(k[i:i+3]) for i in range(0,15,3)])
    s = bytearray(kb.state()); s[9] = 5; kb.write_state(s); time.sleep(0.4)
    show(kb, "same, side effect=5(off?)")
    s = bytearray(kb.state()); s[9] = 2; s[10] = 100; s[14:17] = bytes([255,255,255]); kb.write_state(s); time.sleep(0.4)
    show(kb, "side effect=static white")
finally:
    kb.write_state(base); time.sleep(0.3); print("\nrestored:", kb.state().hex()); kb.close()
