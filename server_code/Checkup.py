"""The free website check-up (#checkup/<host>): anyone, signed in or not, types an address and the robots run one
visit plus the certificate, domain and security-header checks, then show a report card with a link to share.

Two calls so each stays well under a server-call timeout and drives the robot log on the page:
    checkup_http(address, fresh=False)  -> the page visit (status, time, redirects, weight, server, headers)
    checkup_tls(run_id)                  -> the certificate + the domain registration, and the finished card
Results are kept per run in `checkups` (host, url, at, result) for 2 days (Bots.janitor), so a shared link shows the same
card without a new visit. A fresh run is refused for a host checked in the last 30 minutes (the cached card comes
back instead), after 8 fresh runs per browser session in an hour, and after 200 fresh runs per hour for everyone.
No IP address or account is stored with a check-up.

SSRF guard: only http(s) on the default ports, only public hostnames (Probe.normalize_url refuses localhost, .local,
.internal, literal private/loopback/link-local/metadata IPs; Probe.http_check / cert_check refuse names that RESOLVE
into a private network, also after every redirect).
"""
import datetime as dt
import hashlib

import anvil.server
from anvil.tables import app_tables
import anvil.tables as tables
import anvil.tables.query as q

from . import common as C
from . import Probe

FRESH_MIN = 30            # a run younger than this is served from the table, never repeated
SESSION_LIMIT = 8         # fresh runs per browser session per hour
GLOBAL_LIMIT = 200        # fresh runs per hour, everyone together
TLS_WINDOW_MIN = 10       # the second half of a run must follow its first half within this time
HTTP_TIMEOUT, CERT_TIMEOUT, RDAP_TIMEOUT = 10, 6, 8

REFUSE = ("That doesn't look like a public website address. Type something like example.com "
          "(no passwords, no private or local addresses).")


# ----------------------------------------------------------------------------------------------- addresses
def clean_host(raw):
    """(host, None) for a public website address typed in any shape, or (None, reason)."""
    s = C.text(raw, 300)
    if not s:
        return None, "Type the address of a website first."
    low = s.lower()
    if "://" in low and not low.startswith(("http://", "https://")):
        return None, "The robots only visit http and https addresses."
    url = Probe.normalize_url(s)
    if not url:
        return None, REFUSE
    import urllib.parse
    u = urllib.parse.urlsplit(url)
    if u.port not in (None, 80, 443):
        return None, "The free check-up only visits websites on the normal ports (80 and 443)."
    host = (u.hostname or "").lower()
    if not host or len(host) > 253 or Probe._private_ip(host):
        return None, REFUSE
    return host, None


def _latest(host):
    for r in app_tables.checkups.search(tables.order_by("at", ascending=False), host=host):
        return r
    return None


def _minutes(row):
    return C.minutes_since(row["at"]) or 0.0


def _recent_runs():
    return len(app_tables.checkups.search(at=q.greater_than(C.now() - dt.timedelta(hours=1))))


# ----------------------------------------------------------------------------------------------- the report card
def _row(key, label, status, value, todo):
    return {"key": key, "label": label, "status": status, "value": value, "todo": todo}


def _days_text(n):
    if n is None:
        return ""
    if n < 0:
        return "expired %d day%s ago" % (-n, "" if n == -1 else "s")
    return "%d day%s left" % (n, "" if n == 1 else "s")


