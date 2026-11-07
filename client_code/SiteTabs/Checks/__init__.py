from anvil import *

from ._anvil_designer import ChecksTemplate


class Checks(ChecksTemplate):
    """Site -> Checks: the last 80 robot visits."""

    def __init__(self, site, page, **properties):
        super().__init__(**properties)
        self.checks_panel.items = site["checks"]
        self.no_checks.visible = not site["checks"]
