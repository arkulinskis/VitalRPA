"""Server tests against the strict mock of Anvil (tools/testing/mock).

    python tools/testing/test_server.py          -> prints ALL OK, or the first failure

call(name, ...) runs a server function the way the browser does: by name, with require_user enforced,
and the reply must be JSON (a datetime or a row in a reply fails here, like it would break the page).
Add tests for every new server function: the happy path, bad input, and someone who isn't allowed.
"""
import datetime as dt
import importlib
import json
import os
import pathlib
import shutil
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
_tmp = pathlib.Path(tempfile.mkdtemp())
shutil.copytree(PROJECT / "server_code", _tmp / "app")
(_tmp / "app" / "__init__.py").write_text("")
os.environ["ANVIL_APP_YAML"] = str(PROJECT / "anvil.yaml")  # the mock's tables follow the app's own schema
sys.path[:0] = [str(HERE / "mock"), str(_tmp)]
import anvil.server  # noqa: E402
import anvil.users  # noqa: E402
from anvil.tables import app_tables as T  # noqa: E402

M = {p.stem: importlib.import_module("app." + p.stem) for p in sorted((PROJECT / "server_code").glob("*.py"))}
now = dt.datetime.now(dt.timezone.utc)


def call(name, *args):
    r = anvil.server.call(name, *args)
    json.dumps(r)  # strict: must be JSON-able
    return r


def as_user(row):
    anvil.users.CURRENT[0] = row
    anvil.server.session.use(row.get_id() if row is not None else None)


def denied(name, *args):
    try:
        call(name, *args)
    except anvil.server.PermissionDenied:
        return True
    return False


def ok(r, msg=""):
    assert isinstance(r, dict) and r.get("ok"), (msg, r)
    return r


def bad(r, msg=""):
    assert isinstance(r, dict) and r.get("ok") is False and r.get("error"), (msg, r)
    return r


def person(email, name=None, **kw):
    return T.users.add_row(email=email, enabled=True, signed_up=now, display_name=name, **kw)


# ---------------------------------------------------------------------------------- accounts
admin = person("arkulinskis@gmail.com", "The Admin")
ana = person("ana@example.com", "Ana")
bob = person("bob@example.com")

as_user(None)
assert call("get_me") is None
assert denied("update_profile", "X")
as_user(admin)
assert call("get_me")["is_admin"] is True, "ADMIN_EMAILS become admins on first sign-in"
as_user(ana)
me = call("get_me")
assert me["name"] == "Ana" and me["is_admin"] is False
assert ana["last_seen"] is not None
as_user(bob)
assert call("get_me")["name"] == "Bob", "a name comes from the email when none is set"
bad(call("update_profile", " x "))
assert ok(call("update_profile", "  Bob   Stone "))["me"]["name"] == "Bob Stone"

# ---------------------------------------------------------------------------------- feedback
as_user(None)
bad(call("submit_feedback", "bug", "hi"))
ok(call("submit_feedback", "bug", "The button is broken", "guest@example.com", {"page": "#home", "evil": "x" * 9999}))
fb = T.feedback.search()[0]
assert fb["name"] == "Guest" and fb["email"] == "guest@example.com" and "evil" not in fb["context"] and fb["status"] == "new"
for i in range(4):
    ok(call("submit_feedback", "idea", "Idea number %d" % i))
bad(call("submit_feedback", "idea", "One too many this hour"), "rate limit")
as_user(ana)
ok(call("submit_feedback", "nonsense-kind", "Signed-in feedback"))
assert T.feedback.get(message="Signed-in feedback")["kind"] == "other"
assert denied("list_feedback")
as_user(admin)
lst = call("list_feedback")
assert lst["counts"]["new"] == 6 and len(lst["items"]) == 6
fid = lst["items"][0]["id"]
ok(call("set_feedback_status", fid, "done", "Fixed it"))
assert call("list_feedback", "done")["items"][0]["note"] == "Fixed it"
bad(call("set_feedback_status", fid, "weird"))
bad(call("set_feedback_status", "nope", "done"))
ok(call("delete_feedback", fid))
assert len(call("list_feedback")["items"]) == 5

# ---------------------------------------------------------------------------------- admin
as_user(ana)
for fn, args in [("admin_overview", ()), ("list_users", ()), ("set_admin", (bob.get_id(), True)), ("demo_load", ()), ("demo_remove", ())]:
    assert denied(fn, *args), fn
