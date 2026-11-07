"""The sample fleet, so the app never looks empty: Mara Lindqvist (a demo account) runs ops for Northwind
Coffee and a few client sites, all on the reserved .example domain (clearly fictional, never online).

People who have no sites of their own yet see this fleet read-only (common.scope). It is loaded the first
time anyone opens the app (ensure_loaded), removed or reloaded in Admin -> Demo data (removal is
remembered). Demo sites never touch the network: the robots simulate them from SITES (Probe.simulate),
and keep_alive() fills the gap when the scheduler hasn't run (dev server, a quiet night), so the sample
always looks current. Every demo row has is_demo=True, so remove() deletes exactly what load() added.
"""
import datetime as dt
import math
import random

from anvil.tables import app_tables

from . import common as C

DEMO_USERS = [("Mara Lindqvist", C.DEMO_OWNER_EMAIL), ("Theo Martin", "theo.demo@example.com")]

# One profile per demo site: what the simulated robots see. views = page views on a weekday.
SITES: list = [
    dict(key="shop", name="Northwind Coffee shop", url="https://shop.northwind-coffee.example/", tags=["northwind", "shop"],
         interval=15, base=185, jitter=45, views=1450, load=1850, headers=5, bytes=91000, server="nginx", issuer="Let's Encrypt",
         ssl_days=63, domain_days=212, quiet=6, errors=6, keyword="Add to cart"),
    dict(key="www", name="Northwind Coffee website", url="https://www.northwind-coffee.example/", tags=["northwind", "marketing"],
         interval=60, base=240, jitter=50, views=820, load=1400, headers=4, bytes=64000, server="cloudflare", issuer="Google Trust Services",
         ssl_days=71, domain_days=212, quiet=12),
    dict(key="dental", name="Harbor Dental Clinic", url="https://harbordental.example/", tags=["clients"], interval=30, base=430,
         jitter=90, views=150, load=2600, headers=2, bytes=148000, server="Apache", issuer="Sectigo", ssl_days=118, domain_days=330,
         quiet=24, down=True, down_h=3, code=502),
    dict(key="realty", name="Pinecrest Realty", url="https://pinecrest-realty.example/listings", tags=["clients"], interval=60,
         base=2750, jitter=300, slow_ms=2000, views=320, load=4800, headers=3, bytes=412000, server="Apache", issuer="Let's Encrypt",
         ssl_days=40, domain_days=150, quiet=24, errors=2),
    dict(key="api", name="Atlas Freight API", url="https://api.atlasfreight.example/health", tags=["clients", "api"], interval=15,
         base=92, jitter=18, headers=6, bytes=180, server="envoy", issuer="Amazon", ssl_days=255, domain_days=600,
         keyword='"status":"ok"', views=0),
    dict(key="bakery", name="Little Fern Bakery", url="https://littlefern.example/", tags=["clients"], interval=60, base=310,
         jitter=70, views=95, load=1700, headers=1, bytes=83000, server="LiteSpeed", issuer="Let's Encrypt", ssl_days=9,
         domain_days=95, quiet=48),
    dict(key="law", name="Maple & Co. Law", url="https://maplelaw.example/", tags=["clients"], interval=60, base=360, jitter=60,
         views=70, load=1500, headers=3, bytes=71000, server="nginx", issuer="DigiCert", ssl_days=190, domain_days=21, quiet=24,
         silent_h=30),
    dict(key="staging", name="Northwind staging", url="https://staging.northwind-coffee.example/", tags=["northwind"], interval=60,
         base=520, jitter=80, views=0, headers=2, bytes=91000, server="nginx", issuer="Let's Encrypt", ssl_days=50, domain_days=212,
         paused=True),
]
_BY_URL = {p["url"]: p for p in SITES}

