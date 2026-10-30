"""#10090 interop control: runs the producer half's clock_bridge (path given) as ONE producer incarnation
against a local disposable Postgres. Args: DB_URL CASE WINDOW_S PRODUCER_SOURCE. Prints P lines."""
import importlib.util, sys, time
url, case, window = sys.argv[1], sys.argv[2], float(sys.argv[3])
spec = importlib.util.spec_from_file_location("clock_bridge", sys.argv[4])
cb = importlib.util.module_from_spec(spec); spec.loader.exec_module(cb)
env = {"DATABASE_URL": url, "DYNO": "worker-ws.interop", "CLOCK_MARKER_CASE": case,
       "CLOCK_MARKER_EXPIRES_AT": str(time.time() + window + 60)}
bridge = cb.ClockBridge(env=env, emit=lambda prefix, pid, text: print(prefix, text, flush=True))
bridge.armed("kalshi", window)
time.sleep(window + 3)
t = bridge._thread
if t is not None: t.join(10)
print("PRODUCER-EXIT", flush=True)
