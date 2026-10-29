"""Alerts: playbooks, the "if this happens, the robot does that" rules, and what they do.

A playbook = a trigger (an incident kind, "recovered" or "any") + optionally one site + actions:
  email   {type, to}    to = "" means the owner's alert address
  webhook {type, url}   POSTs JSON with "text" (Slack, Teams, Google Chat) and "content" (Discord)
  recheck {type}        a second robot loads the site again right away and writes the result as a note
Every action is written to actions_log. Sample-fleet playbooks only pretend (nothing is sent).
"""
import datetime as dt
import json

import anvil.email
import anvil.http
import anvil.server
from anvil.tables import app_tables
import anvil.tables as tables
import anvil.tables.query as q

from . import common as C

TRIGGERS = [
    ("down", "A site goes down"),
    ("slow", "A site turns slow"),
    ("ssl", "A certificate is expiring or broken"),
    ("domain", "A domain is about to expire"),
    ("silence", "Visitors stop arriving"),
    ("jserrors", "JavaScript errors pile up"),
    ("heartbeat", "A cron job misses its check-in"),
    ("any", "Any new incident"),
    ("recovered", "Something recovers"),
]
TRIGGER_KEYS = {k for k, _ in TRIGGERS}
ACTION_TYPES = ("email", "webhook", "recheck")
MAX_ACTIONS_PER_HOUR = 60
MAX_PLAYBOOKS = 30


# ----------------------------------------------------------------------------------------------- firing
def fire(trigger, incident):
    owner = incident["owner"]
    if owner is None:
        return 0
    n = 0
    for pb in app_tables.playbooks.search(owner=owner, enabled=True):
        t = pb["trigger"]
        if not (t == trigger or (t == "any" and trigger != "recovered")):
            continue
        if pb["site"] is not None and pb["site"] != incident["site"]:
            continue
        run_playbook(pb, incident, trigger)
        n += 1
    return n


def _recent_actions(owner):
    since = C.now() - dt.timedelta(hours=1)
    return len(app_tables.actions_log.search(owner=owner, at=q.greater_than(since)))


def _message(incident, trigger, playbook_name):
    from . import Incidents
    subject = Incidents.subject_name(incident)
    if trigger == "recovered":
        head = "RECOVERED: %s" % incident["title"]
        body = incident["resolution"] or "It's fine again."
    else:
        head = "%s: %s" % (incident["severity"].upper(), incident["title"])
        body = incident["detail"] or ""
    link = C.origin()
    if link and incident["site"] is not None:
        link += "/#site/" + incident["site"].get_id()
    elif link:
        link += "/#incidents"
    text = "%s\n%s\nStarted %s UTC" % (head, body, C.utc(incident["started"]).strftime("%Y-%m-%d %H:%M"))
    if link:
        text += "\n%s" % link
    text += "\n(VitalRPA robot: %s)" % playbook_name
    return subject, head, text


def run_playbook(pb, incident, trigger, test=False):
    owner = pb["owner"]
    subject, head, text = _message(incident, trigger, pb["name"])
    pb.update(fired=(pb["fired"] or 0) + 1, last_fired=C.now())
    results = []
    for a in pb["actions"] or []:
        kind = a.get("type")
        if not test and _recent_actions(owner) >= MAX_ACTIONS_PER_HOUR:
            results.append(_log(pb, subject, kind, "", "Skipped: more than %d actions this hour" % MAX_ACTIONS_PER_HOUR, False))
            continue
        try:
            ok, target, result = _do(a, pb, incident, head, text, test)
        except Exception as e:  # noqa: BLE001 - one broken action never stops the others
            ok, target, result = False, a.get("url") or a.get("to") or "", "Failed: %s" % str(e)[:140]
        results.append(_log(pb, subject, kind, target, result, ok))
    return results


