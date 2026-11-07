from anvil import *

from ._anvil_designer import LogLineTemplate
from ... import vr


class LogLine(LogLineTemplate):
    """Console robot log: one line (time, coloured dot, which robot, what happened)."""

    def __init__(self, **properties):
        super().__init__(**properties)
        i, n = self.item, self.dom_nodes
        n["line"].className = "cn-line " + (i.get("level") or "ok")
        n["at"].textContent = vr.hhmm(i.get("at"))
        n["bot"].textContent = i.get("bot") or ""
        n["text"].textContent = " " + (i.get("text") or "")
