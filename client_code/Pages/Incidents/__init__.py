from anvil import *

from ._anvil_designer import IncidentsTemplate
from ... import router, state
from ...Dialogs.AddSite import add_site

FILTERS = ["open", "resolved", "all"]


class Incidents(IncidentsTemplate):
    """#incidents, #incidents/resolved, #incidents/all: what broke, opened and closed by the robots. Acknowledge
    ("someone is on it"), add notes (a shared timeline), resolve by hand. Sample ones are read-only."""

    def __init__(self, args=(), **properties):
        super().__init__(**properties)
        state.heading(self.title, 1)
        self.filter = args[0] if args and args[0] in FILTERS else "open"
        self.inc_panel.add_event_handler("x-changed", self._changed)
        self._load()

    def _load(self):
        d = state.call("list_incidents", self.filter)
        if not d:
            return
        mine = d["mode"] == "mine"
        self.sample_banner.visible = not mine
        for key, el, label in (("open", self.f_open, "Open (%d)" % d["open"]), ("resolved", self.f_resolved, "Resolved"),
                               ("all", self.f_all, "All")):
            el.text = label
            el.role = ["seg", "on"] if key == self.filter else ["seg"]
            state.set_control_attr(el, "aria-pressed", "true" if key == self.filter else "false")
        crit = len([i for i in d["incidents"] if not i["resolved"] and i["severity"] == "critical"])
        self.crit.visible = self.filter == "open" and crit > 0
        self.crit.text = "%d critical" % crit
        self.inc_panel.items = d["incidents"]
        self.empty.visible = not d["incidents"]
        self.empty_title.text = "All quiet" if self.filter == "open" else "Nothing here"
        self.empty_text.text = "No open incidents. The robots are watching." if self.filter == "open" else "No incidents yet."
        state.set_open(d["open"] if mine else 0)

    def _set(self, value):
        self.filter = value
        router.replace("incidents", "" if value == "open" else value)
        self._load()

    @handle("f_open", "click")
    def f_open_click(self, **event_args):
        self._set("open")

    @handle("f_resolved", "click")
    def f_resolved_click(self, **event_args):
        self._set("resolved")

    @handle("f_all", "click")
    def f_all_click(self, **event_args):
        self._set("all")

    def _changed(self, **event_args):
        self._load()

    @handle("add_button", "click")
    def add_button_click(self, **event_args):
        add_site()
