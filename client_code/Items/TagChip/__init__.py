from anvil import *

from ._anvil_designer import TagChipTemplate
from ... import state


class TagChip(TagChipTemplate):
    """Console filter chip: "all" or "#tag"; raises x-tag on the panel."""

    def __init__(self, **properties):
        super().__init__(**properties)
        g = self.item["tag"]
        self.chip.text = "all" if g == "all" else "#" + g
        self.chip.role = ["cn-chip", "on"] if self.item.get("on") else ["cn-chip"]
        state.set_control_attr(self.chip, "aria-pressed", "true" if self.item.get("on") else "false")
        state.set_control_attr(self.chip, "data-key", g)

    @handle("chip", "click")
    def chip_click(self, **event_args):
        self.parent.raise_event("x-tag", tag=self.item["tag"])
