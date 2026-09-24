"""Component 0 done-when: create a heartbeat job through the API and watch it reach
'executed' via the worker. Exit 0 on success, 1 on timeout."""
import os
import sys
import time

import httpx

API = os.environ.get("API_URL", "http://localhost:8000")
H = {"x-api-key": os.environ.get("API_KEY", "dev-key")}

with httpx.Client(base_url=API, headers=H, timeout=10) as c:
    print("health:", c.get("/health").json())
    co = c.post("/companies", json={"name": "Heartbeat Co", "stage": "seed"}).json()
    job = c.post("/jobs", json={"company_id": co["id"], "type": "heartbeat", "channel": "internal"}).json()
    print("job created:", job["id"], job["state"])
    for _ in range(30):
        j = c.get(f"/jobs/{job['id']}").json()
        if j["state"] == "executed":
            print("job executed, platform_ref =", j["platform_ref"])
            sys.exit(0)
        time.sleep(1)
    print("timeout: job still", j["state"])
    sys.exit(1)
