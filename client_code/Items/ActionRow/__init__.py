from anvil import *

from ._anvil_designer import ActionRowTemplate
from ... import vr

ICON = {"email": "mail", "webhook": "link", "recheck": "refresh"}


class ActionRow(ActionRowTemplate):
    """Robots -> What the robots did: one action (when, playbook, about, did, result)."""

    def __init__(self, **properties):
        super().__init__(**properties)
        l, n = self.item, self.dom_nodes
        n["at"].textContent = vr.stamp(l.get("at"))
        n["pb"].textContent = l.get("playbook") or ""
        n["about"].textContent = l.get("subject") or ""
        n["icon"].className = "ic ic-" + ICON.get(l.get("action"), "zap")
        n["did"].textContent = " " + (l.get("action") or "")
        n["res"].textContent = l.get("result") or ""
        n["res"].classList.toggle("bad", not l.get("ok"))
