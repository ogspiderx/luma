from textual.theme import Theme

from .branding import DAY, NIGHT


def _build(name, palette, dark):
    return Theme(
        name=name,
        dark=dark,
        background=palette["ground"],
        surface=palette["surface"],
        panel=palette["panel"],
        boost=palette["boost"],
        foreground=palette["text"],
        primary=palette["light"],
        accent=palette["glow"],
        secondary=palette["support"],
        success=palette["good"],
        warning=palette["caution"],
        error=palette["bad"],
        variables={
            "block-cursor-foreground": palette["ground"],
            "block-cursor-background": palette["light"],
            "input-selection-background": palette["selection"],
            "footer-key-foreground": palette["glow"],
            "border": palette["rule"],
            "scrollbar": palette["track"],
            "scrollbar-hover": palette["track_hover"],
            "scrollbar-active": palette["light"],
        },
    )


LUMA_NIGHT = _build("luma-night", NIGHT, dark=True)
LUMA_DAY = _build("luma-day", DAY, dark=False)

THEMES = (LUMA_NIGHT, LUMA_DAY)

DEFAULT_THEME = LUMA_NIGHT.name

THEME_NAMES = tuple(theme.name for theme in THEMES)


def register(app):
    for theme in THEMES:
        try:
            app.register_theme(theme)
        except Exception:
            pass
