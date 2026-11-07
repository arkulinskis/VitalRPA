from anvil import *

from ._anvil_designer import ErrorsTemplate
from ... import state


class Errors(ErrorsTemplate):
    """Site -> JS errors: what real visitors hit, grouped by message (from the beacon)."""

    def __init__(self, site, page, **properties):
        super().__init__(**properties)
        self.s, self.page = site, page
        errs = site["jserrors"]
        self.errors_panel.items = errs
        self.clear_button.visible = bool(site["can_edit"] and errs)
        self.empty.visible = not errs
        self.empty_text.text = ("Install the beacon to catch errors your visitors see." if site["beacon"] == "none"
                                else "Visitors haven't hit any. Nice.")

    @handle("clear_button", "click")
    def clear_button_click(self, **event_args):
        if confirm("They come back if visitors hit them again.", title="Clear all JavaScript errors?",
                   buttons=[("Cancel", False), ("Clear", True)], role="app-dialog"):
            if state.call("clear_js_errors", self.s["id"]):
                self.page.reload()
