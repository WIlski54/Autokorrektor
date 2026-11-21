"""Verfahren 3: GPT liest, verortet und analysiert."""
import base64

from openai import OpenAI

from korrektor.anweisung import RAHMEN_ANTEIL
from korrektor.koordinaten import anteil_zu_pixel
from korrektor.verfahren import allein

NAME = "gpt"


def fragen(anweisung, jpeg, modell):
    bild_url = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()
    antwort = OpenAI().chat.completions.create(
        model=modell,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": [
            {"type": "text", "text": anweisung},
            {"type": "image_url", "image_url": {"url": bild_url}},
        ]}],
    )
    return antwort.choices[0].message.content, {
        "eingabe": antwort.usage.prompt_tokens, "ausgabe": antwort.usage.completion_tokens}


def ausfuehren(bildpfad, einst):
    return allein.ausfuehren(bildpfad, NAME, einst["modelle"]["gpt"], RAHMEN_ANTEIL,
                             anteil_zu_pixel, fragen, einst["max_kante"])
