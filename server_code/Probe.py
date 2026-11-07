"""Probe: the robots' hands. Load a site the way a visitor would and report what the server said:
status code, response time, redirects, page weight, a keyword, security headers. Also the TLS
certificate and the domain's registration expiry (RDAP). No tables here: Monitor.py records results.

Never touches private networks (localhost, 10.x, 192.168.x, cloud metadata...), also after redirects.
Tests replace http_check / cert_check / domain_check. Demo sites never use the network: simulate()
makes their results up from a profile. The dev server sets SIMULATE_ALL so nothing goes online locally.
"""
import datetime as dt
import ipaddress
import json
import random
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (compatible; VitalRPA-Bot/1.0; uptime check)"
MAX_BYTES = 3 * 1024 * 1024
SIMULATE_ALL = False

# (header, short name, why it matters)
SEC_HEADERS = [
    ("strict-transport-security", "HSTS", "Browsers always come back over HTTPS"),
    ("content-security-policy", "CSP", "Limits where scripts may load from"),
    ("x-content-type-options", "No-sniff", "Stops browsers guessing file types"),
    ("x-frame-options", "Frame guard", "Stops other sites from framing yours"),
    ("referrer-policy", "Referrer policy", "Controls what your links leak to others"),
    ("permissions-policy", "Permissions policy", "Turns off camera, mic and friends you don't use"),
]
SECOND_LEVEL = {"co.uk", "org.uk", "ac.uk", "gov.uk", "me.uk", "com.au", "net.au", "org.au", "co.nz", "co.jp",
                "com.br", "co.za", "com.mx", "co.in", "com.tr", "com.cn", "com.sg", "com.hk", "co.kr", "qc.ca"}
REASONS = {400: "Bad Request", 401: "Unauthorized", 403: "Forbidden", 404: "Not Found", 405: "Method Not Allowed",
           408: "Request Timeout", 410: "Gone", 429: "Too Many Requests", 500: "Internal Server Error",
           501: "Not Implemented", 502: "Bad Gateway", 503: "Service Unavailable", 504: "Gateway Timeout",
           520: "Unknown Error", 521: "Web Server Is Down", 522: "Connection Timed Out", 523: "Origin Unreachable",
           524: "A Timeout Occurred", 525: "SSL Handshake Failed", 526: "Invalid SSL Certificate"}


def reason(code):
    return REASONS.get(code, "")


# ----------------------------------------------------------------------------------------------- addresses
def _private_ip(host):
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified


def _resolves_public(host):
    """False if the name points into a private network (the robots don't poke inside networks)."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return True  # the fetch reports the DNS failure itself
    return not any(_private_ip(i[4][0]) for i in infos)


def normalize_url(raw):
    """A clean http(s) URL for a public host, or None."""
    s = (raw or "").strip()
    if not s or len(s) > 500 or any(c.isspace() for c in s):
        return None
    if "://" not in s:
        s = "https://" + s
    try:
        u = urllib.parse.urlsplit(s)
        port = u.port
    except ValueError:
        return None
    host = (u.hostname or "").lower().rstrip(".")
    if u.scheme not in ("http", "https") or not host or "." not in host or u.username or u.password:
        return None
    if host == "localhost" or host.endswith((".local", ".internal", ".localhost", ".lan", ".home")) or _private_ip(host):
        return None
    netloc = host + (":%d" % port if port else "")
    return urllib.parse.urlunsplit((u.scheme, netloc, u.path or "/", u.query, ""))


def host_of(url):
    try:
        return (urllib.parse.urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def registrable_domain(host):
    parts = host.split(".")
    if len(parts) >= 3 and ".".join(parts[-2:]) in SECOND_LEVEL:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


# ----------------------------------------------------------------------------------------------- HTTP
class _Redirects(urllib.request.HTTPRedirectHandler):
    def __init__(self):
        self.count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.count += 1
        h = host_of(newurl)
        if self.count > 8:
            raise urllib.error.URLError("More than 8 redirects")
        if not h or _private_ip(h) or not _resolves_public(h):
            raise urllib.error.URLError("Redirect into a private network was blocked")
        return urllib.request.HTTPRedirectHandler.redirect_request(self, req, fp, code, msg, headers, newurl)


def _why(err):
    r = getattr(err, "reason", err)
    if isinstance(r, socket.gaierror):
        return "DNS lookup failed (the domain doesn't resolve)"
    if isinstance(r, ConnectionRefusedError):
        return "Connection refused"
    if isinstance(r, (socket.timeout, TimeoutError)):
        return "Timed out"
    if isinstance(r, ssl.SSLCertVerificationError):
        return "Certificate problem: %s" % (getattr(r, "verify_message", "") or str(r))[:120]
    if isinstance(r, ssl.SSLError):
        return "TLS handshake failed"
    return (str(r) or type(r).__name__)[:160]


def http_check(url, keyword=None, timeout=12):
    """Load the page. Returns {code, ms, error, final_url, redirects, bytes, keyword_found, headers, server}."""
    out = {"code": None, "ms": None, "error": None, "final_url": url, "redirects": 0, "bytes": None,
           "keyword_found": None, "headers": None, "server": None}
    host = host_of(url)
    if not host or _private_ip(host) or not _resolves_public(host):
        out["error"] = "Blocked: that address is inside a private network"
        return out
    red = _Redirects()
    opener = urllib.request.build_opener(red, urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/json,*/*;q=0.8",
                                               "Accept-Encoding": "identity", "Cache-Control": "no-cache"})
    t0 = time.monotonic()
    resp = None
    try:
        resp = opener.open(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        resp = e
    except urllib.error.URLError as e:
        out["error"] = _why(e)
    except (socket.timeout, TimeoutError):
        out["error"] = "Timed out after %d s" % timeout
    except Exception as e:  # noqa: BLE001 - any failure is a failed check, never a crash
        out["error"] = _why(e)
    if resp is None:
        out["ms"] = int((time.monotonic() - t0) * 1000)
        return out
    try:
        body = resp.read(MAX_BYTES) or b""
    except Exception:  # noqa: BLE001
        body = b""
    out["ms"] = int((time.monotonic() - t0) * 1000)
    out["code"] = int(getattr(resp, "code", None) or resp.getcode() or 0) or None
    out["final_url"] = (resp.geturl() or url)[:500]
    out["redirects"] = red.count
    out["bytes"] = len(body)
    hdrs = {k.lower(): v for k, v in (resp.headers.items() if resp.headers else [])}
    present = {k: (k in hdrs) for k, _, _ in SEC_HEADERS}
    if not present["x-frame-options"] and "frame-ancestors" in hdrs.get("content-security-policy", ""):
        present["x-frame-options"] = True
    present["https"] = out["final_url"].startswith("https://")
    out["headers"] = present
    out["server"] = (hdrs.get("server") or "")[:60] or None
    if keyword:
        try:
            charset = resp.headers.get_content_charset() or "utf-8"
        except Exception:  # noqa: BLE001
            charset = "utf-8"
        out["keyword_found"] = keyword.lower() in body.decode(charset, "replace").lower()
    return out


# ----------------------------------------------------------------------------------------------- certificate + domain
def cert_check(host, timeout=8):
    """{expires (datetime), issuer, error} for the site's TLS certificate."""
    try:
        if _private_ip(host) or not _resolves_public(host):
            return {"expires": None, "issuer": None, "error": "Blocked: private network address"}
        ctx = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as s:
                cert = dict(s.getpeercert() or {})
    except ssl.SSLCertVerificationError as e:
        return {"expires": None, "issuer": None, "error": "Certificate not valid: %s" % (e.verify_message or str(e))[:120]}
    except Exception as e:  # noqa: BLE001
        return {"expires": None, "issuer": None, "error": _why(e)}
    expires = dt.datetime.fromtimestamp(ssl.cert_time_to_seconds(str(cert["notAfter"])), dt.timezone.utc)
    issuer = {}
    for part in cert.get("issuer", ()):
        for k, v in part:
            issuer[k] = v
    return {"expires": expires, "issuer": (issuer.get("organizationName") or issuer.get("commonName") or "")[:80], "error": None}


