from anvil import *
from anvil.js import window

from ._anvil_designer import ReportCardTemplate
from ... import state, vr


def report_link(token):
    return window.location.origin + window.location.pathname + "#report/" + token


class ReportCard(ReportCardTemplate):
    """#reports: one client report (name, tag, private link with Copy, Rename, New link, Turn off). item = report dict
    (+ "_open": show the editor, set when the Console just created it). Raises x-changed on the panel."""

    def __init__(self, **properties):
        super().__init__(**properties)
        self._draw()
        self._edit(bool(self.item.get("_open")), focus=False)

    def _draw(self):
        r, n = self.item, self.dom_nodes
        n["title"].textContent = r.get("title") or ""
        n["meta"].textContent = "%s \u00b7 %s \u00b7 opened %s" % (
            ("#" + r["tag"]) if r.get("tag") else "all sites", state.plural(r.get("sites") or 0, "site"),
            state.plural(r.get("views") or 0, "time"))
        link = report_link(r["token"])
        n["link"].textContent = link
        state.set_attr(self.open_link, "href", "#report/" + r["token"])
        self.title_box.text = r.get("title") or ""
        self.note_box.text = r.get("note") or ""

    def _edit(self, on, focus=True):
        self.editor.visible = on
        self.save_button.visible = on
        self.edit_button.visible = not on
        if on and focus:
            self.title_box.focus()

    @handle("copy_button", "click")
    def copy_button_click(self, **event_args):
        link = report_link(self.item["token"])
        state.toast("Link copied: send it to your client" if vr.copy(link) else link, "ok")

    @handle("edit_button", "click")
    def edit_button_click(self, **event_args):
        self._edit(True)

    @handle("save_button", "click")
    def save_button_click(self, **event_args):
        r = state.call("save_report", {"id": self.item["id"], "title": self.title_box.text or "", "tag": self.item.get("tag") or "",
                                       "note": self.note_box.text or ""})
        if r:
            self.item = r["report"]
            self._draw()
            self._edit(False)
            state.toast("Saved", "ok")

    @handle("rotate_button", "click")
    def rotate_button_click(self, **event_args):
        if confirm("Anyone with the old link sees \u201cThis report link was turned off\u201d.", title="Make a new link?",
                   buttons=[("Cancel", False), ("New link", True)], role="app-dialog"):
            r = state.call("rotate_report_link", self.item["id"])
            if r:
                self.item = r["report"]
                self._draw()
                state.toast("New link ready: copy it again", "ok")

    @handle("delete_button", "click")
    def delete_button_click(self, **event_args):
        if confirm("The link stops working straight away. Your sites and their history stay.", title="Turn off this report?",
                   buttons=[("Cancel", False), ("Turn off", True)], role="app-dialog"):
            if state.call("delete_report", self.item["id"]):
                state.toast("Report turned off", "ok")
                self.parent.raise_event("x-changed")
