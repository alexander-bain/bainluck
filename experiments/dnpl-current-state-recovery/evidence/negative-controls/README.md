# Known-bad negative control, not implementation

`authority-unsafe-serialization.txt` is the earlier Lua authority model before the numeric correction. It deliberately demonstrates Lua5.1 owner/sequence serialization failures. Only the explicit paired regression probe loads it; no adapter, test helper default, or application import selects it. Never use it as a storage implementation. All positive/model tests select atomic-numeric-encoding/authority.lua.
