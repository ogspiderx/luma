"""
Spacing that suits the window it is in.

Textual's stylesheet has no media queries, so the only way to change a
padding when the terminal changes shape is to put a class on something every
rule can see and let the stylesheet key off it. Every Luma screen mixes this
in; the class lands on the screen itself, so a rule reads:

    Screen.-narrow #main-body { padding: 0 1; }

Three sizes, not five. The gaps are a scale -- 1 line between blocks, 2 at
the widest -- rather than a number chosen per widget, which is what made the
old layout look different at every size.
"""

#: Below this many columns, side gutters shrink and optional text is dropped.
NARROW_COLUMNS = 88

#: At or above this many columns there is room to breathe properly.
ROOMY_COLUMNS = 132

#: Below this many rows, vertical gaps close up so the list stays usable.
SHORT_ROWS = 26

SIZE_CLASSES = ("-narrow", "-roomy", "-short")


def classes_for(width, height):
    """Which size classes a window of this shape should carry."""
    wanted = set()
    if width < NARROW_COLUMNS:
        wanted.add("-narrow")
    elif width >= ROOMY_COLUMNS:
        wanted.add("-roomy")
    if height < SHORT_ROWS:
        wanted.add("-short")
    return wanted


class SizeAware:
    """Keeps the size classes on a screen up to date.

    Mix in before `Screen`, and call `apply_size_classes()` from `on_mount`
    so a screen opened at an unusual size is right from its first frame
    rather than only after the window is next resized.
    """

    def apply_size_classes(self, width=None, height=None) -> None:
        if width is None or height is None:
            size = self.app.size
            width, height = size.width, size.height
        wanted = classes_for(width, height)
        for name in SIZE_CLASSES:
            self.set_class(name in wanted, name)

    def on_resize(self, event) -> None:
        self.apply_size_classes(event.size.width, event.size.height)
