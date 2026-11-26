from lib import *
orig = bytes.fromhex(open("orig_state.hex").read())
kb = KB(); cur = bytearray(kb.state()); cur[9:17] = orig[9:17]; kb.write_state(cur); time.sleep(0.3)
print("restored side:", list(kb.state()[9:])); kb.close()
