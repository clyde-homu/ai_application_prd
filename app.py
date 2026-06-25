"""AW Client Report Portal — Flask application.

Run locally:   flask --app app run --debug
Production:    gunicorn app:app
"""

from __future__ import annotations

import os
from datetime import date
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)

import calculations as calc
from models import Account, AccountBalance, Client, Report, User, db
from pdf import render_sacs_pdf, render_tcc_pdf

load_dotenv()

# Account type options offered in the UI, grouped by category.
ACCOUNT_TYPES = {
    calc.RETIREMENT: ["IRA", "Roth IRA", "401K", "403B", "Pension", "SEP IRA"],
    calc.NON_RETIREMENT: ["Brokerage", "Joint Brokerage", "Checking", "Savings", "Other"],
    calc.TRUST: ["Trust Account", "Trust (Real Estate)"],
    calc.LIABILITY: ["Mortgage", "Auto Loan", "HELOC", "Personal Loan", "Other"],
}

# Team roles and the minimum password length enforced everywhere.
USER_ROLES = ["admin", "planner", "assistant"]
MIN_PASSWORD_LENGTH = 8


# --------------------------------------------------------------------------- #
# Parsing helpers (forms send strings)
# --------------------------------------------------------------------------- #

def _clean_number(raw: str | None) -> str:
    return (raw or "").replace(",", "").replace("$", "").strip()


def parse_float(raw, default: float = 0.0) -> float:
    cleaned = _clean_number(raw)
    if cleaned == "":
        return default
    try:
        return float(cleaned)
    except ValueError:
        return default


def parse_optional_float(raw):
    cleaned = _clean_number(raw)
    if cleaned == "":
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_date(raw):
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def admin_required(view):
    """Allow only authenticated admins; everyone else gets 403."""

    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if getattr(current_user, "role", None) != "admin":
            abort(403)
        return view(*args, **kwargs)

    return wrapped


# --------------------------------------------------------------------------- #
# App factory
# --------------------------------------------------------------------------- #

def _database_uri() -> str:
    db_path = os.environ.get("RAILWAY_DATABASE_PATH")
    if not db_path:
        instance_dir = Path(__file__).parent / "instance"
        instance_dir.mkdir(exist_ok=True)
        db_path = str(instance_dir / "portal.db")
    # Make sure the parent dir exists (e.g. the Railway volume mount point).
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{db_path}"


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")
    app.config["SQLALCHEMY_DATABASE_URI"] = _database_uri()
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)

    login_manager = LoginManager(app)
    login_manager.login_view = "login"
    login_manager.login_message_category = "error"

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    register_routes(app)

    with app.app_context():
        db.create_all()
        ensure_seed_user()

    return app


def ensure_seed_user() -> None:
    """Create an initial admin from env vars if no users exist yet."""
    if db.session.query(User).count() > 0:
        return
    name = os.environ.get("SEED_ADMIN_NAME", "Admin")
    email = os.environ.get("SEED_ADMIN_EMAIL", "admin@example.com")
    password = os.environ.get("SEED_ADMIN_PASSWORD", "change-me-now")
    user = User(name=name, email=email.lower(), role="admin")
    user.set_password(password)
    db.session.add(user)
    db.session.commit()


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #

