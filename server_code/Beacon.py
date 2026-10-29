"""Beacon: the two public HTTP endpoints the outside world calls.

  /_/api/b?k=SITEKEY&t=v&p=/path&r=referrer-host&w=width&l=load-ms&f=ttfb-ms    a page view (the snippet)
  /_/api/b?k=SITEKEY&t=e&p=/path&m=message&s=source:line                        a JavaScript error (the snippet)
  /_/api/hb?t=TOKEN                                                              a cron job checking in

The snippet (web/pages/site.html, snippet()) sends these with navigator.sendBeacon after the page has
loaded, so it never slows a page down. No cookies: unique visitors are counted with a fingerprint
salted with a secret that changes every day (sha256 of salt + IP + browser), never the IP itself, and
fingerprints are deleted after 2 days (Bots.janitor).
"""
import hashlib

import anvil.server
from anvil.tables import app_tables

from . import common as C

BOT_WORDS = ("bot", "crawl", "spider", "slurp", "headless", "lighthouse", "pingdom", "uptime", "monitor", "preview", "curl", "wget", "python-")
MAX_VIEWS_PER_DAY = 200000
SPIKE_ERRORS_PER_DAY = 50  # the janitor closes the incident on a calmer day
NO_CONTENT = 204


def _params(kw):
    p = dict(getattr(anvil.server.request, "query_params", None) or {})
    p.update({k: v for k, v in kw.items() if isinstance(v, str)})
    return p


def _num(v, lo, hi):
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        return None
    return n if lo <= n <= hi else None


def _device(width):
    w = _num(width, 1, 20000)
    if w is None:
        return "unknown"
    return "phone" if w < 700 else "tablet" if w < 1100 else "desktop"


def _salt(day):
    key = "beacon_salt"
    cur = C.get_setting(key) or {}
    if cur.get("day") != day.isoformat():
        cur = {"day": day.isoformat(), "salt": C.token(24)}
        C.set_setting(key, cur)
    return cur["salt"]


def _visitor(day):
    req = anvil.server.request
    ip = getattr(req, "remote_address", "") or ""
    ua = (getattr(req, "headers", None) or {}).get("user-agent", "")
    return hashlib.sha256(("%s|%s|%s" % (_salt(day), ip, ua)).encode("utf-8")).hexdigest()[:20]


def _is_bot():
    ua = ((getattr(anvil.server.request, "headers", None) or {}).get("user-agent", "") or "").lower()
    return any(w in ua for w in BOT_WORDS)


def _empty():
    return anvil.server.HttpResponse(NO_CONTENT, "", headers={"Cache-Control": "no-store", "Access-Control-Allow-Origin": "*"})


@anvil.server.http_endpoint("/b", methods=["GET", "POST"], enable_cors=True)
def beacon(**kw):
    p = _params(kw)
    try:
        record(p, check_bot=p.get("x") != "1")  # x=1: the app's own "Send a test beacon" button
    except Exception as e:  # noqa: BLE001 - a beacon never errors back at a visitor's browser
        print("beacon failed: %r" % e)
    return _empty()


def record(p, at=None, visitor=None, check_bot=True):
    """Store one beacon hit. Returns what happened (for tests): 'view', 'error', or why it was ignored."""
    site = app_tables.sites.get(site_key=C.text(p.get("k"), 40)) if p.get("k") else None
    if site is None:
        return "unknown site"
    if check_bot and _is_bot():
        return "bot"
    at = at or C.now()
    day = at.date()
    path = C.text(p.get("p") or "/", 160) or "/"
    from . import Monitor, Incidents
    d = Monitor.daily_row(site, day)
    if p.get("t") == "e":
        _error(site, d, p, path, at)
        return "error"
    if (d["views"] or 0) >= MAX_VIEWS_PER_DAY:
        return "over the daily cap"
    ref = C.text(p.get("r"), 80).lower()
    host = Monitor.Probe.host_of(site["url"])
    if ref.startswith("www."):
        ref = ref[4:]
    if not ref or ref == host or ref == host.replace("www.", "", 1):
        ref = "(direct)"
    visitor = visitor or _visitor(day)
    new = len(app_tables.visits.search(site=site, day=day, visitor=visitor)) == 0
    if new:
        app_tables.visits.add_row(site=site, day=day, visitor=visitor)
    load, ttfb = _num(p.get("l"), 1, 120000), _num(p.get("f"), 1, 120000)
    hours = list(d["hours"] or [0] * 24)
    hours[at.hour] = (hours[at.hour] or 0) + 1
    d.update(views=(d["views"] or 0) + 1, visitors=(d["visitors"] or 0) + (1 if new else 0),
             load_sum=(d["load_sum"] or 0) + (load or 0), load_n=(d["load_n"] or 0) + (1 if load else 0),
             ttfb_sum=(d["ttfb_sum"] or 0) + (ttfb or 0) if load else (d["ttfb_sum"] or 0),
             pages=C.bump(dict(d["pages"] or {}), path), refs=C.bump(dict(d["refs"] or {}), ref, cap=40),
             devices=C.bump(dict(d["devices"] or {}), _device(p.get("w")), cap=6), hours=hours)
    site["last_beat"] = at
    Incidents.resolve(site=site, kind="silence", how="Visitors are arriving again")
    return "view"


def _error(site, d, p, path, at):
    from . import Incidents
    message = C.text(p.get("m"), 160) or "Script error."
    source = C.text(p.get("s"), 120)
    row = app_tables.jserrors.get(site=site, message=message)
    if row is None:
        if len(app_tables.jserrors.search(site=site)) >= 200:
            return
        app_tables.jserrors.add_row(site=site, message=message, source=source, path=path, count=1, first=at, last=at,
                                    is_demo=bool(site["is_demo"]))
    else:
        row.update(count=(row["count"] or 0) + 1, last=at, source=source or row["source"], path=path)
    d["errors"] = (d["errors"] or 0) + 1
    if d["errors"] >= SPIKE_ERRORS_PER_DAY:
        Incidents.open_incident(site["owner"], "jserrors", "%s: JavaScript errors are piling up" % site["name"],
                                "%d errors today. Latest: %s" % (d["errors"], message), site=site)


@anvil.server.http_endpoint("/hb", methods=["GET", "POST", "HEAD"], enable_cors=True)
def heartbeat(**kw):
    p = _params(kw)
    hb = app_tables.heartbeats.get(token=C.text(p.get("t"), 40)) if p.get("t") else None
    if hb is None:
        return anvil.server.HttpResponse(404, "Unknown heartbeat token\n", headers={"Content-Type": "text/plain"})
    ping(hb)
    return anvil.server.HttpResponse(200, "OK %s\n" % hb["name"], headers={"Content-Type": "text/plain", "Cache-Control": "no-store"})


def ping(hb, at=None):
    from . import Incidents
    at = at or C.now()
    hb.update(last_ping=at, pings=(hb["pings"] or 0) + 1, status="paused" if hb["status"] == "paused" else "up")
    Incidents.resolve(heartbeat=hb, kind="heartbeat", how="Checked in at %s UTC" % at.strftime("%H:%M"))
