# AW Client Report Portal

A small internal portal for a financial-planning firm. The team enters client
financial data into structured forms; the app auto-calculates every total and
generates two polished quarterly PDFs in minutes instead of a full day:

- **SACS** — *Simple Automated Cash Flow*: a cashflow diagram (green **Inflow** →
  red **Outflow** → blue **Private Reserve**).
- **TCC** — *Total Client Chart*: a net-worth overview with retirement,
  non-retirement, trust, and a separate liabilities section.

Built per `PRD AI Engineer Test`. No AI and no external API integrations in V1 —
all balances are entered manually (intentional, per the PRD).

## Features (V1)

- **Client records** — names, DOB (age auto-calculated), SSN last-4, account
  structure (retirement / non-retirement / trust / liabilities), static financials.
- **One-click quarterly report** — a data-entry form pre-filled with static data,
  showing each field's last-quarter value, with "use last value" shortcuts and
  **live totals** as you type. Required balances must be filled in.
- **Automated math** — exact PRD rules: excess = inflow − outflow; reserve target
  = 6 × expenses + deductibles; per-spouse retirement totals; grand-total net worth.
  Liabilities are shown **separately and never subtracted**; the trust is **never**
  folded into the non-retirement total.
- **Polished PDFs** — fixed-layout SACS and TCC PDFs (WeasyPrint) that match the
  on-screen preview exactly, plus a re-downloadable report history.
- **Individual logins** for each team member (financial/SSN data stays behind auth).

## Tech stack

Python · Flask · Flask-Login · Flask-SQLAlchemy · SQLite · Jinja2 +
HTML/CSS/SVG · WeasyPrint · gunicorn. Deploys on Railway.

## Project structure

```
app.py             Flask app factory, auth, routes
models.py          SQLAlchemy models (User, Client, Account, Report, AccountBalance)
calculations.py    Pure, unit-tested financial rules
pdf.py             HTML templates → WeasyPrint PDF
seed.py            Seed team users + a demo client
templates/         UI + report partials (_sacs_body, _tcc_body shared by preview & PDF)
static/            style.css, app.js (live totals, dynamic account rows)
tests/             pytest for the calculation rules
nixpacks.toml      Native libs WeasyPrint needs on Railway
railway.json       Railway build/deploy config
```

## Local development

> WeasyPrint needs native libraries (Pango, Cairo, GDK-Pixbuf). On Linux/macOS
> they install cleanly. On **Windows**, install the GTK runtime (see the
> [WeasyPrint docs](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#windows));
> the app, preview, and tests all run without it — only PDF *download* needs it.

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate     Linux/macOS:  source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # then edit SECRET_KEY etc.
python seed.py                # creates team users + a demo client
flask --app app run --debug   # http://127.0.0.1:5000
```

Default seeded login: `andrew@windbrook.example` / `changeme123`
(override with `SEED_TEAM_PASSWORD`). **Change it after first login** under **My Profile**.

## Managing accounts

- **Change your own password** — click your name in the top bar to open **My Profile**,
  then enter your current password and a new one (min 8 characters).
- **Manage the team** (admins only) — the **Team** link in the top bar lets an admin add or
  remove members and reset anyone's password, so onboarding a new user never requires the
  `seed.py` script or shell access. You can't delete your own account or the last admin (prevents
  lockout). The seed gives **Andrew** the `admin` role; adjust roles as needed.
- **Emergency recovery** — if all admin passwords are lost, reset one from a shell:
  ```bash
  python -c "from app import app; from models import db, User; app.app_context().push(); \
  u=db.session.query(User).filter_by(email='andrew@windbrook.example').first(); \
  u.set_password('NewPassword123'); db.session.commit(); print('reset')"
  ```
  (On Railway, run the same snippet from the service shell.)

Run the tests:

```bash
pytest
```

## Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `SECRET_KEY` | yes (prod) | Flask session signing. Generate: `python -c "import secrets;print(secrets.token_hex(32))"` |
| `RAILWAY_DATABASE_PATH` | yes (Railway) | Absolute SQLite path on the mounted volume, e.g. `/data/portal.db`. Defaults to `./instance/portal.db` locally. |
| `SEED_ADMIN_NAME` / `SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD` | optional | First admin auto-created on first boot if no users exist. |
| `SEED_TEAM_PASSWORD` | optional | Password used by `python seed.py` for the 3 team accounts. |

## Deploy to Railway

Follows the standard Railway flow (the steps in `RAILWAY.pdf`):

1. **Push this repo to GitHub** (already wired to `clyde-homu/ai_application_prd`).
2. In Railway: **New Project → Deploy from GitHub repo** → pick the repo. Railway
   detects `nixpacks.toml` / `railway.json` and builds automatically.
3. **Add a Volume** to the service and set its mount path to `/data` (this keeps
   the SQLite database across redeploys).
4. **Variables** → add:
   - `SECRET_KEY` = a long random value
   - `RAILWAY_DATABASE_PATH` = `/data/portal.db`
   - `SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD` (your first login)
5. Railway builds and starts `gunicorn app:app`. On first boot the database is
   created and the admin user is seeded. **Settings → Networking → Generate
   Domain** to get a public URL.
6. (Optional) Open the service shell and run `python seed.py --no-demo` to add the
   other team members.
7. **Smoke test**: open the domain, log in, create a client, generate a report,
   download the SACS and TCC PDFs.

### Dockerfile fallback

If a future Nixpacks base can't resolve the Pango/Cairo packages, switch the
builder to a Dockerfile based on `python:3.11-slim` and `apt-get install -y
libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 libcairo2 libffi-dev
shared-mime-info fonts-liberation`, then `pip install -r requirements.txt` and
run the same gunicorn command.

## Out of scope (V2)

Canva export, Dropbox auto-save, monthly email distribution, and automated data
pulls (RightCapital / Schwab / Pinnacle / Zillow) are deferred per the PRD.

## Note on report fidelity

The SACS and TCC layouts are recreated from the PRD's written description. Once the
firm shares the real sample PDFs / "Data Point List," do a styling pass in
`templates/_sacs_body.html`, `templates/_tcc_body.html`, and
`templates/_report_styles.html` to match exact colors and spacing.
