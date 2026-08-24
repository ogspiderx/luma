"""
Luma's own colours.

The name means light, so the palette is built around one: a warm gold that
falls on a deep, slightly violet ink. Gold is reserved for the things that are
actually happening -- the bar as it fills, the link box under the cursor -- so
attention goes where the work is. Everything structural stays quiet.

Two versions of the same idea, so the app looks deliberate in a dark room and
on a bright screen, rather than inheriting whatever the terminal happened to
be set to.
"""

from textual.theme import Theme

#: Night: ink and gold.
LUMA_NIGHT = Theme(
    name="luma-night",
    dark=True,
    # Deep ink with a violet cast, so black areas have some warmth.
    background="#12111A",
    surface="#1B1A26",
    panel="#252435",
    boost="#2E2C40",
    foreground="#EDEAF5",
    # The light itself.
    primary="#E5B54D",
    accent="#F2C55C",
    # A quiet violet for anything supporting.
    secondary="#9B8CE0",
    success="#5FB98F",
    warning="#E8A24B",
    error="#E06C75",
    variables={
        "block-cursor-foreground": "#12111A",
        "block-cursor-background": "#E5B54D",
        "input-selection-background": "#9B8CE0 35%",
        "footer-key-foreground": "#F2C55C",
        "border": "#2E2C40",
        "scrollbar": "#252435",
        "scrollbar-hover": "#3A3850",
        "scrollbar-active": "#E5B54D",
    },
)

#: Day: warm paper and a deeper gold, so the same character survives daylight.
LUMA_DAY = Theme(
    name="luma-day",
    dark=False,
    background="#FBF9F4",
    surface="#FFFFFF",
    panel="#F1ECE1",
    boost="#E8E1D2",
    foreground="#2A2735",
    # Darkened so it still reads as gold against paper.
    primary="#A87C1F",
    accent="#C2942C",
    secondary="#6B5CB8",
    success="#3D8F6A",
    warning="#B87A22",
    error="#C0504D",
    variables={
        "block-cursor-foreground": "#FBF9F4",
        "block-cursor-background": "#A87C1F",
        "input-selection-background": "#6B5CB8 25%",
        "footer-key-foreground": "#A87C1F",
        "border": "#DCD4C4",
        "scrollbar": "#E8E1D2",
        "scrollbar-hover": "#D8CFBC",
        "scrollbar-active": "#A87C1F",
    },
)

THEMES = (LUMA_NIGHT, LUMA_DAY)

#: What a fresh install opens with.
DEFAULT_THEME = LUMA_NIGHT.name


def register(app):
    """Make Luma's themes available to the app. Never raises."""
    for theme in THEMES:
        try:
            app.register_theme(theme)
        except Exception:                              # noqa: BLE001
            pass
