"""Shared server helpers: time, permissions, input cleaning, rate limits, app settings.

Every other server module imports this as `from . import common as C`.
Rules every callable follows:
  - check who is calling (C.me() / C.require_user() / C.require_admin()) before touching data
  - return JSON-friendly values only (dicts, lists, str, numbers, bools, None); dates via C.iso()
  - expected problems return C.fail("Message the user can read"); the page shows it
"""
import datetime as dt
import re

import anvil.server
import anvil.users
from anvil.tables import app_tables


def now():
    return dt.datetime.now(dt.timezone.utc)


def iso(v):
    """date/datetime -> ISO string (datetimes in UTC), anything else unchanged."""
    if isinstance(v, dt.datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=dt.timezone.utc)
        return v.astimezone(dt.timezone.utc).isoformat()
    if isinstance(v, dt.date):
        return v.isoformat()
    return v


def fail(message):
    return {"ok": False, "error": message}


def ok(**data):
    data["ok"] = True
    return data


def text(value, limit=200, multiline=False):
    """Clean user text: str, trimmed, length-capped; single-line unless multiline."""
    s = "" if value is None else str(value)
    s = s.replace("\r\n", "\n").strip()
    if not multiline:
        s = re.sub(r"\s+", " ", s)
    else:
        s = re.sub(r"\n{3,}", "\n\n", s)
    return s[:limit]


def me():
    return anvil.users.get_user()


def require_user():
    u = anvil.users.get_user()
    if u is None:
        raise anvil.server.PermissionDenied("Please sign in first.")
    return u


def is_admin(user):
    return bool(user is not None and user["is_admin"])


def require_admin():
    u = require_user()
    if not is_admin(u):
        raise anvil.server.PermissionDenied("Only admins can do that.")
    return u


def name_of(user):
    if user is None:
        return "Someone"
    return user["display_name"] or (user["email"] or "Someone").split("@")[0].capitalize()


def row_by_id(table, row_id):
    """get_by_id that returns None for a missing or malformed id (ids come from the browser)."""
    if not isinstance(row_id, str) or not row_id:
        return None
    try:
        return table.get_by_id(row_id)
    except Exception:
        return None


def rate_limited(key, limit, seconds):
    """True if this browser session already did `key` `limit` times in the last `seconds`."""
    stamp = now()
    store = "rate_" + key
    recent = [t for t in (getattr(anvil.server, "session").get(store) or [])
              if (stamp - dt.datetime.fromisoformat(t)).total_seconds() < seconds]
    if len(recent) >= limit:
        return True
    getattr(anvil.server, "session")[store] = recent + [stamp.isoformat()]
    return False


def get_setting(key, default=None):
    row = app_tables.app_settings.get(key=key)
    return default if row is None else row["value"]


def set_setting(key, value):
    row = app_tables.app_settings.get(key=key)
    if row is None:
        app_tables.app_settings.add_row(key=key, value=value)
    else:
        row["value"] = value


# ----------------------------------------------------------------------------------------------- VitalRPA helpers
def today():
    return now().date()


def utc(v):
    """A datetime from a table, always timezone-aware UTC (None stays None)."""
    if v is None:
        return None
    if v.tzinfo is None:
        return v.replace(tzinfo=dt.timezone.utc)
    return v.astimezone(dt.timezone.utc)


def minutes_since(v):
    v = utc(v)
    return None if v is None else (now() - v).total_seconds() / 60.0


def token(n=10, prefix=""):
    import secrets
    alphabet = "abcdefghijkmnpqrstuvwxyz23456789"
    return prefix + "".join(secrets.choice(alphabet) for _ in range(n))


def origin():
    """The app's public address (for links in emails and the snippet)."""
    try:
        return anvil.server.get_app_origin() or ""
    except Exception:
        return ""


def add_rows(table, rows):
    """Many rows in one go when Anvil supports it (faster demo loading), one by one otherwise."""
    if not rows:
        return
    try:
        table.add_rows(rows)
    except AttributeError:
        for r in rows:
            table.add_row(**r)


def bump(counts, key, n=1, cap=60):
    """Add n to counts[key] in a small {name: count} dict; past `cap` names, new ones go to "(other)"."""
    key = (key or "")[:160] or "(none)"
    if key not in counts and len(counts) >= cap:
        key = "(other)"
    counts[key] = counts.get(key, 0) + n
    return counts


# ----------------------------------------------------------------------------------------------- whose fleet to show
DEMO_OWNER_EMAIL = "mara.ops.demo@example.com"  # owns the sample fleet (DemoData)


def has_fleet(user):
    return user is not None and (len(app_tables.sites.search(owner=user)) > 0 or len(app_tables.heartbeats.search(owner=user)) > 0)


def scope(user, sample=None):
    """([owner rows], mode). People with nothing of their own yet see the sample fleet (read-only):
    sample=None decides by itself, True asks for the sample, False for their own."""
    mine = has_fleet(user)
    if sample is True or (sample is None and not mine):
        demo = app_tables.users.get(email=DEMO_OWNER_EMAIL)
        if demo is not None:
            return [demo], "sample"
    return [user], "mine"


def can_view(row, user):
    return row is not None and (row["owner"] == user or bool(row["is_demo"]) or is_admin(user))


def can_edit(row, user):
    return row is not None and user is not None and (row["owner"] == user or is_admin(user))


def edit_error(row, user):
    """None if `user` may change `row`, else a message."""
    if row is None:
        return "That no longer exists."
    if can_edit(row, user):
        return None
    if row["is_demo"]:
        return "This belongs to the sample fleet, so it's read-only. Add your own site to try it for real."
    return "That isn't yours."