def card(res):
    """The report card rows (status good / warn / bad / info, a value, what to do) from a run's result."""
    h = res.get("http") or {}
    rows = []
    code, ms = h.get("code"), h.get("ms")
    if not code:
        rows.append(_row("status", "Answers visitors", "bad", h.get("error") or "No answer",
                         "Visitors can't reach the site right now. Check the hosting, the DNS records and the firewall."))
    elif 200 <= code < 400:
        rows.append(_row("status", "Answers visitors", "good", "HTTP %d in %s ms" % (code, ms),
                         "Nothing to do. Robots can check this every hour so you hear about an outage first."))
    else:
        why = Probe.reason(code)
        rows.append(_row("status", "Answers visitors", "bad", "HTTP %d%s" % (code, (" " + why) if why else ""),
                         "The server answers with an error page. Check the server's error log or the hosting dashboard."))
    if code:
        weight = h.get("bytes")
        extra = ", %s" % _size(weight) if weight else ""
        if ms is not None and ms <= 800:
            rows.append(_row("speed", "First response", "good", "%d ms%s" % (ms, extra), "Quick. Keep an eye on it after big updates."))
        elif ms is not None and ms <= 2500:
            rows.append(_row("speed", "First response", "warn", "%d ms%s" % (ms, extra),
                             "A bit slow. Page caching or a CDN usually brings this under half a second."))
        else:
            rows.append(_row("speed", "First response", "bad", "%s ms%s" % (ms, extra),
                             "Slow: visitors and search engines notice. Look at caching, hosting and heavy plugins."))
    t = res.get("tls")
    if t is not None:
        cert = t.get("cert")
        if not h.get("https"):
            rows.append(_row("cert", "HTTPS certificate", "bad", "No HTTPS",
                             "Browsers mark the site \"Not secure\". Turn on a free Let's Encrypt certificate at your host."))
        elif cert and cert.get("error"):
            rows.append(_row("cert", "HTTPS certificate", "bad", cert["error"], "Renew or reinstall the certificate today."))
        elif cert and cert.get("days") is not None:
            d = cert["days"]
            st = "bad" if d <= 7 else "warn" if d <= 21 else "good"
            todo = ("Renew it now, or check that auto-renewal still works." if st != "good"
                    else "Fine for now. Make sure auto-renewal works: nobody emails you before it runs out.")
            rows.append(_row("cert", "HTTPS certificate", st, "%s, %s (%s)" % (cert.get("issuer") or "Unknown issuer",
                                                                               _days_text(d), cert.get("expires", "")[:10]), todo))
        dom = t.get("domain") or {}
        if dom.get("days") is not None:
            d = dom["days"]
            st = "bad" if d <= 14 else "warn" if d <= 60 else "good"
            rows.append(_row("domain", "Domain registration", st, "%s renews %s (%s)" % (dom.get("domain"), dom.get("expires", "")[:10], _days_text(d)),
                             "Renew it at the registrar now, and check the card on file." if st != "good" else
                             "Fine. Check that auto-renew is on and the card on file is current."))
        else:
            rows.append(_row("domain", "Domain registration", "info", "%s: %s" % (dom.get("domain") or "?", dom.get("error") or "no data"),
                             "This registry doesn't publish an expiry date. Note it from your registrar's dashboard."))
    sec = Probe.sec_grade(h.get("headers"), h.get("final_url") or "")
    if sec["grade"]:
        g = sec["grade"]
        missing = [i["name"] for i in sec["items"] if not i["ok"]]
        rows.append(_row("headers", "Security headers", "good" if g in ("A", "B") else "warn" if g == "C" else "bad",
                         "Grade %s, %d of 6" % (g, sec["score"]),
                         ("Add: " + ", ".join(missing[:4]) + "." if missing else "All six are in place.") +
                         (" Your host or CDN can add them without changing the site." if missing else "")))
    elif code is None:
        rows.append(_row("headers", "Security headers", "info", "Not read", "The page didn't answer, so there were no headers to read."))
    return rows


def _size(n):
    if n >= 1048576:
        return "%.1f MB" % (n / 1048576.0)
    if n >= 1024:
        return "%d KB" % int(round(n / 1024.0))
    return "%d B" % n


def _log_http(url, h):
    lines = []
    if h.get("code"):
        lines.append({"level": "ok" if 200 <= h["code"] < 400 else "bad", "bot": "uptime",
                      "text": "GET %s → %s in %s ms" % (url, h["code"], h.get("ms"))})
    else:
        lines.append({"level": "bad", "bot": "uptime", "text": "GET %s → %s" % (url, h.get("error") or "no answer")})
    if h.get("redirects"):
        lines.append({"level": "ok", "bot": "uptime", "text": "%d redirect%s → %s" % (h["redirects"], "" if h["redirects"] == 1 else "s",
                                                                                      h.get("final_url"))})
    facts = [x for x in (_size(h["bytes"]) if h.get("bytes") else "", h.get("server") or "") if x]
    if facts:
        lines.append({"level": "ok", "bot": "uptime", "text": ", ".join(facts)})
    sec = Probe.sec_grade(h.get("headers"), h.get("final_url") or "")
    if sec["grade"]:
        lines.append({"level": "ok" if sec["grade"] in ("A", "B") else "warn", "bot": "headers",
                      "text": "Security headers: %s, %d of 6" % (sec["grade"], sec["score"])})
    return lines


def _log_tls(t, https):
    lines = []
    cert = t.get("cert")
    if not https:
        lines.append({"level": "bad", "bot": "certs", "text": "TLS: no HTTPS on this address"})
    elif cert and cert.get("error"):
        lines.append({"level": "bad", "bot": "certs", "text": "TLS: " + cert["error"]})
    elif cert:
        d = cert.get("days")
        lines.append({"level": "ok" if d is None or d > 21 else "warn" if d > 7 else "bad", "bot": "certs",
                      "text": "TLS: %s, %s" % (cert.get("issuer") or "?", _days_text(d))})
    dom = t.get("domain") or {}
    if dom.get("expires"):
        lines.append({"level": "ok" if (dom.get("days") or 0) > 60 else "warn", "bot": "certs",
                      "text": "Domain: %s renews %s" % (dom.get("domain"), dom["expires"][:10])})
    else:
        lines.append({"level": "warn", "bot": "certs", "text": "Domain: %s, %s" % (dom.get("domain") or "?", dom.get("error") or "no data")})
    return lines


