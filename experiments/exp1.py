from lib import *
kb = KB(); base = kb.state(); print("baseline:", base.hex())
try:
    for eff in range(0, 8):
        for flag in (0, 1):
            s = bytearray(base); s[9:17] = bytes([eff, 100, 2, flag, 0, 255, 0, 0])
            kb.write_state(s); time.sleep(0.6)
            got = kb.state()
            print(f"\n== effect={eff} flag={flag} readback side={list(got[9:])}")
            for t in range(2):
                a, b = kb.side_leds()
                ua, ub = sorted(set(a)), sorted(set(b))
                print(f"   t{t}: L uniq={ua[:4]}{'…' if len(ua)>4 else ''}  R uniq={ub[:4]}{'…' if len(ub)>4 else ''}")
                time.sleep(0.5)
finally:
    kb.write_state(base); time.sleep(0.3); print("\nrestored:", kb.state().hex()); kb.close()
