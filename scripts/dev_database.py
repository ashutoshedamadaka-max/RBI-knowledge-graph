"""Start the local PostgreSQL used for development and evaluation (no Docker; ADR-019).

The server keeps running after this script exits; data lives in data/runtime/postgres.
Use the printed settings, for example:  set VECTOR_BACKEND=postgres  and  set DATABASE_URL=...
Stop it with:  python scripts/dev_database.py --stop
"""
import argparse
from pathlib import Path

import pgserver

DATA = Path(__file__).resolve().parents[1] / "data" / "runtime" / "postgres"

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--stop", action="store_true")
args = parser.parse_args()
server = pgserver.get_server(str(DATA), cleanup_mode="stop" if args.stop else None)
if args.stop:
    server.cleanup()
    print("Stopped.")
else:
    print(f"VECTOR_BACKEND=postgres\nDATABASE_URL={server.get_uri()}")