as_user(admin)
ov = call("admin_overview")
assert ov["users"] == 3 and ov["admins"] == 1 and ov["feedback_new"] == 5
assert len(call("list_users")["users"]) == 3 and len(call("list_users", "bob")["users"]) == 1
ok(call("set_admin", bob.get_id(), True))
assert bob["is_admin"] is True
bad(call("set_admin", admin.get_id(), False), "can't remove your own admin")
ok(call("set_enabled", bob.get_id(), False))
assert bob["enabled"] is False
bad(call("set_enabled", admin.get_id(), False))
ok(call("set_enabled", bob.get_id(), True))
ok(call("set_admin", bob.get_id(), False))
assert bob["is_admin"] is False

# ---------------------------------------------------------------------------------- VitalRPA: no network in tests
import anvil.email as E  # noqa: E402
import anvil.http as H  # noqa: E402
import anvil.tables.query  # noqa: E402
P, MON, B, BOTS, D = M["Probe"], M["Monitor"], M["Beacon"], M["Bots"], M["DemoData"]
HDRS = {k: True for k, _, _ in P.SEC_HEADERS}
HDRS["https"] = True
NEXT = {"code": 200, "ms": 180, "error": None, "bytes": 5000, "server": "nginx", "redirects": 0, "headers": HDRS, "kw": True}


def fake_http(url, keyword=None, timeout=12):
    r = dict(NEXT)
    r["final_url"] = url
    r["keyword_found"] = (r.pop("kw") if keyword else None)
    return r


P.http_check = fake_http
CERT = {"days": 200}
P.cert_check = lambda host, timeout=8: {"expires": dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=CERT["days"]), "issuer": "Test CA", "error": None}
P.domain_check = lambda host, timeout=12: {"domain": host, "expires": dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=300), "error": None}


def set_next(**kw):
    NEXT.clear()
    NEXT.update({"code": 200, "ms": 180, "error": None, "bytes": 5000, "server": "nginx", "redirects": 0, "headers": HDRS, "kw": True})
    NEXT.update(kw)


def visitor_request(ua="Mozilla/5.0 (Windows NT 10.0) Test", ip="203.0.113.7"):
    anvil.server.request.headers = {"user-agent": ua}
    anvil.server.request.remote_address = ip
    anvil.server.request.query_params = {}


# ---------------------------------------------------------------------------------- URL rules
assert P.normalize_url("example.com") == "https://example.com/"
assert P.normalize_url("http://Example.com/a?b=1#x") == "http://example.com/a?b=1"
for badurl in ("localhost", "http://10.0.0.1/", "http://192.168.1.4", "ftp://example.com", "not a url", "https://intranet.local/", "https://user:pw@example.com"):
    assert P.normalize_url(badurl) is None, badurl
assert P.registrable_domain("shop.example.co.uk") == "example.co.uk" and P.registrable_domain("a.b.example.com") == "example.com"

# ---------------------------------------------------------------------------------- the sample fleet
as_user(None)
assert denied("get_console")
as_user(ana)
con = call("get_console")
assert D.state() == "loaded", "demo loads on first visit"
assert con["mode"] == "sample" and len(con["sites"]) == len(D.SITES) and con["has_own"] is False
assert con["totals"]["down"] >= 1 and con["totals"]["incidents"] >= 5 and con["feed"], con["totals"]
assert con["sites"][0]["status"] == "down", "down sites come first"
assert all(len(x["cells"]) == 24 for x in con["sites"])
demo_site = con["sites"][0]
assert not demo_site["can_edit"]
bad(call("update_site", demo_site["id"], {"url": "https://x.example.com"}), "the sample fleet is read-only")
bad(call("delete_site", demo_site["id"]))
detail = ok(call("get_site", demo_site["id"]))["site"]
assert detail["site_key"] == "vr_xxxxxxxxxx", "the sample's real keys stay hidden"
assert len(detail["uptime90"]) == 90 and detail["traffic"]["days"] and detail["security"]["items"]
ok(call("check_now", demo_site["id"]), "sample sites can be checked (simulated)")
shop = [x for x in con["sites"] if x["name"] == "Northwind Coffee shop"][0]
sd = ok(call("get_site", shop["id"]))["site"]
assert sd["traffic"]["views7"] > 1000 and sd["traffic"]["pages"][0]["name"] == "/" and sd["jserrors"], "sample traffic + errors"
bad(call("get_site", "nope"))
inc = call("list_incidents", "open")
assert inc["mode"] == "sample" and inc["open"] >= 6
assert bad(call("ack_incident", inc["incidents"][0]["id"]))
bots = call("get_bots")
assert bots["mode"] == "sample" and len(bots["playbooks"]) == len(D.PLAYBOOKS) and len(bots["heartbeats"]) == len(D.HEARTBEATS)
assert bots["log"] and all(h["token"] is None for h in bots["heartbeats"]), "sample heartbeat tokens stay hidden"
bad(call("delete_playbook", bots["playbooks"][0]["id"]))
bad(call("ping_heartbeat_now", bots["heartbeats"][0]["id"]))

