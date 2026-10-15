"""
A controlled load test: many people using LexDesk at once.

    python load_check.py http://localhost:3000 --email lawyer@firm --password ... --users 25 --seconds 30

Run it only against a LexDesk you own, ideally a test copy, never against a
live server during working hours. It measures response times and errors
under concurrent use; it does not prove the system can survive a real
distributed denial-of-service attack (that is the job of the network edge:
Caddy's limits, the host's firewall, and a provider such as Cloudflare).
"""

import json
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:3000").rstrip("/")
arg = lambda name, default: sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default  # noqa: E731
USERS = int(arg("--users", "20"))
SECONDS = int(arg("--seconds", "20"))
EMAIL, PASSWORD = arg("--email", ""), arg("--password", "")


# No system proxy lookups: on Windows they add seconds to every request.
urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))


def call(path, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(urllib.request.Request(BASE + path, headers=headers), timeout=30) as r:
            r.read()
            status = r.status
    except urllib.error.HTTPError as e:
        status = e.code
    except Exception:  # noqa: BLE001
        status = 0
    return status, (time.perf_counter() - start) * 1000


token = None
if EMAIL:
    req = urllib.request.Request(BASE + "/api/v1/auth/login/", data=json.dumps({"email": EMAIL, "password": PASSWORD}).encode(),
                                 headers={"Content-Type": "application/json", "X-LexDesk-Client": "mobile"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        token = json.loads(r.read())["access"]

MIX = [("/", None), ("/login", None), ("/api/v1/firm/public/", None), ("/api/v1/appointments/public/lawyers/", None)]
if token:
    MIX += [("/api/v1/dashboard/", token), ("/api/v1/diary/", token), ("/api/v1/matters/", token), ("/api/v1/notifications/unread-count/", token)]

results = []
lock = threading.Lock()
stop = time.time() + SECONDS


def worker(n):
    i = n
    while time.time() < stop:
        path, tok = MIX[i % len(MIX)]
        i += 1
        status, ms = call(path, tok)
        with lock:
            results.append((path, status, ms))


threads = [threading.Thread(target=worker, args=(n,)) for n in range(USERS)]
for t in threads:
    t.start()
for t in threads:
    t.join()

times = sorted(ms for _, _, ms in results)
errors = [r for r in results if r[1] == 0 or r[1] >= 500]
throttled = [r for r in results if r[1] == 429]
pct = lambda p: times[min(len(times) - 1, int(len(times) * p))] if times else 0  # noqa: E731
print(f"{USERS} simultaneous users for {SECONDS}s against {BASE}")
print(f"requests: {len(results)}  ({len(results) / SECONDS:.0f}/s)")
print(f"response time ms: median {statistics.median(times):.0f}, 95th {pct(0.95):.0f}, 99th {pct(0.99):.0f}, max {times[-1]:.0f}")
print(f"server errors or timeouts: {len(errors)}  |  rate-limited (429): {len(throttled)}")
by_path = {}
for path, status, ms in results:
    by_path.setdefault(path, []).append(ms)
for path, ms in by_path.items():
    print(f"  {path:45s} median {statistics.median(ms):6.0f} ms  ({len(ms)} requests)")
sys.exit(1 if errors else 0)
