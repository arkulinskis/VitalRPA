from anvil import *

from ._anvil_designer import RobotCardTemplate
from ... import state, vr


class RobotCard(RobotCardTemplate):
    """Robots: one built-in robot (what it does, its schedule, last run, next run or what it covers)."""

    def __init__(self, **properties):
        super().__init__(**properties)
        b, n = self.item, self.dom_nodes
        n["icon"].className = "ic ic-" + (b.get("icon") or "robot")
        n["name"].textContent = b.get("name") or ""
        n["cron"].textContent = b.get("cron") or ""
        n["does"].textContent = b.get("does") or ""
        fleet = b.get("fleet") or ""
        if b.get("key") == "beacon":
            fleet = ("last page view " + state.ago(b["last_beat"])) if b.get("last_beat") else "no snippet installed yet"
            last = "listening"
        else:
            last = ("%s \u00b7 %s" % (state.ago(b["last"]["at"]), vr.ms(b["last"].get("ms")))) if b.get("last") else "not run yet"
        n["last"].textContent = last
        n["next"].textContent = ("next " + vr.until(b["next"])) if b.get("next") else fleet
