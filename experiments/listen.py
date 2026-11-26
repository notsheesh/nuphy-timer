import hid, time
devs = [d for d in hid.enumerate(0x19F5, 0x1028) if d["usage_page"] in (1, 12)]
opened = []
for d in devs:
    h = hid.device()
    try:
        h.open_path(d["path"]); h.set_nonblocking(True)
        opened.append((d["interface_number"], d["usage_page"], d["usage"], h))
    except Exception as e:
        print("open failed", d["interface_number"], d["usage_page"], d["usage"], e)
print("listening on", [(i, hex(p), hex(u)) for i, p, u, _ in opened], flush=True)
end = time.monotonic() + 15
seen = 0
while time.monotonic() < end:
    for i, p, u, h in opened:
        r = h.read(64)
        if r and any(r):
            print(f"{time.strftime('%H:%M:%S')} iface{i} page{hex(p)} usage{hex(u)} report={bytes(r[:12]).hex()}", flush=True); seen += 1
    time.sleep(0.005)
print("done, reports:", seen)
