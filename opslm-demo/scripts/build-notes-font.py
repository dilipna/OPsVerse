"""Reproduce the static PDF font from the existing licensed Inter web font.

Requires fonttools[woff]; run from opslm-demo. The OFL remains in
public/fonts/Inter-OFL.txt. No font download or runtime conversion is used.
"""

from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

font = TTFont("public/fonts/Inter.woff2")
font = instantiateVariableFont(font, {"wght": 400, "opsz": 14}, inplace=True)
font.flavor = None
font.save("public/fonts/Inter-Notes.ttf")