def _do(a, pb, incident, head, text, test):
    owner, kind = pb["owner"], a.get("type")
    demo = bool(pb["is_demo"])
    if kind == "email":
        to = a.get("to") or owner["alert_email"] or owner["email"]
        if demo:
            return True, to, "Simulated (sample fleet): email not sent"
        anvil.email.send(to=to, subject="[VitalRPA] " + head[:150], text=text, from_name="VitalRPA robots")
        return True, to, "Email sent"
    if kind == "webhook":
        url = a.get("url") or ""
        if demo:
            return True, url, "Simulated (sample fleet): webhook not called"
        payload = {"text": text, "content": text[:1900], "event": "test" if test else incident["kind"],
                   "severity": incident["severity"], "title": incident["title"],
                   "resolved": incident["resolved"] is not None, "started": C.iso(incident["started"])}
        if incident["site"] is not None:
            payload["site"] = {"name": incident["site"]["name"], "url": incident["site"]["url"]}
        try:
            anvil.http.request(url, method="POST", data=json.dumps(payload), timeout=10,
                               headers={"Content-Type": "application/json", "User-Agent": "VitalRPA-Bot/1.0"})
        except anvil.http.HttpError as e:
            return False, url, "Webhook answered HTTP %s" % getattr(e, "status", "?")
        return True, url, "Webhook delivered"
    if kind == "recheck":
        site = incident["site"]
        if site is None or test:
            return True, "", "Nothing to recheck" if site is None else "Recheck skipped (test run)"
        from . import Monitor
        res = Monitor.run_check(site, source="playbook")
        note = "Second robot recheck: %s" % ("still failing (%s)" % res["problem"] if res["state"] == "fail" else
                                              "loads fine now (HTTP %s, %s ms)" % (res["code"], res["ms"]))
        incident["notes"] = list(incident["notes"] or []) + [{"at": C.iso(C.now()), "by": "Robot", "text": note}]
        return True, site["name"], note
    return False, "", "Unknown action"


def _log(pb, subject, action, target, result, ok):
    app_tables.actions_log.add_row(owner=pb["owner"], at=C.now(), playbook=pb["name"], subject=C.text(subject, 120),
                                   action=action or "?", target=C.text(target, 200), result=C.text(result, 300), ok=ok,
                                   is_demo=bool(pb["is_demo"]))
    return {"action": action, "target": target, "result": result, "ok": ok}


# ----------------------------------------------------------------------------------------------- playbooks (people)
def to_dict(pb, me=None):
    return {"id": pb.get_id(), "name": pb["name"], "trigger": pb["trigger"],
            "trigger_label": dict(TRIGGERS).get(pb["trigger"], pb["trigger"]),
            "site_id": pb["site"].get_id() if pb["site"] is not None else None,
            "site_name": pb["site"]["name"] if pb["site"] is not None else "Any site",
            "actions": list(pb["actions"] or []), "enabled": bool(pb["enabled"]), "fired": pb["fired"] or 0,
            "last_fired": C.iso(pb["last_fired"]), "demo": bool(pb["is_demo"]), "can_edit": C.can_edit(pb, me)}


def clean_actions(actions):
    """(actions, error)."""
    out = []
    for a in (actions or [])[:6]:
        if not isinstance(a, dict):
            continue
        t = a.get("type")
        if t == "email":
            to = C.text(a.get("to"), 120)
            if to and ("@" not in to or "." not in to.split("@")[-1]):
                return None, "That email address doesn't look right: %s" % to
            out.append({"type": "email", "to": to})
        elif t == "webhook":
            url = C.text(a.get("url"), 400)
            from . import Probe
            clean = Probe.normalize_url(url)
            if not clean or not clean.startswith("https://"):
                return None, "Webhooks need a public https:// address."
            out.append({"type": "webhook", "url": clean})
        elif t == "recheck":
            out.append({"type": "recheck"})
    if not out:
        return None, "Pick at least one thing for the robot to do."
    return out, None


