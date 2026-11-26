import sys, time, secrets
exec(open("probe_read.py").read().split("devs = [")[0])
import hid
pct = int(sys.argv[1])
devs = [d for d in hid.enumerate(VID, PID) if d["usage_page"] == 1 and d["usage"] == 0]
dev = hid.device(); dev.open_path(devs[0]["path"])
def txn(cmd, length, addr=0, payload=b""):
    hello = bytearray(64); hello[:2] = b"\x55\xee"; hello[8:] = secrets.token_bytes(56)
    key = hello[28] or 0xAA; hello[28] = key; hello[3] = sum(hello[4:]) & 255
    exchange(dev, hello)
    r = exchange(dev, frame(cmd, length, addr, key, payload))
    return bytes(x ^ key for x in r[8:8 + length])
cur = txn(0xD5, 17)
new = bytearray(cur); new[10] = pct          # side brightness
txn(0xD6, 17, 0, bytes(new))
for _ in range(5):
    time.sleep(0.15)
    got = txn(0xD5, 17)
    if got[9:] == bytes(new[9:]): print("side readback OK:", list(got[9:])); break
else: print("MISMATCH", list(got[9:]))
dev.close()
