"""Status pages: a public page per account (#status/<slug>) that customers can bookmark during an outage.
It shows only what the owner chose: site names, today's state, 90 days of uptime and recent incidents.
Never the URLs' internals, notes, emails or traffic."""
import datetime as dt
import re

import anvil.server
from anvil.tables import app_tables

from . import common as C
from . import DemoData

RESERVED = {"admin", "api", "app", "status", "vitalrpa", "login", "signup", "help", "support", "www", "demo", "test"}
STATE = {"up": "operational", "slow": "degraded", "retrying": "operational", "down": "outage", "paused": "maintenance", "pending": "operational"}


def _sites(page):
    out = []
    for sid in page["site_ids"] or []:
        s = C.row_by_id(app_tables.sites, sid)
        if s is not None and s["owner"] == page["owner"]:
            out.append(s)
    return out


@anvil.server.callable
def get_status_page(slug):
    DemoData.ensure_loaded()
    slug = C.text(slug, 40).lower()
    page = app_tables.status_pages.get(slug=slug) if slug else None
    me = C.me()
    if page is None or not (page["public"] or (me is not None and page["owner"] == me)):
        return C.fail("There's no public status page at this address.")
    if page["is_demo"]:
        DemoData.keep_alive()
    today = C.today()
    rows = []
    for s in _sites(page):
        dailies = {d["day"]: d for d in app_tables.daily.search(site=s) if d["day"] > today - dt.timedelta(days=90)}
        bars, tot, fails = [], 0, 0
        for back in range(89, -1, -1):
            day = today - dt.timedelta(days=back)
            d = dailies.get(day)
            n, f = ((d["checks"] or 0), (d["fails"] or 0)) if d else (0, 0)
            tot += n
            fails += f
            bars.append({"day": day.isoformat(), "pct": None if not n else round(100.0 * (n - f) / n, 2), "fails": f})
        rows.append({"name": s["name"], "state": STATE.get(s["status"] or "pending", "operational"),
                     "uptime": None if not tot else round(100.0 * (tot - fails) / tot, 2), "bars": bars})
    since = C.now() - dt.timedelta(days=14)
    incs = []
    for s in _sites(page):
        for i in app_tables.incidents.search(site=s):
            if C.utc(i["started"]) > since and i["kind"] in ("down", "slow"):
                incs.append({"title": i["title"], "severity": i["severity"], "started": C.iso(i["started"]),
                             "resolved": C.iso(i["resolved"]), "resolution": i["resolution"] or ""})
    incs.sort(key=lambda x: x["started"], reverse=True)
    states = [r["state"] for r in rows]
    overall = "outage" if "outage" in states else "degraded" if "degraded" in states else "maintenance" if "maintenance" in states else "operational"
    return C.ok(page={"title": page["title"], "intro": page["intro"] or "", "slug": page["slug"], "public": bool(page["public"]),
                      "overall": overall, "sites": rows, "incidents": incs[:20], "updated": C.iso(C.now()),
                      "mine": me is not None and page["owner"] == me, "demo": bool(page["is_demo"])})


@anvil.server.callable(require_user=True)
def get_my_status_page():
    me = C.require_user()
    DemoData.ensure_loaded()
    page = app_tables.status_pages.get(owner=me)
    sites = [{"id": s.get_id(), "name": s["name"], "host": s["url"]} for s in app_tables.sites.search(owner=me)]
    base = re.sub(r"[^a-z0-9]+", "-", (C.name_of(me) or "my").lower()).strip("-")[:30] or "my-sites"
    sample = app_tables.status_pages.get(slug="northwind")
    return {"page": None if page is None else {"slug": page["slug"], "title": page["title"], "intro": page["intro"] or "",
                                               "site_ids": list(page["site_ids"] or []), "public": bool(page["public"])},
            "suggest": {"slug": base + "-status", "title": "%s status" % C.name_of(me)}, "sites": sites,
            "sample_slug": sample["slug"] if sample is not None and sample["public"] else None}


@anvil.server.callable(require_user=True)
def save_status_page(data):
    me = C.require_user()
    data = data if isinstance(data, dict) else {}
    slug = C.text(data.get("slug"), 40).lower()
    if not re.match(r"^[a-z0-9][a-z0-9-]{2,39}$", slug) or slug in RESERVED:
        return C.fail("The address needs 3 to 40 letters, digits or dashes (and a few words are reserved).")
    title = C.text(data.get("title"), 80)
    if len(title) < 2:
        return C.fail("Give the page a title.")
    taken = app_tables.status_pages.get(slug=slug)
    page = app_tables.status_pages.get(owner=me)
    if taken is not None and taken != page:
        return C.fail("Someone already uses that address. Try another.")
    mine = {s.get_id() for s in app_tables.sites.search(owner=me)}
    ids = [i for i in (data.get("site_ids") or []) if isinstance(i, str) and i in mine][:50]
    fields = dict(slug=slug, title=title, intro=C.text(data.get("intro"), 400, multiline=True), site_ids=ids, public=bool(data.get("public")))
    if page is None:
        page = app_tables.status_pages.add_row(owner=me, created=C.now(), is_demo=False, **fields)
    else:
        page.update(**fields)
    return C.ok(slug=slug)
