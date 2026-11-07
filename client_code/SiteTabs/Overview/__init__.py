from anvil import *
from anvil.js import window

from ._anvil_designer import OverviewTemplate
from ... import state, vr


class Overview(OverviewTemplate):
    """Site -> Overview: uptime and response KPIs, 90-day bars, the response chart (24 h / 7 days), certificate,
    domain, security headers, the page itself, recent incidents."""

    def __init__(self, site, page, **properties):
        super().__init__(**properties)
        s = self.s = site
        self.range = "7d"
        n = self.dom_nodes
        last = ("HTTP %s" % s["last_code"] if s.get("last_code") else "no answer") + " \u00b7 " + vr.ms(s.get("last_ms")) if s.get("last_check") else "not yet"
        self._kpi("k1", vr.pct(s.get("up24")), "30 days: %s \u00b7 90 days: %s" % (vr.pct(s.get("up30")), vr.pct(s.get("up90"))))
        self._kpi("k2", vr.ms(s.get("avg_ms")), "slow above " + vr.ms(s["settings"]["slow_ms"]))
        self._kpi("k3", last, (state.ago(s["last_check"]) + ((" \u00b7 " + s["last_error"]) if s.get("last_error") else ""))
                  if s.get("last_check") else "the robots are on their way")
        self._kpi("k4", "paused" if s["paused"] else vr.until(s.get("next_check")),
                  "every %s = %s" % (vr.every(s["interval"]), vr.check_ins(s["interval"])))
        n["up90"].textContent = vr.pct(s.get("up90"))
        self.bars.show("uptimeBars", s["uptime90"])
        self._chart()
        # certificate
        https = s["url"].startswith("https://")
        self.ssl_nohttps.visible = not https
        self.ssl_err.visible = https and bool(s.get("ssl_error"))
        self.ssl_err.text = s.get("ssl_error") or ""
        self.ssl_ok.visible = https and not s.get("ssl_error")
        n["ssl_days"].textContent = vr.DASH if s.get("ssl_days") is None else str(s["ssl_days"])
        n["ssl_exp"].textContent = vr.date(s.get("ssl_expires"))
        n["ssl_issuer"].textContent = s.get("ssl_issuer") or vr.DASH
        n["inspected"].textContent = state.ago(s["inspected"]) if s.get("inspected") else "not yet"
        # domain
        self.dom_none.visible = s.get("domain_days") is None
        self.dom_none.text = s.get("domain_error") or "Not inspected yet."
        self.dom_big.visible = s.get("domain_days") is not None
        n["dom_days"].textContent = str(s.get("domain_days") if s.get("domain_days") is not None else "")
        n["domain"].textContent = s.get("domain") or vr.DASH
        n["dom_exp"].textContent = vr.date(s.get("domain_expires")) if s.get("domain_expires") else vr.DASH
        # security headers
        sec = s["security"]
        grade = sec.get("grade")
        n["grade"].textContent = grade or ""
        n["grade"].className = "st-grade " + (grade or "")
        n["grade"].hidden = not grade
        self.headers_panel.visible = bool(grade)
        self.headers_none.visible = not grade
        if grade:
            self.headers_panel.items = [{"ok": sec.get("https"), "name": "HTTPS", "why": "Encrypted connection"}] + list(sec.get("items") or [])
        # the page itself
        st = s["settings"]
        n["bytes"].textContent = vr.size(s.get("page_bytes"))
        n["server"].textContent = s.get("server") or vr.DASH
        n["keyword"].textContent = ("\u201c%s\u201d must appear" % st["keyword"]) if st.get("keyword") else "not checked"
        n["expect"].textContent = str(st.get("expect_status") or "any 2xx / 3xx")
        n["quiet"].textContent = ("after %d h without visitors" % st["quiet_hours"]) if st.get("quiet_hours") else "off"
        incs = s["incidents"][:5]
        self.inc_panel.items = incs
        self.no_inc.visible = not incs

    def _kpi(self, key, value, sub):
        self.dom_nodes[key].textContent = value
        self.dom_nodes[key + "_sub"].textContent = sub

    def _chart(self):
        series = self.s["series"]
        if self.range == "24h":
            now = window.Date.now()
            series = [p for p in series if now - window.Date.parse(p[0]) <= 86400000]
        self.line.show("lineChart", series, {"limit": self.s["settings"]["slow_ms"]})
        for key, el in (("24h", self.r24), ("7d", self.r7)):
            el.classes["on"] = key == self.range

    def range_click(self, event):
        self.range = event.currentTarget.getAttribute("data-range")
        self._chart()