# ---------------------------------------------------------------------------------- adding a site, checks, incidents, playbooks
for badsite in ({"url": ""}, {"url": "localhost"}, {"url": "example.com", "interval_min": 7}, {"url": "example.com", "slow_ms": 10},
                {"url": "example.com", "expect_status": 999}, {"url": "example.com", "quiet_hours": 500}):
    bad(call("add_site", badsite), badsite)
sid = ok(call("add_site", {"url": "ana-shop.example.com", "name": "Ana's shop", "interval_min": 60, "tags": "Shop, client A, shop"}))["site_id"]
bad(call("add_site", {"url": "https://ana-shop.example.com/"}), "no duplicates")
site_row = T.sites.get_by_id(sid)
assert site_row["tags"] == ["shop", "client-a"] and site_row["status"] == "pending" and site_row["site_key"].startswith("vr_")
assert len(T.playbooks.search(owner=ana)) == 2, "a new fleet gets the default email playbooks"
con = call("get_console")
assert con["mode"] == "mine" and len(con["sites"]) == 1 and con["sites"][0]["can_edit"]
assert call("get_console", True)["mode"] == "sample", "the sample can still be opened"
r = ok(call("check_now", sid))["result"]
assert r["state"] == "up" and site_row["status"] == "up" and site_row["last_ms"] == 180
mail0 = len(E.OUTBOX)
set_next(code=503, ms=40)
r = ok(call("check_now", sid))["result"]
assert site_row["status"] == "retrying" and not T.incidents.search(site=site_row), "one failure is retried before alarming"
ok(call("check_now", sid))
assert site_row["status"] == "down"
open_inc = T.incidents.search(site=site_row, resolved=None)
assert len(open_inc) == 1 and open_inc[0]["kind"] == "down" and "503" in open_inc[0]["detail"]
assert len(E.OUTBOX) == mail0 + 1 and E.OUTBOX[-1]["to"] == "ana@example.com" and "CRITICAL" in E.OUTBOX[-1]["subject"]
ok(call("check_now", sid))
assert len(T.incidents.search(site=site_row)) == 1, "still down: no duplicate incident"
set_next()
ok(call("check_now", sid))
assert site_row["status"] == "up" and T.incidents.search(site=site_row)[0]["resolved"] is not None
assert "RECOVERED" in E.OUTBOX[-1]["subject"], "the default playbook says it's fixed"
set_next(ms=5000)
for i in range(3):
    ok(call("check_now", sid))
assert site_row["status"] == "slow" and T.incidents.get(site=site_row, kind="slow", resolved=None) is not None
set_next()
ok(call("check_now", sid))
assert T.incidents.get(site=site_row, kind="slow", resolved=None) is None, "fast again closes the slow incident"
ok(call("update_site", sid, {"url": "ana-shop.example.com", "name": "Ana's shop", "interval_min": 15, "keyword": "Buy now", "slow_ms": 2000}))
set_next(kw=False)
ok(call("check_now", sid))
assert site_row["last_error"] and "Buy now" in site_row["last_error"], "a missing keyword fails the check"
set_next()
ok(call("check_now", sid))
CERT["days"] = 10
ok(call("inspect_now", sid))
assert T.incidents.get(site=site_row, kind="ssl", resolved=None)["severity"] == "warning"
CERT["days"] = 80
ok(call("inspect_now", sid))
assert T.incidents.get(site=site_row, kind="ssl", resolved=None) is None