def domain_check(host, timeout=12):
    """{domain, expires, error}: the registration expiry from RDAP (the modern WHOIS)."""
    dom = registrable_domain(host)
    try:
        req = urllib.request.Request("https://rdap.org/domain/" + urllib.parse.quote(dom),
                                     headers={"User-Agent": UA, "Accept": "application/rdap+json, application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read(600000).decode("utf-8", "replace"))
    except Exception as e:  # noqa: BLE001
        return {"domain": dom, "expires": None, "error": "No registration data (%s)" % _why(e)[:80]}
    for ev in data.get("events") or []:
        if ev.get("eventAction") == "expiration" and ev.get("eventDate"):
            try:
                when = dt.datetime.fromisoformat(ev["eventDate"].replace("Z", "+00:00"))
                return {"domain": dom, "expires": when.astimezone(dt.timezone.utc), "error": None}
            except ValueError:
                break
    return {"domain": dom, "expires": None, "error": "The registry doesn't publish an expiry date"}


# ----------------------------------------------------------------------------------------------- simulation (demo + dev)
def simulate(profile, seed):
    """Made-up but believable results for a site profile (see DemoData.SITES). Deterministic per seed."""
    rnd = random.Random(seed)
    base = profile.get("base", 240)
    jitter = profile.get("jitter", base * 0.25)
    ms = max(20, int(rnd.gauss(base, jitter)))
    if rnd.random() < profile.get("spike", 0.03):
        ms = int(ms * rnd.uniform(2.5, 5))
    headers = {k: i < profile.get("headers", 4) for i, (k, _, _) in enumerate(SEC_HEADERS)}
    headers["https"] = True
    out = {"code": 200, "ms": ms, "error": None, "final_url": profile.get("url"), "redirects": profile.get("redirects", 0),
           "bytes": int(profile.get("bytes", 60000) * rnd.uniform(.97, 1.03)), "keyword_found": True if profile.get("keyword") else None,
           "headers": headers, "server": profile.get("server", "nginx")}
    if profile.get("down") or rnd.random() < profile.get("flaky", 0.0):
        code = profile.get("code", 502)
        if code:
            out.update(code=code, ms=int(rnd.uniform(30, 90) if code in (502, 503) else ms))
        else:
            out.update(code=None, ms=12000, error=profile.get("error", "Timed out after 12 s"), bytes=None, headers=None)
    return out


def simulate_cert(profile):
    days = profile.get("ssl_days", 70)
    return {"expires": _soon(days, 9), "issuer": profile.get("issuer", "Let's Encrypt"), "error": None}


def simulate_domain(profile, host):
    return {"domain": registrable_domain(host), "expires": _soon(profile.get("domain_days", 240), 0), "error": None}


def _soon(days, hour):
    t = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=days)
    return t.replace(hour=hour, minute=0, second=0, microsecond=0)