PAGES = {
    "shop": [("/", 30), ("/coffee/ethiopia-yirgacheffe", 13), ("/coffee/colombia-huila", 9), ("/cart", 11), ("/checkout", 6),
             ("/subscriptions", 7), ("/brewing-guides/v60", 5), ("/account", 4), ("/coffee/decaf-swiss-water", 3)],
    "www": [("/", 40), ("/our-cafes", 18), ("/menu", 15), ("/about", 8), ("/careers", 6), ("/wholesale", 5), ("/blog/cold-brew-at-home", 8)],
    "dental": [("/", 45), ("/book", 20), ("/services/cleaning", 12), ("/team", 10), ("/contact", 13)],
    "realty": [("/listings", 40), ("/listings/48-pinecrest-ave", 14), ("/listings/9-lakeview-rd", 11), ("/sell", 9), ("/agents", 6), ("/", 20)],
    "bakery": [("/", 50), ("/menu", 22), ("/order-a-cake", 18), ("/visit", 10)],
    "law": [("/", 42), ("/practice/family", 18), ("/practice/real-estate", 14), ("/team", 12), ("/contact", 14)],
}
REFS = [("(direct)", 38), ("google.com", 34), ("instagram.com", 8), ("bing.com", 5), ("duckduckgo.com", 4), ("facebook.com", 4),
        ("newsletter.northwind-coffee.example", 4), ("maps.google.com", 3)]
DEVICES = [("phone", 58), ("desktop", 35), ("tablet", 7)]
CURVE = [1, .6, .4, .3, .3, .5, 1, 2, 3.2, 4, 4.4, 4.6, 5, 5.2, 5.4, 5.1, 4.8, 4.6, 4.9, 5.2, 4.6, 3.6, 2.4, 1.5]
WEEKDAY = [1.0, 1.02, .98, 1.04, .94, .72, .66]
DAYS = 92

JS_ERRORS = [
    ("shop", "TypeError: Cannot read properties of undefined (reading 'price')", "/assets/cart.min.js:1:4211", "/cart", 37, 9),
    ("shop", "ResizeObserver loop completed with undelivered notifications.", "", "/coffee/ethiopia-yirgacheffe", 112, 1),
    ("shop", "Uncaught (in promise) Error: Network request failed", "/assets/subscriptions.js:88:17", "/subscriptions", 6, 30),
    ("realty", "ReferenceError: mapboxgl is not defined", "/listings:212:9", "/listings/48-pinecrest-ave", 9, 140),
]

# kind, site key, opened N hours ago, lasted minutes (None = still open), severity, title, detail, resolution
INCIDENTS = [
    ("down", "dental", 3, None, "critical", "Harbor Dental Clinic is down", "HTTP 502 Bad Gateway", None),
    ("slow", "realty", 5, None, "warning", "Pinecrest Realty is slow", "5 slow checks in a row (latest 2,870 ms)", None),
    ("ssl", "bakery", 26, None, "warning", "Little Fern Bakery: certificate expires in 9 days",
     "Issued by Let's Encrypt. Renew it, or check that auto-renewal still works.", None),
    ("silence", "law", 6, None, "warning", "Maple & Co. Law: no visitors for 24 hours",
     "The beacon last heard from a visitor 30 hours ago. Was the snippet removed, or is the site broken for real visitors?", None),
    ("domain", "law", 50, None, "warning", "Maple & Co. Law: domain expires in 21 days", "maplelaw.example must be renewed at the registrar.", None),
    ("jserrors", "shop", 52, 610, "warning", "Northwind Coffee shop: JavaScript errors are piling up",
     "57 errors today. Latest: TypeError: Cannot read properties of undefined (reading 'price')", "A calmer day: 4 errors so far"),
    ("slow", "shop", 75, 41, "warning", "Northwind Coffee shop is slow", "3 slow checks in a row (latest 4,120 ms)", "Fast again: 191 ms"),
    ("down", "dental", 150, 14, "critical", "Harbor Dental Clinic is down", "Timed out after 12 s", "Back up: HTTP 200 in 512 ms"),
    ("down", "www", 290, 6, "critical", "Northwind Coffee website is down", "HTTP 503 Service Unavailable", "Back up: HTTP 200 in 233 ms"),
    ("down", "api", 482, 9, "critical", "Atlas Freight API is down", "Connection refused", "Back up: HTTP 200 in 88 ms"),
    ("ssl", "www", 700, 2900, "warning", "Northwind Coffee website: certificate expires in 12 days",
     "Issued by Google Trust Services.", "Certificate valid for 89 days"),
]

