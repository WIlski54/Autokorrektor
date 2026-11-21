"""Verfahren 2: Claude liest, verortet und analysiert."""
import base64

import anthropic

from korrektor.anweisung import RAHMEN_ANTEIL
from korrektor.koordinaten import anteil_zu_pixel
from korrektor.verfahren import allein

NAME = "claude"


def fragen(anweisung, jpeg, modell, json_antwort=True, max_tokens=8000):
    """`jpeg` darf None sein; dann geht nur Text an das Modell."""
    inhalt = []
    if jpeg is not None:
        inhalt.append({"type": "image", "source": {
            "type": "base64", "media_type": "image/jpeg",
            "data": base64.b64encode(jpeg).decode()}})
    inhalt.append({"type": "text", "text": anweisung})
    antwort = anthropic.Anthropic().messages.create(
        model=modell, max_tokens=max_tokens,
        messages=[{"role": "user", "content": inhalt}])
    text = "".join(block.text for block in antwort.content if block.type == "text")
    return text, {"eingabe": antwort.usage.input_tokens,
                  "ausgabe": antwort.usage.output_tokens}


def ausfuehren(bildpfad, einst):
    return allein.ausfuehren(bildpfad, NAME, einst["modelle"]["claude"], RAHMEN_ANTEIL,
                             anteil_zu_pixel, fragen, einst["max_kante"])
