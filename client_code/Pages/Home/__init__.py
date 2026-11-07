from anvil import *
import anvil.js
from anvil.js import window

from ._anvil_designer import HomeTemplate
from ... import router, state, vr
from ...Dialogs.AddSite import add_site


class Home(HomeTemplate):
    """#home, #home/sample: the Console (Operate). Every site at a glance: status light, the last 24 hours (one cell
    per hour), 30-day uptime, response time, visitors today, certificate, beacon; KPI tiles; the robot log. Refreshes
    itself every minute. People with no sites see the read-only sample fleet."""

    def __init__(self, args=(), **properties):
        super().__init__(**properties)
        state.heading(self.title, 1)
        state.set_control_attr(self.filter_box, "aria-label", "Filter sites")
        self.sample = True if args and args[0] == "sample" else None
        self.tag, self.query = "all", ""
        self.data: dict = {}
        self._timer = None
        self._tick = anvil.js.report_exceptions(self._refresh_quietly)
        self.tags_panel.add_event_handler("x-tag", self._pick_tag)
        self._load(state.call("get_console", self.sample))

    # ---- data
    def _load(self, d):
        if not d:
            return
        self.data = d
        t, mine = d["totals"], d["mode"] == "mine"
        self.sub.text = "%s \u00b7 %s \u00b7 %s robot checks in 24 h \u00b7 %s passed" % (
            "Your fleet" if mine else "Sample fleet", state.plural(t["sites"], "site"), vr.num(t["checks24"]), vr.pct(t["up24"]))
        self.sample_banner.visible = not mine
        self.dom_nodes["sample_owner"].textContent = d.get("sample_owner") or "demo"
        self.back_link.visible = bool(d.get("has_own")) and not mine
        self._kpi("up", "%d<span class=\"faint\">/%d</span>" % (t["up"], t["sites"] - t["paused"]), "bad" if t["down"] else "good",
                  ("%d down%s" % (t["down"], (", %d slow" % t["slow"]) if t["slow"] else "")) if t["down"]
                  else ("%d slow" % t["slow"]) if t["slow"] else "all answering")
        self._kpi("inc", str(t["incidents"]), "bad" if t["critical"] else "warn" if t["incidents"] else "good",
                  ("%d critical" % t["critical"]) if t["critical"] else "nothing urgent")
        self._kpi("vis", vr.num(t["visitors"]), "", vr.num(t["views"]) + " page views")
        self._kpi("avg", vr.ms(t["avg_ms"]), "", "last 24 h")
        self._kpi("ssl", str(t["certs_soon"]) if t["certs_soon"] else "OK", "warn" if t["certs_soon"] else "good",
                  "expiring \u2264 14 days" if t["certs_soon"] else "none expiring soon")
        self.tools.visible = self.table.visible = bool(d["sites"])
        self.empty.visible = not d["sites"]
        self.log_panel.items = d["feed"]
        self.log_idle.visible = not d["feed"]
        self.updated.text = "Updated %s UTC \u00b7 refreshes every minute" % vr.hhmm(d.get("now"))
        self.sample_link.visible = mine and bool(d.get("can_sample"))
        self._draw_list()
        state.set_open(t["incidents"] if mine else 0)

    def _kpi(self, key, value_html, cls, sub):
        b = self.dom_nodes["k_" + key]
        b.innerHTML = value_html
        b.className = cls
        self.dom_nodes["k_%s_sub" % key].textContent = sub

    def _draw_list(self):
        d = self.data
        tags = ["all"] + list(d["tags"])
        if self.tag not in tags:
            self.tag = "all"
        self.tags_panel.items = [{"tag": g, "on": g == self.tag} for g in tags]
        q = self.query
        rows = [s for s in d["sites"] if (self.tag == "all" or self.tag in s["tags"])
                and (not q or q in (s["name"] + " " + s["host"]).lower())]
        self.sites_panel.items = rows
        self.no_match.visible = bool(d["sites"]) and not rows

    # ---- filters
    @handle("filter_box", "change")
    def filter_box_change(self, **event_args):
        self.query = (self.filter_box.text or "").strip().lower()
        self._draw_list()

    def _pick_tag(self, tag, **event_args):
        key = state.focus_key()
        self.tag = tag
        self._draw_list()
        state.refocus(self.tags_panel, key)

    # ---- buttons
    @handle("refresh_button", "click")
    def refresh_button_click(self, **event_args):
        self._load(state.call("get_console", self.sample))

    @handle("add_button", "click")
    def add_button_click(self, **event_args):
        add_site()

    @handle("add_first_button", "click")
    def add_first_button_click(self, **event_args):
        add_site()

    @handle("empty_add_button", "click")
    def empty_add_button_click(self, **event_args):
        add_site()

    # ---- the minute refresh (stops when the page is left)
    def _refresh_quietly(self, *args):
        if window.document.hidden or window.document.querySelector(".modal.in, .anvil-modal.in, .modal-backdrop"):
            return
        d = state.call_quiet("get_console", self.sample)
        if d:
            self._load(d)

    @handle("", "show")
    def form_show(self, **event_args):
        if self._timer is None:
            self._timer = window.setInterval(self._tick, 60000)

    @handle("", "hide")
    def form_hide(self, **event_args):
        self.leave()

    def leave(self):
        if self._timer is not None:
            window.clearInterval(self._timer)
            self._timer = None