# someone else's site
as_user(bob)
assert call("get_console")["mode"] == "sample", "bob sees the sample, never Ana's sites"
bad(call("get_site", sid))
bad(call("check_now", sid))
bad(call("update_site", sid, {"url": "evil.example.com"}))
bad(call("delete_site", sid))
bad(call("set_site_paused", sid, True))
bad(call("rotate_site_key", sid))
as_user(ana)

# ---------------------------------------------------------------------------------- the beacon
key = site_row["site_key"]
visitor_request()
resp = B.beacon(k=key, t="v", p="/pricing", r="www.google.com", w="390", l="1200", f="210")
assert resp.status == 204
B.beacon(k=key, t="v", p="/", r="ana-shop.example.com", w="1440", l="900", f="150")
day = MON.daily_row(site_row)
assert day["views"] == 2 and day["visitors"] == 1, "same browser, same day = one visitor"
assert day["refs"] == {"google.com": 1, "(direct)": 1} and day["devices"] == {"phone": 1, "desktop": 1} and day["pages"]["/pricing"] == 1
visitor_request(ip="198.51.100.9")
B.beacon(k=key, t="v", p="/")
assert day["visitors"] == 2
visitor_request(ua="Mozilla/5.0 (compatible; Googlebot/2.1)")
B.beacon(k=key, t="v", p="/")
B.beacon(k="vr_unknown", t="v", p="/")
assert day["views"] == 3, "bots and unknown keys don't count"
B.beacon(k=key, t="v", p="/", x="1")
assert day["views"] == 4, "the app's own test beacon counts even from a headless browser"
visitor_request()
assert site_row["last_beat"] is not None
B.beacon(k=key, t="e", p="/cart", m="TypeError: x is undefined", s="/app.js:10")
B.beacon(k=key, t="e", p="/cart", m="TypeError: x is undefined", s="/app.js:10")
err = T.jserrors.get(site=site_row)
assert err["count"] == 2 and day["errors"] == 2
for i in range(B.SPIKE_ERRORS_PER_DAY):
    B.record({"k": key, "t": "e", "m": "Boom %d" % (i % 3)}, check_bot=False)
assert T.incidents.get(site=site_row, kind="jserrors", resolved=None) is not None, "an error flood opens an incident"
sd = ok(call("get_site", sid))["site"]
assert sd["traffic"]["today"]["views"] == 4 and sd["traffic"]["load_ms"] and sd["site_key"] == key and sd["jserrors"]
assert ok(call("beacon_status", sid))["state"] == "live"
ok(call("clear_js_errors", sid))
assert not T.jserrors.search(site=site_row) and T.incidents.get(site=site_row, kind="jserrors", resolved=None) is None
old_key = key
assert ok(call("rotate_site_key", sid))["site_key"] != old_key

# silence: the beacon used to hear visitors and stopped
site_row.update(quiet_hours=24, last_beat=now - dt.timedelta(hours=30))
BOTS.sweep_silence()
assert T.incidents.get(site=site_row, kind="silence", resolved=None) is not None
B.record({"k": site_row["site_key"], "t": "v", "p": "/"}, visitor="v1")
assert T.incidents.get(site=site_row, kind="silence", resolved=None) is None, "a new visitor ends the silence"

# ---------------------------------------------------------------------------------- heartbeats
bad(call("save_heartbeat", {"name": "Backup", "period_min": 7}))
bad(call("save_heartbeat", {"name": "", "period_min": 60}))
hb = ok(call("save_heartbeat", {"name": "Nightly backup", "period_min": 1440, "grace_min": 30}))["heartbeat"]
assert hb["token"].startswith("hb_") and hb["status"] == "waiting"
res = B.heartbeat(t=hb["token"])
hb_row = T.heartbeats.get_by_id(hb["id"])
assert res.status == 200 and hb_row["status"] == "up" and hb_row["pings"] == 1
assert B.heartbeat(t="nope").status == 404
hb_row["last_ping"] = now - dt.timedelta(hours=30)
BOTS.sweep_heartbeats()
assert hb_row["status"] == "late" and T.incidents.get(heartbeat=hb_row, resolved=None) is not None
ok(call("ping_heartbeat_now", hb["id"]))
assert hb_row["status"] == "up" and T.incidents.get(heartbeat=hb_row, resolved=None) is None
ok(call("set_heartbeat_paused", hb["id"], True))
assert hb_row["status"] == "paused"
ok(call("set_heartbeat_paused", hb["id"], False))
as_user(bob)
bad(call("delete_heartbeat", hb["id"]))
bad(call("save_heartbeat", {"id": hb["id"], "name": "mine now", "period_min": 60}))
as_user(ana)

