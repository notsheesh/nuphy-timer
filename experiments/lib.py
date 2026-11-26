import time, secrets
import hid
VID, PID = 0x19F5, 0x1028
def frame(cmd, length, addr=0, key=0, payload=b""):
    out = bytearray(64); out[:2] = bytes([0x55, cmd])
    out[4:8] = bytes(x ^ key for x in (length, addr & 255, addr >> 8, 0))
    out[8:8 + len(payload)] = bytes(x ^ key for x in payload)
    out[3] = sum(out[4:]) & 255
    return out
class KB:
    def __init__(self):
        d = [x for x in hid.enumerate(VID, PID) if x["usage_page"] == 1 and x["usage"] == 0]
        assert len(d) == 1, f"{len(d)} candidates"
        self.dev = hid.device(); self.dev.open_path(d[0]["path"])
    def ex(self, pkt):
        self.dev.write(b"\x00" + bytes(pkt)); end = time.monotonic() + 1.5
        while time.monotonic() < end:
            r = bytes(self.dev.read(64, 100))
            if r[:2] == bytes([0xAA, pkt[1]]): return r
        raise RuntimeError("timeout")
    def txn(self, cmd, length, addr=0, payload=b""):
        h = bytearray(64); h[:2] = b"\x55\xee"; h[8:] = secrets.token_bytes(56)
        key = h[28] or 0xAA; h[28] = key; h[3] = sum(h[4:]) & 255
        self.ex(h)
        r = self.ex(frame(cmd, length, addr, key, payload))
        return bytes(x ^ key for x in r[8:8 + length])
    def state(self): return self.txn(0xD5, 17)
    def write_state(self, s): return self.txn(0xD6, 17, 0, bytes(s))
    def side_leds(self):
        a = self.txn(0xD2, 30, 84 * 3); b = self.txn(0xD2, 30, 94 * 3)
        f = lambda x: [tuple(x[i:i+3]) for i in range(0, 30, 3)]
        return f(a), f(b)
    def close(self): self.dev.close()
def show(kb, label):
    a, b = kb.side_leds()
    print(f"{label}\n  84-93 : {a}\n  94-103: {b}")
