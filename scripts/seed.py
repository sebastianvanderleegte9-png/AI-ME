"""Seed company #1: Simplicity, design partner. Public facts only; everything else is
filled in by intake (Component 1)."""
import os

import httpx

API = os.environ.get("API_URL", "http://localhost:8000")
H = {"x-api-key": os.environ.get("API_KEY", "dev-key")}

with httpx.Client(base_url=API, headers=H, timeout=10) as c:
    co = c.post("/companies", json={
        "name": "Simplicity AI",
        "domain": "onesimplicity.com",
        "stage": "seed",
        "founders": [
            {"name": "Juraj Gago", "role": "Co-founder & Co-CEO", "linkedin_handle": "juraj-gago"},
            {"name": "Andrej Krupa", "role": "Co-founder & Co-CEO"},
        ],
    }).json()
    print("seeded:", co["id"], co["name"])
