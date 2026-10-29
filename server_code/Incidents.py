"""Incidents: something is wrong with a site or a cron heartbeat. Opened and closed by the robots
(Monitor, Beacon, Bots), never duplicated (one open incident per subject and kind), and every
opening / recovery runs the owner's playbooks (Alerts.fire). People can acknowledge, add notes and
resolve by hand."""
import anvil.server
from anvil.tables import app_tables
import anvil.tables as tables

from . import common as C

KINDS = {
    "down": ("Down", "critical"),
    "slow": ("Slow", "warning"),
    "ssl": ("Certificate", "warning"),
    "domain": ("Domain", "warning"),
    "silence": ("Visitors stopped", "warning"),
    "jserrors": ("JavaScript errors", "warning"),
    "heartbeat": ("Missed check-in", "critical"),
}


def _open_rows(site=None, heartbeat=None, kind=None):
    kw = {"resolved": None}
    if site is not None:
        kw["site"] = site
    if heartbeat is not None:
        kw["heartbeat"] = heartbeat
    if kind:
        kw["kind"] = kind
    return list(app_tables.incidents.search(**kw))


def open_incident(owner, kind, title, detail="", site=None, heartbeat=None, severity=None):
    """Open an incident unless the same one is already open (then it may be escalated). Returns the row."""
    severity = severity or KINDS.get(kind, ("", "warning"))[1]
    for r in _open_rows(site=site, heartbeat=heartbeat, kind=kind):
        if severity == "critical" and r["severity"] != "critical":
            r.update(severity="critical", title=C.text(title, 160), detail=C.text(detail, 600))
        return r
    demo = bool((site and site["is_demo"]) or (heartbeat and heartbeat["is_demo"]))
    r = app_tables.incidents.add_row(owner=owner, site=site, heartbeat=heartbeat, kind=kind, severity=severity,
                                     title=C.text(title, 160), detail=C.text(detail, 600), started=C.now(), resolved=None,
                                     resolution=None, acked=False, notes=[], is_demo=demo)
    from . import Alerts
    Alerts.fire(kind, r)
    return r


def resolve(site=None, heartbeat=None, kind=None, how="", by_robot=True):
    """Close the matching open incidents; runs "recovered" playbooks. Returns how many closed."""
    if site is None and heartbeat is None:
        return 0
    rows = _open_rows(site=site, heartbeat=heartbeat, kind=kind)
    from . import Alerts
    for r in rows:
        r.update(resolved=C.now(), resolution=C.text(how, 200) or ("Resolved by the robots" if by_robot else "Resolved"))
        Alerts.fire("recovered", r)
    return len(rows)


def subject_name(r):
    if r["site"] is not None:
        return r["site"]["name"]
    if r["heartbeat"] is not None:
        return r["heartbeat"]["name"]
    return "?"


def to_dict(r, me=None):
    started, resolved = C.utc(r["started"]), C.utc(r["resolved"])
    end = resolved or C.now()
    return {"id": r.get_id(), "kind": r["kind"], "kind_label": KINDS.get(r["kind"], (r["kind"], ""))[0],
            "severity": r["severity"], "title": r["title"], "detail": r["detail"] or "",
            "started": C.iso(started), "resolved": C.iso(resolved), "resolution": r["resolution"] or "",
            "minutes": int((end - started).total_seconds() // 60), "acked": bool(r["acked"]),
            "notes": list(r["notes"] or []), "subject": subject_name(r),
            "site_id": r["site"].get_id() if r["site"] is not None else None,
            "heartbeat_id": r["heartbeat"].get_id() if r["heartbeat"] is not None else None,
            "demo": bool(r["is_demo"]), "can_edit": C.can_edit(r, me)}


@anvil.server.callable(require_user=True)
def list_incidents(status="open", sample=None):
    me = C.require_user()
    owners, mode = C.scope(me, sample)
    rows = []
    for o in owners:
        rows += list(app_tables.incidents.search(tables.order_by("started", ascending=False), owner=o))
    rows.sort(key=lambda r: C.utc(r["started"]), reverse=True)
    open_n = len([r for r in rows if r["resolved"] is None])
    if status == "open":
        rows = [r for r in rows if r["resolved"] is None]
    elif status == "resolved":
        rows = [r for r in rows if r["resolved"] is not None]
    # Open critical first, then newest.
    rows.sort(key=lambda r: (r["resolved"] is not None, r["severity"] != "critical"))
    return {"mode": mode, "incidents": [to_dict(r, me) for r in rows[:200]], "open": open_n, "total": len(rows)}


def _mine(incident_id, me):
    r = C.row_by_id(app_tables.incidents, incident_id)
    return r, C.edit_error(r, me)


@anvil.server.callable(require_user=True)
def ack_incident(incident_id):
    me = C.require_user()
    r, err = _mine(incident_id, me)
    if err:
        return C.fail(err)
    if not r["acked"]:
        r["acked"] = True
        r["notes"] = list(r["notes"] or []) + [{"at": C.iso(C.now()), "by": C.name_of(me), "text": "Acknowledged: someone is on it."}]
    return C.ok(incident=to_dict(r, me))


@anvil.server.callable(require_user=True)
def add_incident_note(incident_id, text):
    me = C.require_user()
    r, err = _mine(incident_id, me)
    if err:
        return C.fail(err)
    text = C.text(text, 600, multiline=True)
    if len(text) < 2:
        return C.fail("Write a short note first.")
    notes = list(r["notes"] or [])
    if len(notes) >= 60:
        return C.fail("This incident has a lot of notes already.")
    r["notes"] = notes + [{"at": C.iso(C.now()), "by": C.name_of(me), "text": text}]
    return C.ok(incident=to_dict(r, me))


@anvil.server.callable(require_user=True)
def resolve_incident(incident_id, note=""):
    me = C.require_user()
    r, err = _mine(incident_id, me)
    if err:
        return C.fail(err)
    if r["resolved"] is None:
        note = C.text(note, 200)
        r.update(resolved=C.now(), resolution="Resolved by %s%s" % (C.name_of(me), (": " + note) if note else ""))
        from . import Alerts
        Alerts.fire("recovered", r)
    return C.ok(incident=to_dict(r, me))
