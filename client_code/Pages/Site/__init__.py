import anvil.server
from anvil import *
from anvil.js import window

from ._anvil_designer import SiteTemplate
from ... import router, state, vr

TABS = ["overview", "traffic", "checks", "errors", "install", "settings"]


class Site(SiteTemplate):
    """#site/<id>/<tab>: one site in detail. The head (light, name, address, tags, Run check / Inspect / Pause) and the
    tab links stay; the tab itself is a Form from SiteTabs/ (Overview, Traffic, Checks, Errors, Install, Settings) that
    gets the site dict and this page (set_site / reload / show_tab). Sample sites are read-only (no Settings tab)."""

    def __init__(self, args=(), **properties):
        super().__init__(**properties)
        state.heading(self.name_label, 1)
        self.site_id = args[0] if args else ""
        self.tab = args[1] if len(args) > 1 and args[1] in TABS else "overview"
        self.s: dict = {}
        self._tabs = {"overview": self.tab_overview, "traffic": self.tab_traffic, "checks": self.tab_checks,
                      "errors": self.tab_errors, "install": self.tab_install, "settings": self.tab_settings}
        r: dict = anvil.server.call("get_site", self.site_id) if self.site_id else {"ok": False}
        self.missing.visible = not r.get("ok")
        self.main.visible = bool(r.get("ok"))
        if not r.get("ok"):
            self.missing_text.text = str(r.get("error") or "") or "That site doesn't exist, or it isn't yours."
            return
        self.set_site(r["site"])

    # ---- drawing
    def set_site(self, s, tab=None):
        """New data from the server (load, check, inspect, save): redraw the head and the open tab."""
        self.s = s
        if tab:
            self.tab = tab
        if self.tab == "settings" and not s["can_edit"]:
            self.tab = "overview"
        window.document.title = s["name"] + " \u00b7 VitalRPA"
        n, can = self.dom_nodes, s["can_edit"]
        state.set_attr(self.back_link, "href", "#home/sample" if s["demo"] and not can else "#home")
        st = s["status"] or "pending"
        n["led"].className = "vr-led s-" + st
        self.name_label.text = s["name"]
        n["badge"].className = "ui-badge vr-st s-" + st
        n["badge_led"].className = "vr-led s-" + st
        n["badge_text"].textContent = vr.STATUS.get(st, st)
        n["url"].textContent = s["url"]
        n["url"].setAttribute("href", s["url"])
        n["sample"].hidden = not s["demo"]
        tags = n["tags"]
        tags.textContent = ""
        for t in s["tags"]:
            b = window.document.createElement("span")
            b.className = "ui-badge"
            b.textContent = "#" + t
            tags.appendChild(b)
        self.inspect_button.visible = self.pause_button.visible = can
        self.pause_button.text = "Resume" if s["paused"] else "Pause"
        self.pause_button.role = ["btn", "ic-play" if s["paused"] else "ic-pause"]
        self.tab_settings.visible = can
        for name, link in self._tabs.items():
            state.set_attr(link, "href", router.href("site", s["id"], name))
            link.classes["on"] = name == self.tab
            state.set_attr(link, "aria-current", "page" if name == self.tab else None)
        errs = len(s["jserrors"])
        n["err_count"].textContent = str(errs)
        n["err_count"].hidden = not errs
        self._show_tab()

    def _show_tab(self):
        self.body.clear()
        if self.tab == "overview":
            from ...SiteTabs.Overview import Overview as T
        elif self.tab == "traffic":
            from ...SiteTabs.Traffic import Traffic as T
        elif self.tab == "checks":
            from ...SiteTabs.Checks import Checks as T
        elif self.tab == "errors":
            from ...SiteTabs.Errors import Errors as T
        elif self.tab == "install":
            from ...SiteTabs.Install import Install as T
        else:
            from ...SiteTabs.Settings import Settings as T
        self.body.add_component(T(site=self.s, page=self))

    def reload(self, tab=None):
        r = state.call("get_site", self.site_id)
        if r:
            self.set_site(r["site"], tab)

    def show_tab(self, tab):
        router.replace("site", self.site_id, tab)
        self.set_site(self.s, tab)

    # ---- head buttons
    @handle("check_button", "click")
    def check_button_click(self, **event_args):
        self.check_button.enabled = False
        try:
            r = state.call("check_now", self.s["id"])
        finally:
            self.check_button.enabled = True
        if not r:
            return
        x = r["result"]
        if x.get("state") == "fail":
            state.toast("Check failed: " + (x.get("problem") or "no answer"), "error")
        else:
            state.toast("HTTP %s in %s%s" % (x.get("code"), vr.ms(x.get("ms")), " (slow)" if x.get("state") == "slow" else ""), "ok")
        self.set_site(r["site"])

    @handle("inspect_button", "click")
    def inspect_button_click(self, **event_args):
        self.inspect_button.enabled = False
        try:
            r = state.call("inspect_now", self.s["id"])
        finally:
            self.inspect_button.enabled = True
        if not r:
            return
        x = r["result"]
        if x.get("ssl_error"):
            state.toast(x["ssl_error"], "error")
        else:
            state.toast("Certificate: %s \u00b7 domain: %s" % (
                "n/a" if x.get("ssl_days") is None else "%d days" % x["ssl_days"],
                "unknown" if x.get("domain_days") is None else "%d days" % x["domain_days"]), "ok")
        self.set_site(r["site"])

    @handle("pause_button", "click")
    def pause_button_click(self, **event_args):
        flag = not self.s["paused"]
        if state.call("set_site_paused", self.s["id"], flag):
            state.toast("Paused: the robots leave it alone" if flag else "Resumed: checking now", "ok")
            self.reload()
