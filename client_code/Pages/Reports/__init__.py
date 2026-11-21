import anvil.server
from anvil import *

from ._anvil_designer import ReportsTemplate
from ... import router, state


class Reports(ReportsTemplate):
    """#reports (members), #reports/<id> (the one the Console just made: opened for renaming at the top). Lists the
    owner's client reports with their private links, and makes new ones (name, which tag, sign-off line)."""

    def __init__(self, args=(), **properties):
        super().__init__(**properties)
        state.heading(self.title, 1)
        state.set_control_attr(self.tag_box, "aria-label", "Which sites")
        self.focus_id = args[0] if args else None
        self.reports_panel.add_event_handler("x-changed", self._load)
        self._load()

    def _load(self, **event_args):
        d = anvil.server.call("list_reports")
        fleet = bool(d.get("has_fleet"))
        self.no_fleet.visible = not fleet
        self.new_box.visible = fleet
        self.sample_link.visible = bool(d.get("sample"))
        self.tag_box.items = [("All my sites", "")] + [("#%s (%s)" % (t["tag"], state.plural(t["sites"], "site")), t["tag"]) for t in d["tags"]]
        state.set_control_attr(self.tag_box, "aria-label", "Which sites")
        items = []
        for r in d["reports"]:
            r = dict(r)
            if self.focus_id and r["id"] == self.focus_id:
                r["_open"] = True
                items.insert(0, r)
            else:
                items.append(r)
        self.reports_panel.items = items
        self.empty.visible = fleet and not items

    @handle("create_button", "click")
    def create_button_click(self, **event_args):
        tag = self.tag_box.selected_value or ""
        title = (self.title_box.text or "").strip() or (("#%s: website care" % tag) if tag else "")
        r = state.call("save_report", {"title": title, "tag": tag, "note": self.note_box.text or ""})
        if r:
            self.title_box.text = self.note_box.text = ""
            self.focus_id = None
            state.toast("Report ready: copy the link and send it", "ok")
            self._load()
