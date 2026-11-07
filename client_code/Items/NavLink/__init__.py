from anvil import *

from ._anvil_designer import NavLinkTemplate
from ... import router, state


class NavLink(NavLinkTemplate):
    """A main-menu link (header and phone tab bar). item = {page, label, icon, on, count} from router.NAV; count = open
    incidents (red badge on Incidents)."""

    def __init__(self, **properties):
        super().__init__(**properties)
        state.set_attr(self, "href", router.href(self.item["page"]))
        self.icon.classes.add("ic-" + self.item["icon"])
        self.classes["on"] = bool(self.item.get("on"))
        if self.item.get("on"):
            state.set_attr(self, "aria-current", "page")
        n = self.item.get("count") or 0
        c = self.dom_nodes["count"]
        c.textContent = str(n)
        c.hidden = not n
        c.setAttribute("aria-label", "%d open" % n)
