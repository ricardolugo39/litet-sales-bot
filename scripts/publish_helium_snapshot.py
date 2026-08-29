"""Validate and publish a complete Helium 10 MCP snapshot to Railway."""

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from decision_dashboard_v2.helium_store import validate_snapshot


load_dotenv()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--url", default=os.getenv("DASHBOARD_URL"))
    args = parser.parse_args()
    token = os.getenv("ADMIN_UPLOAD_TOKEN")
    if not args.url or not token:
        raise SystemExit("DASHBOARD_URL and ADMIN_UPLOAD_TOKEN are required")
    payload = json.loads(args.snapshot.read_text())
    validate_snapshot(payload)
    request = urllib.request.Request(
        args.url.rstrip("/") + "/admin/helium-snapshot",
        data=json.dumps(payload).encode(),
        method="PUT",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        print("Published:", json.load(response))


if __name__ == "__main__":
    main()
