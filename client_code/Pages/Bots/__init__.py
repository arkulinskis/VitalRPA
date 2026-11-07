from anvil import *

from ._anvil_designer import BotsTemplate
from ... import state
from ...Dialogs.AddSite import add_site
from ...Dialogs.PlaybookForm import PlaybookForm
from ...Dialogs.HeartbeatForm import HeartbeatForm


class Bots(BotsTemplate):
    """#bots: the RPA side. The built-in robots (schedule, last run), playbooks ("if this happens, the robot does
    that": email, webhook, a second-robot recheck), cron heartbeats (a URL your backups call; silence = an incident)
    and the log of everything the robots did."""

    def __init__(self, args=(), **properties):
        super().__init__(**properties)
        state.heading(self.title, 1)
        self.d: dict = {}
        for panel in (self.pb_panel, self.hb_panel):
            panel.add_event_handler("x-changed", self._changed)
        self.pb_panel.add_event_handler("x-edit", self._edit_playbook)
        self._load()

    def _load(self):
        d = state.call("get_bots")
        if not d:
            return
        self.d = d
        mine = d["mode"] == "mine"
        self.paused_note.visible = bool(d["paused"])
        self.sample_banner.visible = not mine
        self.bots_panel.items = d["bots"]
        self.new_pb_button.visible = mine
        self.pb_panel.items = d["playbooks"]
        self.no_pb.visible = not d["playbooks"]
        self.hb_panel.items = [dict(h, ping_base=d["ping_base"]) for h in d["heartbeats"]]
        self.no_hb.visible = not d["heartbeats"]
        self.log_part.visible = bool(d["log"])
        self.log_panel.items = d["log"]
        self.no_log.visible = not d["log"]

    def _changed(self, **event_args):
        self._load()

    def _edit_playbook(self, playbook=None, **event_args):
        if alert(PlaybookForm(bots=self.d, playbook=playbook), buttons=[], role="app-dialog", large=True, dismissible=True):
            state.toast("Playbook saved", "ok")
            self._load()

    @handle("new_pb_button", "click")
    def new_pb_button_click(self, **event_args):
        self._edit_playbook(None)

    @handle("new_hb_button", "click")
    def new_hb_button_click(self, **event_args):
        if alert(HeartbeatForm(), buttons=[], role="app-dialog", dismissible=True):
            state.toast("Heartbeat ready: copy its URL into your job", "ok")
            self._load()

    @handle("add_button", "click")
    def add_button_click(self, **event_args):
        add_site()