# name, trigger, site key or None, actions, enabled, fired
PLAYBOOKS = [
    ("Page the on-call when a site goes down", "down", None,
     [{"type": "recheck"}, {"type": "email", "to": "oncall@northwind-coffee.example"},
      {"type": "webhook", "url": "https://hooks.slack.example/services/T0NW/B0OPS/demo"}], True, 9),
    ("Second opinion on slow pages", "slow", None, [{"type": "recheck"}], True, 4),
    ("Certificate reminders", "ssl", None, [{"type": "email", "to": "webmaster@northwind-coffee.example"}], True, 3),
    ("Domain renewals to billing", "domain", None, [{"type": "email", "to": "billing@northwind-coffee.example"}], True, 1),
    ("Tell #web when visitors vanish", "silence", None, [{"type": "webhook", "url": "https://hooks.slack.example/services/T0NW/B0WEB/demo"}], True, 2),
    ("Shop errors to the developers", "jserrors", "shop", [{"type": "email", "to": "dev@northwind-coffee.example"}], True, 1),
    ("All-clear in Teams", "recovered", None, [{"type": "webhook", "url": "https://outlook.office.example/webhook/demo"}], False, 6),
]

# name, period min, grace min, last ping hours ago (None: daily at 02:14), status, pings so far
HEARTBEATS = [
    ("Nightly database backup", 1440, 60, None, "up", 412),
    ("Inventory sync (cron)", 60, 10, 3.2, "late", 8121),
    ("Search index rebuild", 360, 30, 1.1, "up", 1390),
    ("Weekly invoice mailer", 10080, 120, 74, "up", 58),
]

# Tables that hold demo rows (each has an is_demo column). Children before parents.
DEMO_TABLES = ["actions_log", "bot_runs", "jserrors", "checks", "daily", "incidents", "playbooks", "status_pages", "heartbeats", "sites"]


def profile(site):
    return _BY_URL.get(site["url"])


def state():
    return C.get_setting("demo", "never")  # "never" | "loaded" | "removed"


def ensure_loaded():
    """Call from the app's main data callables: loads the demo once, unless an admin removed it."""
    if state() == "never":
        load()


# ----------------------------------------------------------------------------------------------- traffic
def _split(n, weights, rnd):
    total = float(sum(w for _, w in weights))
    out, given = {}, 0
    for name, w in weights:
        k = int(n * w / total)
        if k:
            out[name] = k
            given += k
    for _ in range(n - given):
        name = rnd.choices([w[0] for w in weights], [w[1] for w in weights])[0]
        out[name] = out.get(name, 0) + 1
    return out


def _merge(a, b):
    out = dict(a or {})
    for k, v in b.items():
        out[k] = out.get(k, 0) + v
    return out


def _traffic(p, day, hours, rnd, silent_after=None):
    """Made-up beacon traffic for some hours of a day: daily-row fields to add."""
    per_day = p.get("views", 0) * WEEKDAY[day.weekday()]
    curve = float(sum(CURVE))
    counts = {}
    for h in hours:
        n = 0
        stamp = dt.datetime(day.year, day.month, day.day, h, tzinfo=dt.timezone.utc)
        if per_day and (silent_after is None or stamp < silent_after):
            n = max(0, int(round(per_day * CURVE[h] / curve * rnd.uniform(.7, 1.3))))
        counts[h] = n
    views = sum(counts.values())
    loaded = int(views * .93)
    errors = int(round(rnd.uniform(0, 2) * p.get("errors", 0) * len(list(hours)) / 24.0)) if p.get("errors") else 0
    return {"hours": counts, "views": views, "visitors": int(views * rnd.uniform(.55, .68)),
            "load_sum": int(loaded * p.get("load", 1500) * rnd.uniform(.9, 1.1)), "load_n": loaded,
            "ttfb_sum": int(loaded * p.get("base", 200) * 1.1), "errors": errors,
            "pages": _split(views, PAGES.get(p["key"], [("/", 1)]), rnd) if views else {},
            "refs": _split(views, REFS, rnd) if views else {}, "devices": _split(views, DEVICES, rnd) if views else {}}


