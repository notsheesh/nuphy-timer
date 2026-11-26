"""Write full 17-byte lighting state (0xD6) with side color changed; verify by readback."""
import sys, time
sys.argv = sys.argv[:1] + sys.argv[1:]
exec(open("probe_read.py").read().split("devs = [")[0])  # reuse helpers only
import hid, json
devs = [d for d in hid.enumerate(VID, PID) if d["usage_page"] == 1 and d["usage"] == 0]
dev = hid.device(); dev.open_path(devs[0]["path"])
orig = read(dev, 0xD5, 17)
open("orig_state.hex", "w").write(orig.hex())
print("saved original:", orig.hex())
new = bytearray(orig)
new[14:17] = bytes([0, 0, 255])          # side r,g,b -> blue
# one write transaction (fresh session key)
def write(dev, cmd, length, addr, payload):
    import secrets
    hello = bytearray(64); hello[:2] = b"\x55\xee"; hello[8:] = secrets.token_bytes(56)
    key = hello[28] or 0xAA; hello[28] = key; hello[3] = sum(hello[4:]) & 255
    exchange(dev, hello)
    r = exchange(dev, frame(cmd, length, addr, key, payload))
    return bytes(x ^ key for x in r[8:8 + length])
ack = write(dev, 0xD6, 17, 0, bytes(new))
print("ack matches:", ack == bytes(new))
for _ in range(5):
    time.sleep(0.15)
    cur = read(dev, 0xD5, 17)
    if cur == bytes(new): print("readback OK:", cur.hex()); break
else:
    print("readback MISMATCH:", cur.hex())
dev.close()
