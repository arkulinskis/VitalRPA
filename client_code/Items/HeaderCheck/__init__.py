from anvil import *

from ._anvil_designer import HeaderCheckTemplate


class HeaderCheck(HeaderCheckTemplate):
    """Site -> Overview -> Security headers: one header, there or missing, and why it matters."""

    def __init__(self, **properties):
        super().__init__(**properties)
        i, n = self.item, self.dom_nodes
        n["row"].className = "st-hdr " + ("ok" if i.get("ok") else "no")
        n["icon"].className = "ic " + ("ic-check" if i.get("ok") else "ic-x")
        n["state"].textContent = "present" if i.get("ok") else "missing"
        n["name"].textContent = i.get("name") or ""
        n["why"].textContent = i.get("why") or ""
