"""Seed the database with the team's user accounts and an optional demo client.

Usage:
    python seed.py            # seed users + demo client
    python seed.py --no-demo  # seed users only

The default password for seeded team members is read from SEED_TEAM_PASSWORD
(falls back to "changeme123"). Everyone should change it after first login.
"""

from __future__ import annotations

import os
import sys
from datetime import date

from app import app
from models import Account, AccountBalance, Client, Report, User, db

TEAM = [
    ("Andrew", "andrew@windbrook.example", "admin"),
    ("Rebecca", "rebecca@windbrook.example", "planner"),
    ("Maryann", "maryann@windbrook.example", "assistant"),
]


def seed_users() -> None:
    password = os.environ.get("SEED_TEAM_PASSWORD", "changeme123")
    for name, email, role in TEAM:
        if db.session.query(User).filter_by(email=email).first():
            print(f"  user exists: {email}")
            continue
        user = User(name=name, email=email, role=role)
        user.set_password(password)
        db.session.add(user)
        print(f"  + user: {email}")
    db.session.commit()


def seed_demo_client() -> None:
    if db.session.query(Client).filter_by(client1_name="John Sample").first():
        print("  demo client already exists")
        return

    client = Client(
        married=True,
        client1_name="John Sample",
        client1_dob=date(1975, 4, 12),
        client1_ssn_last4="1234",
        client2_name="Jane Sample",
        client2_dob=date(1977, 9, 30),
        client2_ssn_last4="5678",
        monthly_salary=15000,
        monthly_expense_budget=11000,
        insurance_deductibles=5000,
        trust_address="123 Peachtree St, Atlanta, GA",
    )
    ira = Account(owner="client1", category="retirement", type="IRA", acct_last4="1111")
    roth = Account(owner="client1", category="retirement", type="Roth IRA", acct_last4="2222")
    brokerage = Account(owner="joint", category="non_retirement", type="Joint Brokerage",
                        acct_last4="3333", is_investment=True)
    mortgage = Account(owner="joint", category="liability", type="Mortgage",
                       acct_last4="4444", interest_rate=6.5)
    client.accounts.extend([ira, roth, brokerage, mortgage])
    db.session.add(client)
    db.session.flush()  # assign account ids

    report = Report(
        client_id=client.id,
        report_date=date.today(),
        inflow=15000,
        outflow=11000,
        insurance_deductibles=5000,
        private_reserve_balance=40000,
        schwab_investment_balance=50000,
        home_value=450000,
    )
    db.session.add(report)
    db.session.flush()
    report.balances.extend([
        AccountBalance(account_id=ira.id, balance=11000),
        AccountBalance(account_id=roth.id, balance=15000),
        AccountBalance(account_id=brokerage.id, balance=50000, cash_balance=5000),
        AccountBalance(account_id=mortgage.id, balance=200000),
    ])
    db.session.commit()
    print("  + demo client: John & Jane Sample (net worth $526,000)")


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
