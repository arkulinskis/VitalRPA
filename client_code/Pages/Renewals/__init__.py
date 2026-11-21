import anvil.server
from anvil import *

from ._anvil_designer import RenewalsTemplate
from ... import state

KEYS = ["week", "month", "quarter", "later", "none"]


class Renewals(RenewalsTemplate):
    """#renewals, #renewals/sample: every certificate and domain in the fleet sorted by days left, in groups (this
    week, within 30 / 90 days, later, no data), with Inspect now; plus the private calendar feed (.ics, https + webcal)."""

    def __init__(self, args=(), **properties):
        super().__init__(**properties)
        state.heading(self.title, 1)
        self.sample = True if args and args[0] == "sample" else None
        self.cal_box.visible = False
        self.cal_link = ""
        for k in KEYS:
            getattr(self, "p_" + k).add_event_handler("x-inspected", self._load)
        self._load()

    def _load(self, **event_args):
        d = state.call("get_renewals", self.sample)
        if not d:
            return
        mine = d["mode"] == "mine"
        self.mode_mine = mine
        self.sample_banner.visible = not mine
        self.back_link.visible = bool(d.get("has_own")) and not mine
        self.calendar_button.visible = mine
        self.sub.text = "%s \u00b7 %s \u00b7 %d due within 30 days" % (
            "Your fleet" if mine else "Sample fleet", state.plural(d["total"], "date"), d["soon"])
        for g in d["groups"]:
            k = g["key"]
            getattr(self, "p_" + k).items = g["items"]
            getattr(self, "g_" + k).visible = bool(g["items"])
            self.dom_nodes["c_" + k].textContent = str(len(g["items"]))
        self.empty.visible = not d["total"]

    def _show_links(self, r):
        self.dom_nodes["cal_url"].textContent = r["https"]
        self.cal_link = r["https"]
        state.set_attr(self.google_link, "href", "https://calendar.google.com/calendar/r?cid=" + r["webcal"].replace(":", "%3A").replace("/", "%2F").replace("?", "%3F").replace("=", "%3D").replace("&", "%26"))
        state.set_attr(self.webcal_link, "href", r["webcal"])
        self.cal_box.visible = True

    @handle("calendar_button", "click")
    def calendar_button_click(self, **event_args):
        r = state.call("get_calendar_link")
        if r:
            self._show_links(r)

    @handle("copy_button", "click")
    def copy_button_click(self, **event_args):
        from ... import vr
        state.toast("Calendar link copied" if vr.copy(self.cal_link) else self.cal_link, "ok")

    @handle("rotate_button", "click")
    def rotate_button_click(self, **event_args):
        if confirm("Calendars subscribed to the old link stop updating. Add the new link to them.", title="Make a new link?",
                   buttons=[("Cancel", False), ("New link", True)], role="app-dialog"):
            r = state.call("rotate_calendar_link")
            if r:
                self._show_links(r)
                state.toast("New calendar link ready", "ok")
