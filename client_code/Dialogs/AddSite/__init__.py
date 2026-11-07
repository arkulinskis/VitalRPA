import anvil.server
from anvil import *

from ._anvil_designer import AddSiteTemplate
from ... import router, state, vr

INTERVALS = [5, 15, 30, 60, 180, 360, 720, 1440]


def add_site():
    """The "Add a site" dialog (console, empty states, robots, incidents). On success: the first check's result as a
    toast, then the new site's Install tab."""
    r = alert(AddSite(), buttons=[], role="app-dialog", dismissible=True)
    if not r:
        return
    res = r.get("result")
    if res:
        if res.get("state") == "fail":
            state.toast("First check failed: " + (res.get("problem") or "no answer"), "error")
        else:
            state.toast("First check: HTTP %s in %s" % (res.get("code"), vr.ms(res.get("ms"))), "ok")
    router.go("site", r["site_id"], "install")


class AddSite(AddSiteTemplate):
    """Watch a new site: address, name, how often; more checks (keyword, expected status, slow limit, tags) under a
    disclosure. Closes with {site_id, result} or None."""

    def __init__(self, **properties):
        super().__init__(**properties)
        self.interval_box.items = [(vr.every(m), m) for m in INTERVALS]
        self.interval_box.selected_value = 60
        state.set_control_attr(self.interval_box, "aria-label", "Check every")
        state.set_control_attr(self.url_box, "inputmode", "url")
        state.set_control_attr(self.url_box, "autocomplete", "off")
        self._per_day()

    @handle("", "show")
    def form_show(self, **event_args):
        self.url_box.focus()

    @handle("interval_box", "change")
    def interval_box_change(self, **event_args):
        self._per_day()

    def _per_day(self):
        self.per_day.text = vr.check_ins(self.interval_box.selected_value or 60)

    @handle("url_box", "pressed_enter")
    def url_box_pressed_enter(self, **event_args):
        self.save_button_click()

    @handle("name_box", "pressed_enter")
    def name_box_pressed_enter(self, **event_args):
        self.save_button_click()

    @handle("cancel_button", "click")
    def cancel_button_click(self, **event_args):
        self.raise_event("x-close-alert", value=None)

    @handle("save_button", "click")
    def save_button_click(self, **event_args):
        url = (self.url_box.text or "").strip()
        if not url:
            self._say("Paste the address of the site first.")
            return
        data = {"url": url, "name": self.name_box.text or "", "interval_min": self.interval_box.selected_value or 60,
                "keyword": self.keyword_box.text or "", "expect_status": self.status_box.text or "",
                "slow_ms": self.slow_box.text or 3000, "tags": self.tags_box.text or ""}
        self.save_button.enabled = False
        try:
            r = anvil.server.call("add_site", data)
            if not r.get("ok"):
                self._say(r.get("error") or "That didn't work.")
                return
            c = state.call_quiet("check_now", r["site_id"])
        finally:
            self.save_button.enabled = True
        self.raise_event("x-close-alert", value={"site_id": r["site_id"], "result": (c or {}).get("result")})

    def _say(self, text):
        self.message.text, self.message.visible = text, True
