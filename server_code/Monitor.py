"""Monitor: run one check on a site and record everything it means.

run_check(site): the check row, the day's totals, the site's status, and incidents:
  - a failed check is retried 2 minutes later before anyone is alarmed (status "retrying");
  - the second failure in a row marks the site down and opens a "down" incident;
  - while a site is down the robots look every 5 minutes, so recovery is noticed quickly;
  - SLOW_STREAK slow checks in a row open a "slow" incident; a fast check closes it.
inspect(site): the certificate and domain checks (daily, or "Full inspection" on the site page).
"""
import datetime as dt

from anvil.tables import app_tables

from . import common as C
from . import Probe
from . import Incidents

SLOW_STREAK = 3
RETRY_MIN = 2
DOWN_EVERY_MIN = 5
SSL_WARN_DAYS = 14
DOMAIN_WARN_DAYS = 30
INTERVALS = [5, 15, 30, 60, 180, 360, 720, 1440]


def profile(site):
    from . import DemoData
    p = DemoData.profile(site) if site["is_demo"] else None
    return p or {"base": 230, "jitter": 60, "url": site["url"], "headers": 3, "bytes": 52000}


def simulated(site):
    return bool(site["is_demo"]) or Probe.SIMULATE_ALL


def daily_row(site, day=None):
    day = day or C.today()
    for r in app_tables.daily.search(site=site, day=day):
        return r
    return app_tables.daily.add_row(site=site, day=day, checks=0, fails=0, ms_sum=0, views=0, visitors=0, errors=0,
                                    load_sum=0, load_n=0, ttfb_sum=0, pages={}, refs={}, devices={}, hours=[0] * 24,
                                    is_demo=bool(site["is_demo"]))


def evaluate(site, r):
    """('up' | 'slow' | 'fail', problem text or None) for one probe result."""
    code = r.get("code")
    if not code:
        return "fail", r.get("error") or "No answer"
    expect = site["expect_status"]
    good = (code == expect) if expect else (200 <= code < 400)
    if not good:
        why = Probe.reason(code)
        return "fail", "HTTP %d%s" % (code, (" " + why) if why else "") + (" (expected %d)" % expect if expect else "")
    if r.get("keyword_found") is False:
        return "fail", 'The text "%s" is missing from the page' % (site["keyword"] or "")
    if r.get("ms") and r["ms"] > (site["slow_ms"] or 3000):
        return "slow", "Slow: %d ms (limit %d ms)" % (r["ms"], site["slow_ms"] or 3000)
    return "up", None


def run_check(site, at=None, source="robot"):
    """Check the site now (or at `at`, for the demo's catch-up) and record it. Returns a summary dict."""
    at = at or C.now()
    if simulated(site):
        r = Probe.simulate(profile(site), "%s|%s" % (site["url"], at.strftime("%Y%m%d%H%M")))
    else:
        r = Probe.http_check(site["url"], site["keyword"] or None)
    state, problem = evaluate(site, r)
    demo = bool(site["is_demo"])
    app_tables.checks.add_row(site=site, at=at, ok=state != "fail", slow=state == "slow", code=r.get("code"),
                              ms=r.get("ms"), error=problem, source=source, is_demo=demo)
    d = daily_row(site, at.date())
    d.update(checks=(d["checks"] or 0) + 1, fails=(d["fails"] or 0) + (1 if state == "fail" else 0),
             ms_sum=(d["ms_sum"] or 0) + (r.get("ms") or 0))

    fails = (site["fails"] or 0) + 1 if state == "fail" else 0
    slow_streak = (site["slow_streak"] or 0) + 1 if state == "slow" else 0
    interval = site["interval_min"] or 60
    if state == "fail" and fails == 1:
        status, nxt = "retrying", at + dt.timedelta(minutes=RETRY_MIN)
    elif state == "fail":
        status, nxt = "down", at + dt.timedelta(minutes=min(interval, DOWN_EVERY_MIN))
    else:
        status, nxt = ("slow" if state == "slow" else "up"), at + dt.timedelta(minutes=interval)
    changes = dict(last_check=at, last_ms=r.get("ms"), last_code=r.get("code"), last_error=problem, fails=fails,
                   slow_streak=slow_streak, next_check=nxt)
    if not site["paused"]:
        changes["status"] = status
        if status != site["status"]:
            changes["status_since"] = at
    if r.get("headers"):
        changes["sec_headers"] = r["headers"]
    if r.get("bytes") is not None:
        changes["page_bytes"] = r["bytes"]
    if r.get("server"):
        changes["server"] = r["server"]
    site.update(**changes)

    name = site["name"]
    if state == "fail" and fails >= 2:
        Incidents.open_incident(site["owner"], "down", "%s is down" % name, problem, site=site)
    if state != "fail":
        Incidents.resolve(site=site, kind="down", how="Back up: HTTP %s in %s ms" % (r.get("code"), r.get("ms")))
    if state == "slow" and slow_streak >= SLOW_STREAK:
        Incidents.open_incident(site["owner"], "slow", "%s is slow" % name,
                                "%d slow checks in a row (latest %d ms)" % (slow_streak, r.get("ms") or 0), site=site)
    if state == "up":
        Incidents.resolve(site=site, kind="slow", how="Fast again: %s ms" % r.get("ms"))
    return {"state": state, "status": site["status"], "code": r.get("code"), "ms": r.get("ms"), "problem": problem,
            "at": C.iso(at), "redirects": r.get("redirects"), "bytes": r.get("bytes")}