# ---------------------------------------------------------------------------------- playbooks
bad(call("save_playbook", {"name": "x", "trigger": "down", "actions": [{"type": "email"}]}))
bad(call("save_playbook", {"name": "Hook", "trigger": "nope", "actions": [{"type": "email"}]}))
bad(call("save_playbook", {"name": "Hook", "trigger": "down", "actions": []}))
bad(call("save_playbook", {"name": "Hook", "trigger": "down", "actions": [{"type": "webhook", "url": "http://hooks.example.com/x"}]}))
bad(call("save_playbook", {"name": "Hook", "trigger": "down", "actions": [{"type": "email", "to": "not-an-email"}]}))
bad(call("save_playbook", {"name": "Hook", "trigger": "down", "site_id": demo_site["id"], "actions": [{"type": "recheck"}]}), "only own sites")
pb = ok(call("save_playbook", {"name": "Slack on-call", "trigger": "down", "site_id": sid,
                               "actions": [{"type": "webhook", "url": "https://hooks.example.com/T1/B2"}, {"type": "recheck"}]}))["playbook"]
assert pb["site_name"] == "Ana's shop" and len(pb["actions"]) == 2
H.REPLIES["https://hooks.example.com/"] = {"ok": True}
H.CALLS.clear()
t = ok(call("test_playbook", pb["id"]))
assert H.CALLS and H.CALLS[0]["method"] == "POST" and "Test run" in H.CALLS[0]["data"], "the test run calls the webhook"
assert t["results"][0]["ok"]
H.CALLS.clear()
set_next(code=500)
ok(call("check_now", sid))
ok(call("check_now", sid))
assert H.CALLS, "going down fires the site's playbook"
down = T.incidents.get(site=site_row, kind="down", resolved=None)
assert any("recheck" in (n["text"] or "").lower() for n in down["notes"]), "the recheck action writes a note"
set_next()
H.REPLIES["https://hooks.example.com/"] = H.HttpError(500, "nope")
ok(call("test_playbook", pb["id"]))
assert T.actions_log.search(owner=ana, ok=False), "a failing webhook is logged, not raised"
ok(call("set_playbook_enabled", pb["id"], False))
as_user(bob)
bad(call("set_playbook_enabled", pb["id"], True))
bad(call("test_playbook", pb["id"]))
as_user(ana)
bots = call("get_bots")
assert bots["mode"] == "mine" and any(p["name"] == "Slack on-call" for p in bots["playbooks"]) and bots["log"] and bots["heartbeats"][0]["token"]
ok(call("delete_playbook", pb["id"]))

# ---------------------------------------------------------------------------------- incidents by hand
lst = call("list_incidents", "open")
assert lst["mode"] == "mine" and lst["open"] >= 1
iid = lst["incidents"][0]["id"]
as_user(bob)
bad(call("ack_incident", iid))
bad(call("add_incident_note", iid, "hi"))
as_user(ana)
acked = ok(call("ack_incident", iid))["incident"]
assert acked["acked"]
bad(call("add_incident_note", iid, " "))
assert len(ok(call("add_incident_note", iid, "Restarted the app server."))["incident"]["notes"]) == len(acked["notes"]) + 1
assert ok(call("resolve_incident", iid, "Fixed"))["incident"]["resolved"]
assert len(call("list_incidents", "all")["incidents"]) >= len(call("list_incidents", "resolved")["incidents"])

# ---------------------------------------------------------------------------------- status pages
for badpage in ({"slug": "ab", "title": "X"}, {"slug": "admin", "title": "Status"}, {"slug": "northwind", "title": "Mine"}, {"slug": "ana-status", "title": ""}):
    bad(call("save_status_page", badpage), badpage)