def _add_traffic(fields, t):
    hours = list(fields.get("hours") or [None] * 24)
    for h, n in t["hours"].items():
        hours[h] = (hours[h] or 0) + n
    fields["hours"] = hours
    for k in ("views", "visitors", "load_sum", "load_n", "ttfb_sum", "errors"):
        fields[k] = (fields.get(k) or 0) + t[k]
    for k in ("pages", "refs", "devices"):
        fields[k] = _merge(fields.get(k), t[k])
    return fields


# ----------------------------------------------------------------------------------------------- load / remove
def load():
    from . import Monitor, Probe
    remove(remember=False)
    now = C.now()
    today = now.date()
    rnd = random.Random(20261029)
    users = []
    for name, email in DEMO_USERS:
        u = app_tables.users.get(email=email) or app_tables.users.add_row(email=email, enabled=False)
        u.update(display_name=name, is_demo=True, signed_up=now - dt.timedelta(days=120), alert_email="oncall@northwind-coffee.example",
                 alerts_on=True, digest_on=False)
        users.append(u)
    owner = users[0]
    six = now.replace(hour=6, minute=0, second=0, microsecond=0) - (dt.timedelta(days=1) if now.hour < 6 else dt.timedelta(0))

    sites = {}
    for p in SITES:
        silent = now - dt.timedelta(hours=p["silent_h"]) if p.get("silent_h") else None
        beat = silent if silent else (now - dt.timedelta(minutes=rnd.randint(1, 9)) if p.get("views") else None)
        sites[p["key"]] = app_tables.sites.add_row(
            owner=owner, name=p["name"], url=p["url"], site_key="vr_demo" + p["key"], interval_min=p["interval"],
            keyword=p.get("keyword"), expect_status=None, slow_ms=p.get("slow_ms", 3000), quiet_hours=p.get("quiet", 0),
            tags=p["tags"], paused=bool(p.get("paused")), status="paused" if p.get("paused") else "pending", status_since=None,
            last_check=None, next_check=None, last_ms=None, last_code=None, last_error=None, fails=0, slow_streak=0,
            ssl_expires=Probe.simulate_cert(p)["expires"], ssl_issuer=p.get("issuer"), ssl_error=None,
            domain_expires=Probe.simulate_domain(p, Probe.host_of(p["url"]))["expires"], domain_error=None,
            inspected=six, sec_headers=None, page_bytes=p.get("bytes"), server=p.get("server"), last_beat=beat,
            created=now - dt.timedelta(days=118), is_demo=True)

    # The last 24 hours of checks (the paused staging site stopped two days ago).
    check_rows, last = [], {}
    for p in SITES:
        s = sites[p["key"]]
        if p.get("paused"):
            continue
        step = dt.timedelta(minutes=p["interval"])
        t = (now - dt.timedelta(hours=24)).replace(second=0, microsecond=0)
        t = t.replace(minute=(t.minute // p["interval"]) * p["interval"] if p["interval"] < 60 else 0)
        while t <= now:
            prof = dict(p)
            if p.get("down"):
                prof["down"] = t >= now - dt.timedelta(hours=p["down_h"])
            r = Probe.simulate(prof, "%s|%s" % (p["url"], t.strftime("%Y%m%d%H%M")))
            st, problem = Monitor.evaluate(s, r)
            check_rows.append(dict(site=s, at=t, ok=st != "fail", slow=st == "slow", code=r["code"], ms=r["ms"], error=problem,
                                   source="robot", is_demo=True))
            last[p["key"]] = (t, r, st, problem)
            t += step
    C.add_rows(app_tables.checks, check_rows)

    for p in SITES:
        s = sites[p["key"]]
        default_headers = {k: i < p.get("headers", 3) for i, (k, _, _) in enumerate(Probe.SEC_HEADERS)}
        default_headers["https"] = True
        if p["key"] not in last:
            s.update(last_check=now - dt.timedelta(days=2, hours=3), last_ms=505, last_code=200, status_since=now - dt.timedelta(days=2),
                     sec_headers=default_headers)
            continue
        t, r, st, problem = last[p["key"]]
        status = {"fail": "down", "slow": "slow", "up": "up"}[st]
        since = now - dt.timedelta(hours=p.get("down_h") or 5) if status in ("down", "slow") else now - dt.timedelta(days=rnd.randint(3, 11))
        s.update(status=status, status_since=since, last_check=t, last_ms=r["ms"], last_code=r["code"], last_error=problem,
                 fails=6 if status == "down" else 0, slow_streak=5 if status == "slow" else 0,
                 sec_headers=r["headers"] or default_headers,
                 next_check=t + dt.timedelta(minutes=5 if status == "down" else p["interval"]))

    # Daily rows: 45 days of check totals and traffic.
    fail_days = {}
    for kind, key, hours_ago, minutes, sev, title, detail, res in INCIDENTS:
        if kind == "down" and minutes:
            day = (now - dt.timedelta(hours=hours_ago)).date()
            fail_days[(key, day)] = fail_days.get((key, day), 0) + max(2, int(math.ceil(minutes / 5.0)))
    by_day = {}
    for c in check_rows:
        k = (c["site"].get_id(), c["at"].date())
        e = by_day.setdefault(k, [0, 0, 0])
        e[0] += 1
        e[1] += 0 if c["ok"] else 1
        e[2] += c["ms"] or 0
    daily_rows = []
    for p in SITES:
        s = sites[p["key"]]
        silent = now - dt.timedelta(hours=p["silent_h"]) if p.get("silent_h") else None
        per_day = 1440 // p["interval"]
        for back in range(DAYS - 1, -1, -1):
            day = today - dt.timedelta(days=back)
            f: dict = dict(site=s, day=day, checks=0, fails=0, ms_sum=0, views=0, visitors=0, errors=0, load_sum=0, load_n=0,
                     ttfb_sum=0, pages={}, refs={}, devices={}, hours=[None] * 24, is_demo=True)
            if p.get("paused") and back < 3:
                pass
            elif back == 0 and (s.get_id(), day) in by_day:
                n, fails, ms = by_day[(s.get_id(), day)]
                f.update(checks=n, fails=fails, ms_sum=ms)
            elif back == 1 and (s.get_id(), day) in by_day:
                n, fails, ms = by_day[(s.get_id(), day)]
                f.update(checks=per_day + fails, fails=fails, ms_sum=int(ms * (per_day + fails) / max(n, 1)))
            else:
                fails = fail_days.get((p["key"], day), 0)
                f.update(checks=per_day + fails, fails=fails, ms_sum=int((per_day + fails) * p["base"] * rnd.uniform(.92, 1.1)))
            if p.get("views"):
                hours = list(range(24)) if back else list(range(now.hour + 1))
                _add_traffic(f, _traffic(p, day, hours, rnd, silent_after=silent))
            if back:
                f["hours"] = [h or 0 for h in f["hours"]]
            daily_rows.append(f)
    C.add_rows(app_tables.daily, daily_rows)

    for key, msg, src, path, count, first_days in JS_ERRORS:
        app_tables.jserrors.add_row(site=sites[key], message=msg, source=src, path=path, count=count,
                                    first=now - dt.timedelta(days=first_days), last=now - dt.timedelta(minutes=rnd.randint(4, 300)), is_demo=True)

    hbs = {}
    for name, period, grace, ago, status, pings in HEARTBEATS:
        if ago is None:
            last_ping = now.replace(hour=2, minute=14, second=0, microsecond=0)
            if last_ping > now:
                last_ping -= dt.timedelta(days=1)
        else:
            last_ping = now - dt.timedelta(hours=ago)
        hbs[name] = app_tables.heartbeats.add_row(owner=owner, name=name, token=C.token(16, "hb_demo"), period_min=period, grace_min=grace,
                                                  last_ping=last_ping, status=status, pings=pings, created=now - dt.timedelta(days=100), is_demo=True)

    notes_dental = [
        {"at": C.iso(now - dt.timedelta(hours=2, minutes=57)), "by": "Robot", "text": "Second robot recheck: still failing (HTTP 502 Bad Gateway)"},
        {"at": C.iso(now - dt.timedelta(hours=2, minutes=40)), "by": "Mara Lindqvist", "text": "Acknowledged: someone is on it."},
        {"at": C.iso(now - dt.timedelta(hours=2, minutes=31)), "by": "Mara Lindqvist",
         "text": "Host support says the PHP-FPM pool crashed after a plugin update. They're rolling it back."},
    ]
    for kind, key, hours_ago, minutes, sev, title, detail, res in INCIDENTS:
        started = now - dt.timedelta(hours=hours_ago)
        still_open = minutes is None
        app_tables.incidents.add_row(
            owner=owner, site=sites[key], heartbeat=None, kind=kind, severity=sev, title=title, detail=detail, started=started,
            resolved=None if still_open else started + dt.timedelta(minutes=minutes), resolution=res,
            acked=(key == "dental" and still_open) or not still_open,
            notes=notes_dental if (key == "dental" and still_open) else [], is_demo=True)
    late = hbs["Inventory sync (cron)"]
    app_tables.incidents.add_row(owner=owner, site=None, heartbeat=late, kind="heartbeat", severity="critical",
                                 title="Inventory sync (cron) missed its check-in",
                                 detail="Expected every 1 hour; last checked in %s UTC." % C.utc(late["last_ping"]).strftime("%b %d %H:%M"),
                                 started=now - dt.timedelta(hours=2), resolved=None, resolution=None, acked=False, notes=[], is_demo=True)

    for name, trigger, key, actions, enabled, fired in PLAYBOOKS:
        app_tables.playbooks.add_row(owner=owner, name=name, trigger=trigger, site=sites[key] if key else None, actions=actions,
                                     enabled=enabled, fired=fired, last_fired=now - dt.timedelta(hours=rnd.randint(2, 200)),
                                     created=now - dt.timedelta(days=90), is_demo=True)

    oncall = "Page the on-call when a site goes down"
    slack = "https://hooks.slack.example/services/T0NW/B0OPS/demo"
    log = [
        (3, oncall, "Harbor Dental Clinic", "recheck", "Harbor Dental Clinic", "Second robot recheck: still failing (HTTP 502 Bad Gateway)", True),
        (3, oncall, "Harbor Dental Clinic", "email", "oncall@northwind-coffee.example", "Email sent", True),
        (3, oncall, "Harbor Dental Clinic", "webhook", slack, "Webhook delivered", True),
        (2, oncall, "Inventory sync (cron)", "email", "oncall@northwind-coffee.example", "Email sent", True),
        (5, "Second opinion on slow pages", "Pinecrest Realty", "recheck", "Pinecrest Realty", "Second robot recheck: loads fine now (HTTP 200, 2690 ms)", True),
        (6, "Tell #web when visitors vanish", "Maple & Co. Law", "webhook", "https://hooks.slack.example/services/T0NW/B0WEB/demo", "Webhook delivered", True),
        (26, "Certificate reminders", "Little Fern Bakery", "email", "webmaster@northwind-coffee.example", "Email sent", True),
        (50, "Domain renewals to billing", "Maple & Co. Law", "email", "billing@northwind-coffee.example", "Email sent", True),
        (52, "Shop errors to the developers", "Northwind Coffee shop", "email", "dev@northwind-coffee.example", "Email sent", True),
        (150, oncall, "Harbor Dental Clinic", "webhook", slack, "Webhook answered HTTP 500", False),
    ]
    C.add_rows(app_tables.actions_log, [dict(owner=owner, at=now - dt.timedelta(hours=h, minutes=rnd.randint(0, 5)), playbook=pb, subject=subj,
                                             action=act, target=tgt, result=res, ok=ok, is_demo=True) for h, pb, subj, act, tgt, res, ok in log])

    runs = [dict(bot=b, at=now - dt.timedelta(minutes=m), ms=ms, handled=n, summary=sm, ok=True, is_demo=True)
            for b, m, ms, n, sm in [("uptime", 3, 1840, 6, "Checked 6 sites, 2 with a problem"), ("heartbeat", 3, 40, 1, "1 heartbeat late"),
                                    ("silence", 3, 35, 1, "1 site gone quiet")]]
    runs += [dict(bot=b, at=six + dt.timedelta(seconds=i * 20), ms=ms, handled=n, summary=sm, ok=True, is_demo=True)
             for i, (b, ms, n, sm) in enumerate([("certs", 9400, 7, "Inspected 7 certificates and domains"),
                                                 ("janitor", 820, 214, "Deleted 214 old raw rows, closed 0 calm error incidents"),
                                                 ("digest", 300, 0, "Sent 0 digests")])]
    C.add_rows(app_tables.bot_runs, runs)

    app_tables.status_pages.add_row(owner=owner, slug="northwind", title="Northwind Coffee",
                                    intro="Live status of our online shop and website, checked around the clock by robots.",
                                    site_ids=[sites["shop"].get_id(), sites["www"].get_id(), sites["api"].get_id()], public=True,
                                    created=now - dt.timedelta(days=80), is_demo=True)
    C.set_setting("demo", "loaded")
    C.set_setting("demo_alive", C.iso(now))
    return counts()


def keep_alive():
    """Catch the sample fleet up to now when the robots haven't run (at most every 5 minutes)."""
    if state() != "loaded":
        return
    from . import Monitor, Beacon
    now = C.now()
    last = C.get_setting("demo_alive")
    if last and (now - dt.datetime.fromisoformat(last)).total_seconds() < 300:
        return
    C.set_setting("demo_alive", C.iso(now))
    rnd = random.Random(now.strftime("%Y%m%d%H%M"))
    owner = app_tables.users.get(email=C.DEMO_OWNER_EMAIL)
    if owner is None:
        return
    for s in app_tables.sites.search(owner=owner, is_demo=True):
        p = profile(s)
        if p is None or s["paused"]:
            continue
        floor = now - dt.timedelta(hours=6)
        if (C.utc(s["next_check"]) or floor) < floor:
            s["next_check"] = floor
        n = 0
        while s["next_check"] is not None and C.utc(s["next_check"]) <= now and n < 30:
            Monitor.run_check(s, at=C.utc(s["next_check"]))
            n += 1
        if p.get("views"):
            silent = now - dt.timedelta(hours=p["silent_h"]) if p.get("silent_h") else None
            for day in ((now - dt.timedelta(days=1)).date(), now.date()):
                d = Monitor.daily_row(s, day)
                hours = list(d["hours"] or [None] * 24)
                upto = 23 if day < now.date() else now.hour
                todo = [h for h in range(upto + 1) if hours[h] is None]
                if not todo:
                    continue
                fields = {k: d[k] for k in ("views", "visitors", "load_sum", "load_n", "ttfb_sum", "errors", "pages", "refs", "devices")}
                fields["hours"] = hours
                d.update(**_add_traffic(fields, _traffic(p, day, todo, rnd, silent_after=silent)))
            if not silent:
                s["last_beat"] = now - dt.timedelta(minutes=rnd.randint(1, 6))
    for hb in app_tables.heartbeats.search(owner=owner, is_demo=True):
        if hb["status"] != "up":
            continue
        period = dt.timedelta(minutes=hb["period_min"])
        last_ping = C.utc(hb["last_ping"])
        while last_ping + period <= now:
            last_ping += period
        if last_ping != C.utc(hb["last_ping"]):
            Beacon.ping(hb, at=last_ping)


def remove(remember=True):
    for s in app_tables.sites.search(is_demo=True):
        for v in app_tables.visits.search(site=s):
            v.delete()
    for name in DEMO_TABLES:
        for r in getattr(app_tables, name).search(is_demo=True):
            r.delete()
    for u in app_tables.users.search(is_demo=True):
        u.delete()
    if remember:
        C.set_setting("demo", "removed")
    return counts()


def counts():
    out = {"users": len(app_tables.users.search(is_demo=True))}
    for name in DEMO_TABLES:
        out[name] = len(getattr(app_tables, name).search(is_demo=True))
    return out