def inspect(site):
    """Certificate + domain registration. Opens or closes "ssl" and "domain" incidents."""
    host = Probe.host_of(site["url"])
    https = (site["url"] or "").startswith("https://")
    if simulated(site):
        cert = Probe.simulate_cert(profile(site)) if https else None
        dom = Probe.simulate_domain(profile(site), host)
    else:
        cert = Probe.cert_check(host) if https else None
        dom = Probe.domain_check(host)
    changes = {"inspected": C.now()}
    name = site["name"]
    if cert is not None:
        changes.update(ssl_expires=cert["expires"], ssl_issuer=cert["issuer"], ssl_error=cert["error"])
        days = _days_left(cert["expires"])
        if cert["error"]:
            Incidents.open_incident(site["owner"], "ssl", "%s: certificate problem" % name, cert["error"], site=site, severity="critical")
        elif days is not None and days <= SSL_WARN_DAYS:
            sev = "critical" if days <= 3 else "warning"
            Incidents.open_incident(site["owner"], "ssl", "%s: certificate expires in %s" % (name, _plural_days(days)),
                                    "Issued by %s. Renew it, or check that auto-renewal still works." % (cert["issuer"] or "?"),
                                    site=site, severity=sev)
        else:
            Incidents.resolve(site=site, kind="ssl", how="Certificate valid for %s" % _plural_days(days))
    else:
        changes.update(ssl_expires=None, ssl_issuer=None, ssl_error=None)
    changes.update(domain_expires=dom["expires"], domain_error=dom["error"])
    ddays = _days_left(dom["expires"])
    if ddays is not None and ddays <= DOMAIN_WARN_DAYS:
        Incidents.open_incident(site["owner"], "domain", "%s: domain expires in %s" % (name, _plural_days(ddays)),
                                "%s must be renewed at the registrar." % dom["domain"], site=site,
                                severity="critical" if ddays <= 7 else "warning")
    elif ddays is not None:
        Incidents.resolve(site=site, kind="domain", how="Domain renewed (%s left)" % _plural_days(ddays))
    site.update(**changes)
    return {"ssl_days": _days_left(changes.get("ssl_expires")), "ssl_error": changes.get("ssl_error"),
            "domain_days": ddays, "domain_error": dom["error"]}


def _days_left(when):
    when = C.utc(when)
    return None if when is None else int((when - C.now()).total_seconds() // 86400)


def days_left(when):
    return _days_left(when)


def _plural_days(n):
    return "%d day%s" % (n, "" if n == 1 else "s") if n is not None else "?"