ok(call("save_status_page", {"slug": "ana-status", "title": "Ana's status", "intro": "Hi", "site_ids": [sid, demo_site["id"]], "public": False}))
assert T.status_pages.get(slug="ana-status")["site_ids"] == [sid], "only own sites go on a status page"
assert call("get_my_status_page")["page"]["slug"] == "ana-status"
as_user(None)
bad(call("get_status_page", "ana-status"), "private pages stay private")
sp = ok(call("get_status_page", "northwind"))["page"]
assert sp["overall"] in ("operational", "degraded", "outage") and len(sp["sites"]) == 3 and len(sp["sites"][0]["bars"]) == 90
assert "url" not in json.dumps(sp["sites"]), "status pages never show addresses"
as_user(ana)
ok(call("save_status_page", {"slug": "ana-status", "title": "Ana's status", "site_ids": [sid], "public": True}))
as_user(None)
assert ok(call("get_status_page", "ana-status"))["page"]["sites"][0]["name"] == "Ana's shop"
bad(call("get_status_page", "no-such-page"))

# ---------------------------------------------------------------------------------- alerts + robots
as_user(ana)
bad(call("save_alerts", "nope", True))
assert ok(call("save_alerts", "oncall@example.com", True))["alerts"]["digest_on"]
assert call("get_alerts")["alert_email"] == "oncall@example.com"
mail0 = len(E.OUTBOX)
BOTS.digest()
assert len(E.OUTBOX) == mail0 + 1 and E.OUTBOX[-1]["to"] == "oncall@example.com" and "Ana's shop" in E.OUTBOX[-1]["text"]
site_row["next_check"] = now - dt.timedelta(minutes=1)
runs = BOTS.bot_tick()
assert [r["bot"] for r in runs] == ["uptime", "heartbeat", "silence"] and all(r["ok"] for r in runs), runs
assert all(r["ok"] for r in BOTS.bot_daily())
T.checks.add_row(site=site_row, at=now - dt.timedelta(days=40), ok=True, slow=False, code=200, ms=1, error=None, source="robot", is_demo=False)
BOTS.janitor()
assert not T.checks.search(site=site_row, at=anvil.tables.query.less_than(now - dt.timedelta(days=31))), "the janitor deletes old checks"
for fn, args in [("admin_bots", ()), ("admin_run_bot", ("uptime",)), ("admin_set_bots_paused", (True,))]:
    assert denied(fn, *args), fn
as_user(admin)
assert call("admin_bots")["stats"]["sites"] >= 1
ok(call("admin_run_bot", "uptime"))
bad(call("admin_run_bot", "nope"))
ok(call("admin_set_bots_paused", True))
assert BOTS.bot_tick() == "paused"
ok(call("admin_set_bots_paused", False))
assert call("admin_overview")["sites"] == 1

# ---------------------------------------------------------------------------------- demo data on / off, deleting a site
ok(call("demo_remove"))
assert D.state() == "removed" and not T.sites.search(is_demo=True) and not T.users.search(is_demo=True)
assert T.sites.get_by_id(sid) is not None, "removing the demo keeps real sites"
as_user(bob)
assert call("get_console")["mode"] == "mine" and call("get_console")["sites"] == [], "no sample once it's removed"
as_user(admin)
ok(call("demo_load"))
ok(call("demo_load"))
assert len(T.sites.search(is_demo=True)) == len(D.SITES), "reloading replaces the demo instead of doubling it"
T.app_settings.get(key="demo_alive")["value"] = (now - dt.timedelta(hours=3)).isoformat()
D.keep_alive()
as_user(ana)
ok(call("delete_site", sid))
assert not [x for x in T.sites.search() if x.get_id() == sid] and not T.checks.search(site=site_row) and not T.daily.search(site=site_row)
assert call("get_my_status_page")["page"]["site_ids"] == []

# ---------------------------------------------------------------------------------- Privacy & Terms
if "legal_server" in M:
    as_user(ana)
    st = call("legal_state")
    assert st["signedIn"] and st["accepted_version"] is None
    ok(call("legal_accept", st["version"], "signup"))
    assert ana["legal_source"] == "signup" and call("legal_state")["accepted_version"] == st["version"]

# ---------------------------------------------------------------------------------- every callable is covered by a permission check
# A callable that changes data without require_user / a C.require_* check is a security hole. List the public ones here.
PUBLIC = {"session_ping", "get_me", "submit_feedback", "get_status_page", "legal_state", "legal_accept"}
for name, (f, need) in sorted(anvil.server.CALLABLES.items()):
    if name in PUBLIC:
        continue
    assert need, "%s is callable by anyone: add require_user=True (or list it in PUBLIC in test_server.py)" % name

print("ALL OK (%d server functions)" % len(anvil.server.CALLABLES))
