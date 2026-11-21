from anvil import *

from ._anvil_designer import LandingTemplate
from ... import router, state
from ..Checkup import clean_host

# The app's video on the Addanapp YouTube channel (APP_MAKER/youtube/manifest.json), shown in the Watch section.
YT_VIDEO = "W0yKLujjtPk"


class Landing(LandingTemplate):
    """#landing (Persuade), also "About" for members: the promise, the console at work (a robot sweeps the fleet while
    a playbook handles an outage; plain HTML/CSS so it follows light/dark), the Watch section, how it works, what the
    robots check, why the beacon is light, questions. Static copy lives in the template."""

    def __init__(self, args=(), **properties):
        super().__init__(**properties)
        me = state.me()
        self.guest_cta.visible = not me
        self.member_cta.visible = bool(me)
        if me:
            state.set_attr(self.band_link, "href", "#home")
            self.dom_nodes["band_text"].textContent = "Open the console"
        self.dom_nodes["yt_cover"].addEventListener("click", self._play)
        state.set_control_attr(self.check_box, "aria-label", "Website address to check")
        state.set_control_attr(self.check_box, "inputmode", "url")
        state.set_control_attr(self.check_box, "autocomplete", "off")

    def _check(self):
        host = clean_host(self.check_box.text)
        router.go("checkup", host) if host else router.go("checkup")

    @handle("check_button", "click")
    def check_button_click(self, **event_args):
        self._check()

    @handle("check_box", "pressed_enter")
    def check_box_pressed_enter(self, **event_args):
        self._check()

    def _play(self, event):
        """Swap the video's cover for YouTube's player (privacy-enhanced); nothing loads from YouTube before this click."""
        self.dom_nodes["yt_frame"].innerHTML = (
            '<iframe src="https://www.youtube-nocookie.com/embed/' + YT_VIDEO + '?autoplay=1&rel=0&playsinline=1" '
            'title="VitalRPA video" allow="autoplay; encrypted-media; picture-in-picture; fullscreen" allowfullscreen '
            'referrerpolicy="strict-origin-when-cross-origin"></iframe>')
