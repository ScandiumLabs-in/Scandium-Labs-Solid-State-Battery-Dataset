#!/usr/bin/env python3
"""Launch the SSB review dashboard.

Usage:
    python scripts/dashboard.py                 # run on 127.0.0.1:8000
    python scripts/dashboard.py --port 9000     # custom port
    python scripts/dashboard.py --host 0.0.0.0  # expose on LAN
"""

from __future__ import annotations

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="SSB review dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    print(f"SSB Review Dashboard -> http://{args.host}:{args.port}")
    uvicorn.run("ssb_dataset.review.dashboard:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
