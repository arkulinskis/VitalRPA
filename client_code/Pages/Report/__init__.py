import anvil.server
from anvil import *
from anvil.js import window

from ._anvil_designer import ReportTemplate
from ... import state, vr


def _robots_meta(on):
    """noindex while a private report is open (search engines must not list client reports)."""
    doc = window.document
    el = doc.querySelector('meta[name="robots"][data-vr-report]')
    if on and not el:
        el = doc.createElement("meta")
        el.setAttribute("name", "robots")
        el.setAttribute("content", "noindex, nofollow")
        el.setAttribute("data-vr-report", "1")
        doc.head.appendChild(el)
    elif not on and el:
        el.remove()


class Report(ReportTemplate):
    """#report/<token> (anyone, no account): a client report. Month picker (last full month by default, 6 months back),
    the month's headline numbers, one row per site, what the robots handled, the owner's sign-off line and Print (a clean
    A4 page: app.css @media print hides the app around it). No edit controls."""

    def __init__(self, args=(), **properties):
        super().__init__(**properties)
        state.heading(self.title, 1)
        state.set_control_attr(self.month_box, "aria-label", "Month")
        self.token = args[0] if args else ""
        _robots_meta(True)
        self._load(None)

    def _load(self, month):
        r = anvil.server.call("get_report", self.token, month)
        ok = bool(r.get("ok"))
        self.missing.visible, self.main.visible = not ok, ok
        if not ok:
            self.missing_text.text = r.get("error") or ""
            return
        p, n = r["report"], self.dom_nodes
        h = p["head"]
        window.document.title = p["title"] + " \u00b7 " + p["month_label"]
        self.title.text = p["title"]
        n["month_line"].textContent = p["month_label"] + (" (so far)" if p.get("partial") else "") + (
            " \u00b7 #" + p["tag"] if p.get("tag") else "") + (" \u00b7 sample" if p.get("demo") else "")
        self.month_box.items = [(m["label"], m["key"]) for m in p["months"]]
        self.month_box.selected_value = p["month"]
        state.set_control_attr(self.month_box, "aria-label", "Month")
        n["h_up"].textContent = vr.pct(h.get("uptime"))
        n["h_inc"].textContent = str(h.get("incidents") or 0)
        n["h_down"].textContent = vr.dur(h["down_min"]) if h.get("down_min") else "0 min"
        n["h_checks"].textContent = vr.num(h.get("checks"))
        n["h_ms"].textContent = vr.ms(h.get("avg_ms"))
        n["h_vis_box"].hidden = not h.get("beacon")
        n["h_vis"].textContent = vr.num(h.get("visitors"))
        n["summary"].textContent = self._summary(p)
        self.sites_panel.items = p["sites"]
        self.no_sites.visible = not p["sites"]
        self.inc_panel.items = p["handled"]
        self.no_inc.visible = not p["handled"]
        n["note"].textContent = p.get("note") or ""
        n["note"].hidden = not p.get("note")
        n["generated"].textContent = "Made %s UTC" % vr.stamp(p.get("generated"))

    def _summary(self, p):
        h = p["head"]
        if not h.get("checks"):
            return "The robots have no checks for this month yet."
        sites = len(p["sites"])
        line = "In %s the robots checked %s %s times%s." % (
            p["month_label"], state.plural(sites, "site"), vr.num(h["checks"]),
            (" and handled %s" % state.plural(h["incidents"], "incident")) if h.get("incidents") else ", and nothing needed handling")
        soon = [s["name"] for s in p["sites"] if s.get("ssl_days") is not None and s["ssl_days"] <= 21]
        if soon:
            line += " Certificates to renew soon: %s." % ", ".join(soon[:4])
        return line

    @handle("month_box", "change")
    def month_box_change(self, **event_args):
        self._load(self.month_box.selected_value)

    @handle("print_button", "click")
    def print_button_click(self, **event_args):
        window.print()

    @handle("", "hide")
    def form_hide(self, **event_args):
        self.leave()

    def leave(self):
        _robots_meta(False)
