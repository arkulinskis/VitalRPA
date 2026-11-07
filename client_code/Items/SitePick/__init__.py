from anvil import *

from ._anvil_designer import SitePickTemplate


class SitePick(SitePickTemplate):
    """Status page editor: a site to show on the page (tick box, name, address)."""

    def __init__(self, **properties):
        super().__init__(**properties)
        self.box.text = self.item["name"]
        self.box.checked = bool(self.item.get("on"))
        self.dom_nodes["host"].textContent = self.item.get("host") or ""

    def picked(self):
        return bool(self.box.checked)