def default_playbook(owner):
    """Every new fleet starts with one: email me when anything breaks or recovers."""
    if len(app_tables.playbooks.search(owner=owner)):
        return
    for name, trigger in (("Email me when something breaks", "any"), ("Email me when it's fixed", "recovered")):
        app_tables.playbooks.add_row(owner=owner, name=name, trigger=trigger, site=None, actions=[{"type": "email", "to": ""}],
                                     enabled=True, fired=0, last_fired=None, created=C.now(), is_demo=False)


@anvil.server.callable(require_user=True)
def save_playbook(data):
    me = C.require_user()
    data = data if isinstance(data, dict) else {}
    pb = None
    if data.get("id"):
        pb = C.row_by_id(app_tables.playbooks, data["id"])
        err = C.edit_error(pb, me)
        if err:
            return C.fail(err)
    name = C.text(data.get("name"), 80)
    if len(name) < 2:
        return C.fail("Give the playbook a name.")
    trigger = data.get("trigger")
    if trigger not in TRIGGER_KEYS:
        return C.fail("Pick what should set it off.")
    site = None
    if data.get("site_id"):
        site = C.row_by_id(app_tables.sites, data["site_id"])
        owner = pb["owner"] if pb is not None else me
        if site is None or site["owner"] != owner:
            return C.fail("Pick one of your own sites.")
    actions, err = clean_actions(data.get("actions"))
    if err:
        return C.fail(err)
    fields = dict(name=name, trigger=trigger, site=site, actions=actions, enabled=data.get("enabled") is not False)
    if pb is None:
        if len(app_tables.playbooks.search(owner=me)) >= MAX_PLAYBOOKS:
            return C.fail("You have %d playbooks already. Remove one first." % MAX_PLAYBOOKS)
        pb = app_tables.playbooks.add_row(owner=me, fired=0, last_fired=None, created=C.now(), is_demo=False, **fields)
    else:
        pb.update(**fields)
    return C.ok(playbook=to_dict(pb, me))


@anvil.server.callable(require_user=True)
def set_playbook_enabled(playbook_id, flag):
    me = C.require_user()
    pb = C.row_by_id(app_tables.playbooks, playbook_id)
    err = C.edit_error(pb, me)
    if err:
        return C.fail(err)
    pb["enabled"] = bool(flag)
    return C.ok(playbook=to_dict(pb, me))


@anvil.server.callable(require_user=True)
def delete_playbook(playbook_id):
    me = C.require_user()
    pb = C.row_by_id(app_tables.playbooks, playbook_id)
    if pb is None:
        return C.ok()
    err = C.edit_error(pb, me)
    if err:
        return C.fail(err)
    pb.delete()
    return C.ok()


class _FakeIncident(dict):
    """A pretend incident for "Test run", shaped like a row."""
    def get_id(self):
        return "test"


@anvil.server.callable(require_user=True)
def test_playbook(playbook_id):
    me = C.require_user()
    pb = C.row_by_id(app_tables.playbooks, playbook_id)
    err = C.edit_error(pb, me)
    if err:
        return C.fail(err)
    if C.rate_limited("test_playbook", 10, 3600):
        return C.fail("That's a lot of test runs. Try again in a while.")
    fake = _FakeIncident(owner=pb["owner"], site=pb["site"], heartbeat=None, kind="test", severity="test",
                         title="Test run of “%s”" % pb["name"],
                         detail="This is a test from VitalRPA. If you can read it, the robot can reach you.",
                         started=C.now(), resolved=None, resolution=None, notes=[], is_demo=pb["is_demo"])
    results = run_playbook(pb, fake, "test", test=True)
    return C.ok(results=results, playbook=to_dict(pb, me))


def log_for(owners, limit=40):
    rows = []
    for o in owners:
        rows += list(app_tables.actions_log.search(tables.order_by("at", ascending=False), owner=o))
    rows.sort(key=lambda r: C.utc(r["at"]), reverse=True)
    return [{"at": C.iso(r["at"]), "playbook": r["playbook"], "subject": r["subject"], "action": r["action"],
             "target": r["target"], "result": r["result"], "ok": bool(r["ok"])} for r in rows[:limit]]
