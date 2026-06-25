"""CLI to seed the database with team accounts and an optional demo client.

Usage:
    python seed.py            # seed users + demo client
    python seed.py --no-demo  # seed users only

The seed data itself lives in ``seeding.py`` so it can also run on boot via the
``SEED_DEMO=1`` env var. The default team password comes from SEED_TEAM_PASSWORD
(falls back to "changeme123"). Everyone should change it after first login.
"""

from __future__ import annotations

import sys

from app import app
from seeding import seed_demo_client, seed_users


def main() -> None:
    with app.app_context():
        print("Seeding users...")
        seed_users()
        if "--no-demo" not in sys.argv:
            print("Seeding demo client...")
            seed_demo_client()
    print("Done.")


if __name__ == "__main__":
    main()