def verdict(rows):
    bad = sum(1 for r in rows if r["status"] == "bad")
    warn = sum(1 for r in rows if r["status"] == "warn")
    if bad:
        return {"level": "bad", "text": "%d problem%s found" % (bad, "" if bad == 1 else "s")}
    if warn:
        return {"level": "warn", "text": "Healthy, %d thing%s to watch" % (warn, "" if warn == 1 else "s")}
    return {"level": "good", "text": "Healthy"}


def _reply(row, cached):
    res = dict(row["result"] or {})
    out = {"host": row["host"], "url": row["url"], "at": C.iso(row["at"]), "age_min": int(_minutes(row)), "run_id": row.get_id(),
           "cached": cached, "http": res.get("http"), "log": list(res.get("log") or []), "done": res.get("tls") is not None,
           "fresh_after_min": FRESH_MIN}
    if out["done"]:
        rows = card(res)
        out.update(rows=rows, verdict=verdict(rows))
    return C.ok(**out)


# ----------------------------------------------------------------------------------------------- simulation (local + tests)
def _simulated_http(url, host):
    seed = int(hashlib.sha256(host.encode("utf-8")).hexdigest()[:8], 16)
    prof = {"base": 180 + seed % 400, "jitter": 40, "url": url, "headers": seed % 7, "bytes": 40000 + seed % 900000,
            "redirects": seed % 2, "server": ["nginx", "cloudflare", "Apache", "LiteSpeed"][seed % 4]}
    r = Probe.simulate(prof, host)
    r["headers"] = dict(r["headers"] or {})
    return r


# ----------------------------------------------------------------------------------------------- callables (public)
@anvil.server.callable
def checkup_http(address, fresh=False):
    """Part 1: the page visit. Serves the latest stored run for the host unless `fresh` (Run again) is asked for and
    the latest run is older than 30 minutes."""
    host, err = clean_host(address)
    if err:
        return C.fail(err)
    last = _latest(host)
    if last is not None and (not fresh or _minutes(last) < FRESH_MIN):
        return _reply(last, True)
    if _recent_runs() >= GLOBAL_LIMIT:
        return C.fail("The robots are very busy right now. Try again in a few minutes." +
                      (" Here is the last check-up." if last is not None else ""))
    if C.rate_limited("checkup", SESSION_LIMIT, 3600):
        return C.fail("That's %d fresh check-ups in an hour, the most for now. Shared links still open, and an "
                      "account watches your sites around the clock for free." % SESSION_LIMIT)
    url = "https://%s/" % host
    if Probe.SIMULATE_ALL:
        h = _simulated_http(url, host)
    else:
        h = Probe.http_check(url, timeout=HTTP_TIMEOUT)
        err_text = (h.get("error") or "")
        if not h.get("code") and not err_text.startswith(("DNS", "Blocked")) and (h.get("ms") or 0) < 7000:
            plain = Probe.http_check("http://%s/" % host, timeout=6)  # no HTTPS at all? try the plain address once
            if plain.get("code"):
                h, url = plain, "http://%s/" % host
    if (h.get("error") or "").startswith("Blocked"):
        return C.fail("That address points inside a private network, so the robots won't visit it.")
    h["https"] = (h.get("final_url") or url).startswith("https://")
    log = _log_http(url, h)
    row = app_tables.checkups.add_row(host=host, url=url, at=C.now(), result={"http": h, "log": log, "tls": None})
    return _reply(row, False)


@anvil.server.callable
def checkup_tls(run_id):
    """Part 2: the certificate and the domain for a run that part 1 just started; returns the finished card."""
    row = C.row_by_id(app_tables.checkups, run_id)
    if row is None:
        return C.fail("That check-up has expired. Run it again.")
    res = dict(row["result"] or {})
    if res.get("tls") is not None:
        return _reply(row, True)
    if _minutes(row) > TLS_WINDOW_MIN:
        return C.fail("That check-up has expired. Run it again.")
    host, h = row["host"], res.get("http") or {}
    https = bool(h.get("https"))
    if Probe.SIMULATE_ALL:
        seed = int(hashlib.sha256(host.encode("utf-8")).hexdigest()[:8], 16)
        cert = Probe.simulate_cert({"ssl_days": 5 + seed % 80, "issuer": ["Let's Encrypt", "Google Trust Services", "Sectigo"][seed % 3]}) if https else None
        dom = Probe.simulate_domain({"domain_days": 20 + seed % 400}, host)
    else:
        cert = Probe.cert_check(host, timeout=CERT_TIMEOUT) if https else None
        dom = Probe.domain_check(host, timeout=RDAP_TIMEOUT)
    from . import Monitor
    t = {"cert": None if cert is None else {"expires": C.iso(cert["expires"]), "issuer": cert["issuer"], "error": cert["error"],
                                             "days": Monitor.days_left(cert["expires"])},
         "domain": {"domain": dom["domain"], "expires": C.iso(dom["expires"]), "error": dom["error"], "days": Monitor.days_left(dom["expires"])}}
    res["tls"] = t
    res["log"] = list(res.get("log") or []) + _log_tls(t, https)
    row["result"] = res
    return _reply(row, False)
