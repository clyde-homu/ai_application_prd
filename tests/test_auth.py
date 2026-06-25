"""Tests for the profile (password change) and admin team-management features."""

import os
import tempfile

# Point the app at a throwaway database BEFORE importing it.
os.environ.setdefault("RAILWAY_DATABASE_PATH", os.path.join(tempfile.mkdtemp(), "test.db"))
os.environ.setdefault("SECRET_KEY", "test-secret")

import pytest  # noqa: E402

from app import app as flask_app  # noqa: E402
from models import User, db  # noqa: E402


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.app_context():
        db.session.query(User).delete()
        db.session.commit()
        admin = User(name="Andrew", email="andrew@test.com", role="admin")
        admin.set_password("changeme123")
        planner = User(name="Rebecca", email="rebecca@test.com", role="planner")
        planner.set_password("changeme123")
        db.session.add_all([admin, planner])
        db.session.commit()
    return flask_app.test_client()


def login(client, email, password="changeme123"):
    return client.post(
        "/login", data={"email": email, "password": password}, follow_redirects=True
    )


def logged_in(resp):
    return resp.status_code == 200 and b"Sign out" in resp.data


# ---- Profile: change password -------------------------------------------- #

def test_change_password_wrong_current_is_rejected(client):
    login(client, "andrew@test.com")
    resp = client.post("/profile", data={
        "current_password": "wrong",
        "new_password": "brandnew123",
        "confirm_password": "brandnew123",
    }, follow_redirects=True)
    assert b"Current password is incorrect" in resp.data
    # Old password still works.
    client.get("/logout")
    assert logged_in(login(client, "andrew@test.com", "changeme123"))


def test_change_password_success(client):
    login(client, "andrew@test.com")
    resp = client.post("/profile", data={
        "current_password": "changeme123",
        "new_password": "brandnew123",
        "confirm_password": "brandnew123",
    }, follow_redirects=True)
    assert b"Password updated" in resp.data
    client.get("/logout")
    assert not logged_in(login(client, "andrew@test.com", "changeme123"))  # old fails
    assert logged_in(login(client, "andrew@test.com", "brandnew123"))      # new works


def test_change_password_mismatch_rejected(client):
    login(client, "andrew@test.com")
    resp = client.post("/profile", data={
        "current_password": "changeme123",
        "new_password": "brandnew123",
        "confirm_password": "different123",
    }, follow_redirects=True)
    assert b"do not match" in resp.data


def test_change_password_too_short_rejected(client):
    login(client, "andrew@test.com")
    resp = client.post("/profile", data={
        "current_password": "changeme123",
        "new_password": "short",
        "confirm_password": "short",
    }, follow_redirects=True)
    assert b"at least 8 characters" in resp.data


# ---- Team: admin gating + management ------------------------------------- #

def test_non_admin_cannot_access_team(client):
    login(client, "rebecca@test.com")
    resp = client.get("/team")
    assert resp.status_code == 403


def test_admin_can_access_team(client):
    login(client, "andrew@test.com")
    resp = client.get("/team")
    assert resp.status_code == 200
    assert b"Add member" in resp.data


def test_admin_can_add_member_who_can_log_in(client):
    login(client, "andrew@test.com")
    resp = client.post("/team/add", data={
        "name": "Maryann", "email": "maryann@test.com",
        "role": "assistant", "password": "welcome123",
    }, follow_redirects=True)
    assert b"Added Maryann" in resp.data
    client.get("/logout")
    assert logged_in(login(client, "maryann@test.com", "welcome123"))


def test_add_member_duplicate_email_rejected(client):
    login(client, "andrew@test.com")
    resp = client.post("/team/add", data={
        "name": "Dup", "email": "rebecca@test.com",
        "role": "planner", "password": "welcome123",
    }, follow_redirects=True)
    assert b"already exists" in resp.data


def test_admin_can_reset_member_password(client):
    login(client, "andrew@test.com")
    with flask_app.app_context():
        rebecca = db.session.query(User).filter_by(email="rebecca@test.com").first()
        rid = rebecca.id
    resp = client.post(f"/team/{rid}/reset", data={"password": "resetpass123"},
                       follow_redirects=True)
    assert b"Password reset" in resp.data
    client.get("/logout")
    assert logged_in(login(client, "rebecca@test.com", "resetpass123"))


def test_admin_cannot_delete_self(client):
    login(client, "andrew@test.com")
    with flask_app.app_context():
        admin = db.session.query(User).filter_by(email="andrew@test.com").first()
        aid = admin.id
    resp = client.post(f"/team/{aid}/delete", follow_redirects=True)
    assert b"can't delete your own account" in resp.data.lower() or b"own account" in resp.data
    with flask_app.app_context():
        assert db.session.query(User).filter_by(email="andrew@test.com").first() is not None


def test_admin_can_remove_member(client):
    login(client, "andrew@test.com")
    with flask_app.app_context():
        rebecca = db.session.query(User).filter_by(email="rebecca@test.com").first()
        rid = rebecca.id
    resp = client.post(f"/team/{rid}/delete", follow_redirects=True)
    assert b"Removed" in resp.data
    with flask_app.app_context():
        assert db.session.query(User).filter_by(email="rebecca@test.com").first() is None
