"""SQLAlchemy models for the AW Client Report Portal."""

from __future__ import annotations

from datetime import date, datetime

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

import calculations as calc

db = SQLAlchemy()


class User(UserMixin, db.Model):
    """A member of the firm's team (Andrew, Rebecca, Maryann)."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), default="planner")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<User {self.email}>"


class Client(db.Model):
    """A household the firm advises. Stores static info entered once."""

    __tablename__ = "clients"

    id = db.Column(db.Integer, primary_key=True)
    married = db.Column(db.Boolean, default=False)

    client1_name = db.Column(db.String(120), nullable=False)
    client1_dob = db.Column(db.Date)
    client1_ssn_last4 = db.Column(db.String(4))

    client2_name = db.Column(db.String(120))
    client2_dob = db.Column(db.Date)
    client2_ssn_last4 = db.Column(db.String(4))

    # Static financial data (defaults for each quarterly report).
    monthly_salary = db.Column(db.Float, default=0)          # SACS inflow
    monthly_expense_budget = db.Column(db.Float, default=0)  # SACS outflow
    insurance_deductibles = db.Column(db.Float, default=0)   # for reserve target
    private_reserve_target_override = db.Column(db.Float)     # optional manual target

    trust_address = db.Column(db.String(255))                # property for Zillow lookup

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    accounts = db.relationship(
        "Account", backref="client", cascade="all, delete-orphan", order_by="Account.id"
    )
    reports = db.relationship(
        "Report",
        backref="client",
        cascade="all, delete-orphan",
        order_by="Report.report_date.desc()",
    )

    @property
    def client1_age(self):
        return calc.calculate_age(self.client1_dob)

    @property
    def client2_age(self):
        return calc.calculate_age(self.client2_dob)

    @property
    def display_name(self) -> str:
        if self.married and self.client2_name:
            return f"{self.client1_name} & {self.client2_name}"
        return self.client1_name

    @property
    def last_report(self):
        return self.reports[0] if self.reports else None

    @property
    def last_report_date(self):
        rpt = self.last_report
        return rpt.report_date if rpt else None


class Account(db.Model):
    """One account (or liability) belonging to a client."""

    __tablename__ = "accounts"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=False)

    owner = db.Column(db.String(20), default=calc.JOINT)       # client1 | client2 | joint
    category = db.Column(db.String(20), nullable=False)        # retirement | non_retirement | trust | liability
    type = db.Column(db.String(60), nullable=False)            # IRA, Roth IRA, 401K, brokerage, mortgage, ...
    acct_last4 = db.Column(db.String(8))
    interest_rate = db.Column(db.Float)                        # liabilities only
    is_investment = db.Column(db.Boolean, default=False)       # track a separate cash balance (e.g. Schwab)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Report(db.Model):
    """A single quarter's report for a client, with its entered balances."""

    __tablename__ = "reports"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))

    report_date = db.Column(db.Date, default=date.today, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Dynamic, snapshot-per-quarter SACS inputs.
    inflow = db.Column(db.Float, default=0)
    outflow = db.Column(db.Float, default=0)
    insurance_deductibles = db.Column(db.Float, default=0)
    private_reserve_balance = db.Column(db.Float, default=0)
    schwab_investment_balance = db.Column(db.Float, default=0)
    home_value = db.Column(db.Float, default=0)               # Zillow value of trust property

    balances = db.relationship(
        "AccountBalance", backref="report", cascade="all, delete-orphan"
    )
    author = db.relationship("User")

    # -- helpers used by the preview + PDF templates ----------------------- #

    def balance_map(self) -> dict[int, "AccountBalance"]:
        return {b.account_id: b for b in self.balances}

    def calc_accounts(self) -> list[dict]:
        """Build the plain account list that calculations.compute_report expects."""
        bmap = self.balance_map()
        rows = []
        for acct in self.client.accounts:
            bal = bmap.get(acct.id)
            rows.append(
                {
                    "id": acct.id,
                    "owner": acct.owner,
                    "category": acct.category,
                    "type": acct.type,
                    "acct_last4": acct.acct_last4,
                    "interest_rate": acct.interest_rate,
                    "is_investment": acct.is_investment,
                    "balance": bal.balance if bal else 0,
                    "cash_balance": bal.cash_balance if bal else None,
                }
            )
        return rows

    def calc_fields(self) -> dict:
        return {
            "inflow": self.inflow,
            "outflow": self.outflow,
            "monthly_expenses": self.outflow,
            "insurance_deductibles": self.insurance_deductibles,
            "home_value": self.home_value,
        }

    def computed(self) -> dict:
        """All derived values; respects a manual reserve-target override."""
        result = calc.compute_report(self.calc_accounts(), self.calc_fields())
        override = self.client.private_reserve_target_override
        if override is not None:
            result["private_reserve_target"] = override
        return result

    def grouped(self) -> dict[str, list[dict]]:
        """Accounts (with this report's balances) bucketed for the TCC layout."""
        rows = self.calc_accounts()
        return {
            "client1_retirement": [
                r for r in rows
                if r["category"] == calc.RETIREMENT and r["owner"] == calc.CLIENT1
            ],
            "client2_retirement": [
                r for r in rows
                if r["category"] == calc.RETIREMENT and r["owner"] == calc.CLIENT2
            ],
            "non_retirement": [r for r in rows if r["category"] == calc.NON_RETIREMENT],
            "trust": [r for r in rows if r["category"] == calc.TRUST],
            "liabilities": [r for r in rows if r["category"] == calc.LIABILITY],
        }


class AccountBalance(db.Model):
    """The balance entered for one account in one report."""

    __tablename__ = "account_balances"

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey("reports.id"), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    balance = db.Column(db.Float, default=0)
    cash_balance = db.Column(db.Float)  # investment accounts only

    account = db.relationship("Account")
