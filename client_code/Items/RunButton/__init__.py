from anvil import *

from ._anvil_designer import RunButtonTemplate
from ... import state


class RunButton(RunButtonTemplate):
    """Admin -> Robots: "Run <robot>" (a background task); raises x-ran so the page reloads the runs a moment later."""

    def __init__(self, **properties):
        super().__init__(**properties)
        self.run_button.text = "Run " + self.item["name"]

    @handle("run_button", "click")
    def run_button_click(self, **event_args):
        self.run_button.enabled = False
        try:
            r = state.call("admin_run_bot", self.item["key"])
        finally:
            self.run_button.enabled = True
        if r:
            state.toast("Started: results appear below in a moment", "ok")
            self.parent.raise_event("x-ran")
