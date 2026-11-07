from anvil import *

from ._anvil_designer import CheckRowTemplate
from ... import vr


class CheckRow(CheckRowTemplate):
    """Site -> Checks: one robot visit."""

    def __init__(self, **properties):
        super().__init__(**properties)
        c, n = self.item, self.dom_nodes
        st = "down" if not c.get("ok") else "slow" if c.get("slow") else "up"
        n["at"].textContent = vr.stamp(c.get("at"))
        n["badge"].className = "ui-badge vr-st s-" + st
        n["led"].className = "vr-led s-" + st
        n["st"].textContent = vr.STATUS[st]
        n["code"].textContent = str(c.get("code") or vr.DASH)
        n["ms"].textContent = vr.ms(c.get("ms"))
        n["src"].textContent = c.get("source") or "robot"
        n["err"].textContent = c.get("error") or ""
