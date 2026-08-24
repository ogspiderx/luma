"""
Everything that makes Luma look like Luma.

Rebranding is meant to be a one-file job. Change the name, the wordmark and
the colours below and the whole interface follows: the bar across the top,
both themes, every accent, and the words the app greets you with. Nothing
else in the codebase hard-codes a colour or the product name.

The palette is one idea in two moods. LIGHT is the brand colour -- the thing
the eye is meant to land on -- and it is spent only on what is actually
happening: the bar as it fills, the box under the cursor, the answer being
asked for. Everything structural stays quiet.
"""

#: The product name, used in the window title and anywhere it is spoken of.
NAME = "Luma"

#: How the name is set across the top. Short; it is read, not narrated.
WORDMARK = "LUMA"

#: What the link box suggests before anything is typed. The whole of the
#: instruction for a first-time user lives here, so there is no second line
#: of explanation cluttering the screen.
LINK_PLACEHOLDER = "Paste a YouTube link and press Enter"

#: Names for the two themes, as a person would choose between them.
NIGHT_LABEL = "Night - ink and gold"
DAY_LABEL = "Day - paper and gold"


# --------------------------------------------------------------------------- #
#  The palette                                                                 #
# --------------------------------------------------------------------------- #
#
#  ground   the deepest surface, what the app sits on
#  surface  a raised block: a row in the list, the settings panel
#  panel    a quiet edge or an inactive control
#  boost    a hover, or a moment's highlight
#  text     ordinary reading colour
#  light    the brand colour, on what is happening now
#  glow     a brighter cast of the brand colour, for focus
#  support  a second colour, for anything secondary
#
#  Any two dictionaries with these keys make a working Luma.

NIGHT = {
    "ground": "#12111A",
    "surface": "#1B1A26",
    "panel": "#252435",
    "boost": "#2E2C40",
    "text": "#EDEAF5",
    "light": "#E5B54D",
    "glow": "#F2C55C",
    "support": "#9B8CE0",
    "good": "#5FB98F",
    "caution": "#E8A24B",
    "bad": "#E06C75",
    "rule": "#2E2C40",
    "track": "#252435",
    "track_hover": "#3A3850",
    "selection": "#9B8CE0 35%",
}

DAY = {
    "ground": "#FBF9F4",
    "surface": "#FFFFFF",
    "panel": "#F1ECE1",
    "boost": "#E8E1D2",
    "text": "#2A2735",
    # Darkened so it still reads as gold against paper.
    "light": "#A87C1F",
    "glow": "#C2942C",
    "support": "#6B5CB8",
    "good": "#3D8F6A",
    "caution": "#B87A22",
    "bad": "#C0504D",
    "rule": "#DCD4C4",
    "track": "#E8E1D2",
    "track_hover": "#D8CFBC",
    "selection": "#6B5CB8 25%",
}
