"""Unit tests for the PRD's deterministic calculation rules.

The numbers mirror the PRD's own worked example:
  Inflow $15,000 - Outflow $11,000 = $4,000 excess
  IRA $11K + Roth $15K = $26K (Client 1 retirement)
  Brokerage $50K (non-retirement); House $450K (trust); Mortgage $200K (liability)
"""

from datetime import date

import calculations as calc


def sample_accounts():
    return [
        {"owner": "client1", "category": "retirement", "balance": 11000},   # IRA
        {"owner": "client1", "category": "retirement", "balance": 15000},   # Roth IRA
        {"owner": "client2", "category": "retirement", "balance": 8000},    # spouse 401k
        {"owner": "joint", "category": "non_retirement", "balance": 50000},  # brokerage
        {"owner": "joint", "category": "liability", "balance": 200000},     # mortgage
    ]


# ---- SACS ----------------------------------------------------------------- #

def test_sacs_excess():
    assert calc.sacs_excess(15000, 11000) == 4000


def test_sacs_excess_handles_blank():
    assert calc.sacs_excess("", "") == 0
    assert calc.sacs_excess(15000, "") == 15000


def test_private_reserve_target_single_deductible():
    # 6 * 11000 + 5000 = 71000
    assert calc.private_reserve_target(11000, 5000) == 71000


def test_private_reserve_target_list_of_deductibles():
    # 6 * 10000 + (1000 + 2500 + 500) = 64000
    assert calc.private_reserve_target(10000, [1000, 2500, 500]) == 64000


# ---- TCC totals ----------------------------------------------------------- #

def test_client1_retirement_total():
    assert calc.retirement_total(sample_accounts(), calc.CLIENT1) == 26000


def test_client2_retirement_total_is_separate():
    assert calc.retirement_total(sample_accounts(), calc.CLIENT2) == 8000


def test_non_retirement_total_excludes_trust():
    accounts = sample_accounts() + [
        {"owner": "joint", "category": "trust", "balance": 450000},
    ]
    # Trust must NOT be folded into the non-retirement total.
    assert calc.non_retirement_total(accounts) == 50000


def test_trust_total_uses_home_value():
    assert calc.trust_total(sample_accounts(), home_value=450000) == 450000


def test_trust_total_adds_explicit_trust_accounts():
    accounts = sample_accounts() + [
        {"owner": "joint", "category": "trust", "balance": 20000},
    ]
    assert calc.trust_total(accounts, home_value=450000) == 470000


def test_grand_total_net_worth():
    # 26000 + 8000 + 50000 + 450000 = 534000
    assert calc.grand_total_net_worth(26000, 8000, 50000, 450000) == 534000


def test_liabilities_total_is_separate_not_subtracted():
    accounts = sample_accounts()
    liabilities = calc.liabilities_total(accounts)
    assert liabilities == 200000

    # Net worth is computed WITHOUT subtracting liabilities (PRD rule).
    grand = calc.grand_total_net_worth(
        calc.retirement_total(accounts, calc.CLIENT1),
        calc.retirement_total(accounts, calc.CLIENT2),
        calc.non_retirement_total(accounts),
        calc.trust_total(accounts, home_value=450000),
    )
    assert grand == 534000
    assert grand - liabilities != grand  # confirms liabilities are tracked but excluded


# ---- compute_report aggregate -------------------------------------------- #

def test_compute_report_matches_prd_example():
    accounts = sample_accounts()
    fields = {
        "inflow": 15000,
        "outflow": 11000,
        "monthly_expenses": 11000,
        "insurance_deductibles": 5000,
        "home_value": 450000,
    }
    result = calc.compute_report(accounts, fields)
    assert result["excess"] == 4000
    assert result["private_reserve_target"] == 71000
    assert result["client1_retirement_total"] == 26000
    assert result["client2_retirement_total"] == 8000
    assert result["non_retirement_total"] == 50000
    assert result["trust_total"] == 450000
    assert result["grand_total"] == 534000
    assert result["liabilities_total"] == 200000


# ---- Age helper ----------------------------------------------------------- #

def test_calculate_age():
    dob = date(2000, 6, 25)
    assert calc.calculate_age(dob, on_date=date(2026, 6, 25)) == 26
    assert calc.calculate_age(dob, on_date=date(2026, 6, 24)) == 25


def test_calculate_age_none():
    assert calc.calculate_age(None) is None
