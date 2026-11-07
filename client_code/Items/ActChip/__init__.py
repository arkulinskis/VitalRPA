from anvil import *

from ._anvil_designer import ActChipTemplate

ACT = {"email": ("mail", "Email"), "webhook": ("link", "Webhook"), "recheck": ("refresh", "Recheck")}


class ActChip(ActChipTemplate):
    """Robots -> playbook: one action (email to whom, which webhook, a second-robot recheck)."""

    def __init__(self, **properties):
        super().__init__(**properties)
        a, n = self.item, self.dom_nodes
        t = a.get("type")
        label = (a.get("to") or "my alert email") if t == "email" else (a.get("url") or "").replace("https://", "") if t == "webhook" else "second robot"
        icon, name = ACT.get(t, ("zap", t or ""))
        n["chip"].setAttribute("title", label)
        n["icon"].className = "ic ic-" + icon
        n["text"].textContent = "%s: %s" % (name, label)
