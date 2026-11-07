from anvil import *

from ._anvil_designer import RunRowTemplate
from ... import vr


class RunRow(RunRowTemplate):
    """Admin -> Robots: one scheduled-task run (when, robot, how long, what it did)."""

    def __init__(self, **properties):
        super().__init__(**properties)
        i = self.item
        self.dom_nodes["at"].textContent = vr.stamp(i.get("at"))
        self.dom_nodes["bot"].textContent = i.get("bot") or ""
        self.dom_nodes["took"].textContent = vr.ms(i.get("ms"))
        res = self.dom_nodes["res"]
        res.textContent = i.get("summary") or ""
        res.classList.toggle("bad", not i.get("ok"))