def register_routes(app: Flask) -> None:

    # ---- Currency formatting filter for templates ---------------------- #
    @app.template_filter("money")
    def money_filter(value):
        try:
            return f"${float(value):,.0f}"
        except (TypeError, ValueError):
            return "$0"

    # ---- Auth ----------------------------------------------------------- #
    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            user = db.session.query(User).filter_by(email=email).first()
            if user and user.check_password(password):
                login_user(user)
                return redirect(request.args.get("next") or url_for("dashboard"))
            flash("Invalid email or password.", "error")
        return render_template("login.html")

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        return redirect(url_for("login"))

    # ---- Profile (self-service password change) ------------------------- #
    @app.route("/profile", methods=["GET", "POST"])
    @login_required
    def profile():
        if request.method == "POST":
            current = request.form.get("current_password", "")
            new = request.form.get("new_password", "")
            confirm = request.form.get("confirm_password", "")
            if not current_user.check_password(current):
                flash("Current password is incorrect.", "error")
            elif len(new) < MIN_PASSWORD_LENGTH:
                flash(f"New password must be at least {MIN_PASSWORD_LENGTH} characters.", "error")
            elif new != confirm:
                flash("New passwords do not match.", "error")
            else:
                current_user.set_password(new)
                db.session.commit()
                flash("Password updated.", "success")
                return redirect(url_for("profile"))
        return render_template("profile.html")

    # ---- Team management (admin only) ----------------------------------- #
    @app.route("/team")
    @admin_required
    def team():
        users = db.session.query(User).order_by(User.name).all()
        return render_template("team.html", users=users, roles=USER_ROLES)

    @app.route("/team/add", methods=["POST"])
    @admin_required
    def team_add():
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        role = request.form.get("role", "planner").strip()
        password = request.form.get("password", "")
        if not name or not email:
            flash("Name and email are required.", "error")
        elif len(password) < MIN_PASSWORD_LENGTH:
            flash(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.", "error")
        elif db.session.query(User).filter_by(email=email).first():
            flash("A user with that email already exists.", "error")
        else:
            user = User(name=name, email=email,
                        role=role if role in USER_ROLES else "planner")
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash(f"Added {name}.", "success")
        return redirect(url_for("team"))

    @app.route("/team/<int:user_id>/reset", methods=["POST"])
    @admin_required
    def team_reset(user_id):
        user = db.get_or_404(User, user_id)
        password = request.form.get("password", "")
        if len(password) < MIN_PASSWORD_LENGTH:
            flash(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.", "error")
        else:
            user.set_password(password)
            db.session.commit()
            flash(f"Password reset for {user.name}.", "success")
        return redirect(url_for("team"))

    @app.route("/team/<int:user_id>/delete", methods=["POST"])
    @admin_required
    def team_delete(user_id):
        user = db.get_or_404(User, user_id)
        admin_count = db.session.query(User).filter_by(role="admin").count()
        if user.id == current_user.id:
            flash("You can't delete your own account.", "error")
        elif user.role == "admin" and admin_count <= 1:
            flash("Can't delete the last admin.", "error")
        else:
            db.session.delete(user)
            db.session.commit()
            flash(f"Removed {user.name}.", "success")
        return redirect(url_for("team"))

    # ---- Dashboard ------------------------------------------------------ #
    @app.route("/")
    @login_required
    def dashboard():
        clients = db.session.query(Client).order_by(Client.client1_name).all()
        return render_template("dashboard.html", clients=clients)

    # ---- Client create / edit ------------------------------------------ #
    @app.route("/clients/new", methods=["GET", "POST"])
    @login_required
    def client_new():
        if request.method == "POST":
            client = Client()
            _apply_client_form(client)
            db.session.add(client)
            db.session.commit()
            flash("Client created.", "success")
            return redirect(url_for("client_detail", client_id=client.id))
        return render_template(
            "client_form.html", client=None, account_types=ACCOUNT_TYPES
        )

    @app.route("/clients/<int:client_id>/edit", methods=["GET", "POST"])
    @login_required
    def client_edit(client_id):
        client = db.get_or_404(Client, client_id)
        if request.method == "POST":
            _apply_client_form(client)
            db.session.commit()
            flash("Client updated.", "success")
            return redirect(url_for("client_detail", client_id=client.id))
        return render_template(
            "client_form.html", client=client, account_types=ACCOUNT_TYPES
        )

    @app.route("/clients/<int:client_id>")
    @login_required
    def client_detail(client_id):
        client = db.get_or_404(Client, client_id)
        return render_template("client_detail.html", client=client)

    @app.route("/clients/<int:client_id>/delete", methods=["POST"])
    @login_required
    def client_delete(client_id):
        client = db.get_or_404(Client, client_id)
        db.session.delete(client)
        db.session.commit()
        flash("Client deleted.", "success")
        return redirect(url_for("dashboard"))

    # ---- Quarterly report: data entry ---------------------------------- #
    @app.route("/clients/<int:client_id>/report/new", methods=["GET", "POST"])
    @login_required
    def report_new(client_id):
        client = db.get_or_404(Client, client_id)
        if not client.accounts:
            flash("Add at least one account before generating a report.", "error")
            return redirect(url_for("client_edit", client_id=client.id))

        last = client.last_report
        if request.method == "POST":
            report = Report(client_id=client.id, created_by=current_user.id)
            _apply_report_form(report, client)
            db.session.add(report)
            db.session.flush()  # assign report.id before adding balances
            _apply_account_balances(report, client)
            db.session.commit()
            flash("Report generated.", "success")
            return redirect(url_for("report_preview", report_id=report.id))

        return render_template(
            "report_form.html",
            client=client,
            last=last,
            last_balances=last.balance_map() if last else {},
            today=date.today().isoformat(),
        )

    # ---- Report preview + PDFs ----------------------------------------- #
    @app.route("/reports/<int:report_id>")
    @login_required
    def report_preview(report_id):
        report = db.get_or_404(Report, report_id)
        return render_template(
            "report_preview.html",
            report=report,
            client=report.client,
            c=report.computed(),
            groups=report.grouped(),
        )

    @app.route("/reports/<int:report_id>/sacs.pdf")
    @login_required
    def report_sacs_pdf(report_id):
        report = db.get_or_404(Report, report_id)
        pdf_bytes = render_sacs_pdf(report)
        return _pdf_response(pdf_bytes, report, "SACS")

    @app.route("/reports/<int:report_id>/tcc.pdf")
    @login_required
    def report_tcc_pdf(report_id):
        report = db.get_or_404(Report, report_id)
        pdf_bytes = render_tcc_pdf(report)
        return _pdf_response(pdf_bytes, report, "TCC")

    @app.route("/reports/<int:report_id>/delete", methods=["POST"])
    @login_required
    def report_delete(report_id):
        report = db.get_or_404(Report, report_id)
        client_id = report.client_id
        db.session.delete(report)
        db.session.commit()
        flash("Report deleted.", "success")
        return redirect(url_for("client_detail", client_id=client_id))


# --------------------------------------------------------------------------- #
# Form application helpers
# --------------------------------------------------------------------------- #

def _apply_client_form(client: Client) -> None:
    f = request.form
    client.married = f.get("married") == "on"
    client.client1_name = f.get("client1_name", "").strip()
    client.client1_dob = parse_date(f.get("client1_dob"))
    client.client1_ssn_last4 = f.get("client1_ssn_last4", "").strip()[:4] or None
    client.client2_name = f.get("client2_name", "").strip() or None
    client.client2_dob = parse_date(f.get("client2_dob"))
    client.client2_ssn_last4 = f.get("client2_ssn_last4", "").strip()[:4] or None
    client.monthly_salary = parse_float(f.get("monthly_salary"))
    client.monthly_expense_budget = parse_float(f.get("monthly_expense_budget"))
    client.insurance_deductibles = parse_float(f.get("insurance_deductibles"))
    client.private_reserve_target_override = parse_optional_float(
        f.get("private_reserve_target_override")
    )
    client.trust_address = f.get("trust_address", "").strip() or None
    _apply_accounts(client)


def _apply_accounts(client: Client) -> None:
    """Replace the client's accounts from the repeating form rows.

    Every per-row control (selects + text inputs) always submits a value, so the
    parallel lists stay aligned by position. ``account_is_investment`` is a
    Yes/No <select> rather than a checkbox for exactly this reason.
    """
    f = request.form
    owners = f.getlist("account_owner")
    categories = f.getlist("account_category")
    types = f.getlist("account_type")
    last4s = f.getlist("account_last4")
    rates = f.getlist("account_rate")
    investments = f.getlist("account_is_investment")

    def _at(seq, i, default=""):
        return seq[i] if i < len(seq) else default

    client.accounts.clear()
    for i, category in enumerate(categories):
        atype = _at(types, i).strip()
        if not category or not atype:
            continue
        client.accounts.append(
            Account(
                owner=_at(owners, i, calc.JOINT) or calc.JOINT,
                category=category,
                type=atype,
                acct_last4=(_at(last4s, i).strip()[:8]) or None,
                interest_rate=parse_optional_float(_at(rates, i)),
                is_investment=_at(investments, i) == "yes",
            )
        )


def _apply_report_form(report: Report, client: Client) -> None:
    f = request.form
    report.report_date = parse_date(f.get("report_date")) or date.today()
    report.inflow = parse_float(f.get("inflow"), client.monthly_salary or 0)
    report.outflow = parse_float(f.get("outflow"), client.monthly_expense_budget or 0)
    report.insurance_deductibles = parse_float(
        f.get("insurance_deductibles"), client.insurance_deductibles or 0
    )
    report.private_reserve_balance = parse_float(f.get("private_reserve_balance"))
    report.schwab_investment_balance = parse_float(f.get("schwab_investment_balance"))
    report.home_value = parse_float(f.get("home_value"))


def _apply_account_balances(report: Report, client: Client) -> None:
    f = request.form
    for acct in client.accounts:
        balance = parse_float(f.get(f"balance_{acct.id}"))
        cash = parse_optional_float(f.get(f"cash_{acct.id}")) if acct.is_investment else None
        report.balances.append(
            AccountBalance(account_id=acct.id, balance=balance, cash_balance=cash)
        )


def _pdf_response(pdf_bytes: bytes, report: Report, kind: str):
    from flask import Response

    safe_name = report.client.client1_name.split()[0] if report.client.client1_name else "client"
    filename = f"{kind}_{safe_name}_{report.report_date.isoformat()}.pdf"
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# Module-level app for `gunicorn app:app` and `flask --app app`.
app = create_app()


if __name__ == "__main__":
    app.run(debug=True, port=5000)
