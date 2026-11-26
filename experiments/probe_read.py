"""Read-only probe: lighting state (0xD5) and live LED colors (0xD2) on Air75 V3."""
import secrets
import time
import hid

VID, PID = 0x19F5, 0x1028


def frame(cmd, length, addr=0, key=0, payload=b""):
    out = bytearray(64)
    out[:2] = bytes([0x55, cmd])
    out[4:8] = bytes(x ^ key for x in (length, addr & 255, addr >> 8, 0))
    out[8:8 + len(payload)] = bytes(x ^ key for x in payload)
    out[3] = sum(out[4:]) & 255
    return out


def exchange(dev, pkt):
    dev.write(b"\x00" + bytes(pkt))
    end = time.monotonic() + 1.5
    while time.monotonic() < end:
        r = bytes(dev.read(64, 100))
        if r[:2] == bytes([0xAA, pkt[1]]):
            return r
    raise RuntimeError("timeout")


def read(dev, cmd, length, addr=0):
    hello = bytearray(64)
    hello[:2] = b"\x55\xee"
    hello[8:] = secrets.token_bytes(56)
    key = hello[28] or 0xAA
    hello[28] = key
    hello[3] = sum(hello[4:]) & 255
    exchange(dev, hello)
    r = exchange(dev, frame(cmd, length, addr, key))
    return bytes(x ^ key for x in r[8:8 + length])


devs = [d for d in hid.enumerate(VID, PID) if d["usage_page"] == 1 and d["usage"] == 0]
print("candidates:", len(devs))
dev = hid.device()
dev.open_path(devs[0]["path"])
fw = read(dev, 0xA1, 8)
print("fw bytes:", fw.hex())
print("led count byte (0xD1):", read(dev, 0xD1, 1).hex())
st = read(dev, 0xD5, 17)
print("state17:", st.hex())
print("main  [effect,bright,speed,dir,modeflag,palette,r,g,b]:", list(st[:9]))
print("side  [effect,bright,speed,mode,palette,r,g,b]:", list(st[9:17]))
a = read(dev, 0xD2, 30, 84 * 3)
b = read(dev, 0xD2, 30, 94 * 3)
print("LEDs 84-93 :", [tuple(a[i:i + 3]) for i in range(0, 30, 3)])
print("LEDs 94-103:", [tuple(b[i:i + 3]) for i in range(0, 30, 3)])
dev.close()
