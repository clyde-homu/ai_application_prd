"""Deterministic financial calculations for the AW Client Report Portal.

These functions are intentionally pure (no Flask / SQLAlchemy imports) so the
exact rules from the PRD can be unit-tested in isolation. The data-entry routes
build plain dicts/lists from the ORM models and feed them in here.

PRD calculation rules (must be exact):
  - SACS:  excess = inflow - outflow
  - SACS:  private_reserve_target = (6 * monthly_expenses) + sum(insurance deductibles)
  - TCC:   client1_retirement_total = sum of client1 retirement balances (same for client2)
  - TCC:   non_retirement_total = sum of non-retirement balances  (TRUST EXCLUDED)
  - TCC:   grand_total = client1_ret + client2_ret + non_retirement + trust
  - TCC:   liabilities_total = sum of liabilities  (shown separately, NEVER subtracted)
"""

from __future__ import annotations

from datetime import date
from typing import Iterable, Mapping, Sequence


# Account category constants (mirror models.Account.category values).
RETIREMENT = "retirement"
NON_RETIREMENT = "non_retirement"
TRUST = "trust"
LIABILITY = "liability"

# Account owner constants.
CLIENT1 = "client1"
CLIENT2 = "client2"
JOINT = "joint"


def _money(value) -> float:
    """Coerce possibly-missing/blank numeric input to a float (treat blank as 0)."""
    if value is None or value == "":
        return 0.0
    return float(value)


def calculate_age(dob: date | None, on_date: date | None = None) -> int | None:
    """Whole-year age from a date of birth. Returns None if dob is missing."""
    if dob is None:
        return None
    ref = on_date or date.today()
    return ref.year - dob.year - ((ref.month, ref.day) < (dob.month, dob.day))


# --------------------------------------------------------------------------- #
# SACS (cash flow)
# --------------------------------------------------------------------------- #

def sacs_excess(inflow, outflow) -> float:
    """Monthly excess swept to the Private Reserve: inflow - outflow."""
    return _money(inflow) - _money(outflow)


def private_reserve_target(monthly_expenses, insurance_deductibles: Iterable | float = 0) -> float:
    """Target = (6 months of expenses) + sum of all insurance deductibles.

    ``insurance_deductibles`` may be a single number or an iterable of numbers.
    """
    if isinstance(insurance_deductibles, (int, float, str)):
        deductibles_sum = _money(insurance_deductibles)
    else:
        deductibles_sum = sum(_money(d) for d in insurance_deductibles)
    return (6 * _money(monthly_expenses)) + deductibles_sum


# --------------------------------------------------------------------------- #
# TCC (net worth)
# --------------------------------------------------------------------------- #

def _sum_balances(accounts: Sequence[Mapping], *, category: str, owner: str | None = None) -> float:
    total = 0.0
    for acct in accounts:
        if acct.get("category") != category:
            continue
        if owner is not None and acct.get("owner") != owner:
            continue
        total += _money(acct.get("balance"))
    return total


def retirement_total(accounts: Sequence[Mapping], owner: str) -> float:
    """Sum of one spouse's retirement account balances."""
    return _sum_balances(accounts, category=RETIREMENT, owner=owner)


def non_retirement_total(accounts: Sequence[Mapping]) -> float:
    """Sum of all non-retirement account balances. Trust is NOT included."""
    return _sum_balances(accounts, category=NON_RETIREMENT)


def trust_total(accounts: Sequence[Mapping], home_value=0) -> float:
    """Trust value: the home (Zillow value) plus any explicit trust accounts."""
    return _money(home_value) + _sum_balances(accounts, category=TRUST)


def liabilities_total(accounts: Sequence[Mapping]) -> float:
    """Sum of all liability balances. Displayed separately, never subtracted."""
    return _sum_balances(accounts, category=LIABILITY)


def grand_total_net_worth(
    client1_retirement: float,
    client2_retirement: float,
    non_retirement: float,
    trust: float,
) -> float:
    """Net worth = c1 retirement + c2 retirement + non-retirement + trust.

    Liabilities are deliberately excluded (PRD: "we do not subtract liabilities
    from their net worth, they're just a separate box").
    """
    return client1_retirement + client2_retirement + non_retirement + trust


# --------------------------------------------------------------------------- #
# Aggregate computation used by the report preview + PDF templates
# --------------------------------------------------------------------------- #

def compute_report(accounts: Sequence[Mapping], fields: Mapping) -> dict:
    """Compute every value a SACS/TCC report needs from plain data.

    ``accounts`` is a list of dicts with keys: owner, category, balance
    (plus optional type/acct_last4/interest_rate/cash_balance for display).
    ``fields`` is a dict with keys: inflow, outflow, monthly_expenses,
    insurance_deductibles, home_value (and any display-only extras).
    """
    c1_ret = retirement_total(accounts, CLIENT1)
    c2_ret = retirement_total(accounts, CLIENT2)
    non_ret = non_retirement_total(accounts)
    trust = trust_total(accounts, fields.get("home_value", 0))

    return {
        # SACS
        "inflow": _money(fields.get("inflow")),
        "outflow": _money(fields.get("outflow")),
        "excess": sacs_excess(fields.get("inflow"), fields.get("outflow")),
        "private_reserve_target": private_reserve_target(
            fields.get("monthly_expenses"),
            fields.get("insurance_deductibles", 0),
        ),
        # TCC
        "client1_retirement_total": c1_ret,
        "client2_retirement_total": c2_ret,
        "non_retirement_total": non_ret,
        "trust_total": trust,
        "grand_total": grand_total_net_worth(c1_ret, c2_ret, non_ret, trust),
        "liabilities_total": liabilities_total(accounts),
    }
