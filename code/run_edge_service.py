#!/usr/bin/env python3
"""Run the local SRASTA BE+AI service using an internal RF baseline artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from srasta_csi.edge import EdgeRuntime, create_app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--replay", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    runtime = EdgeRuntime(args.model, args.db)
    if args.replay:
        print(json.dumps(runtime.replay(args.replay), indent=2))
    import uvicorn

    try:
        uvicorn.run(create_app(runtime), host=args.host, port=args.port)
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
