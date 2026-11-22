"""Verfahren 3: GPT liest, verortet und analysiert."""
import base64

from openai import OpenAI

from korrektor.anweisung import RAHMEN_ANTEIL
from korrektor.koordinaten import anteil_zu_pixel
from korrektor.verfahren import allein

NAME = "gpt"


def fragen(anweisung, jpeg, modell, json_antwort=True):
    """`jpeg` darf None sein; dann geht nur Text an das Modell."""
    inhalt = [{"type": "text", "text": anweisung}]
    if jpeg is not None:
        bild_url = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()
        inhalt.append({"type": "image_url", "image_url": {"url": bild_url}})
    zusatz = {"response_format": {"type": "json_object"}} if json_antwort else {}
    antwort = OpenAI().chat.completions.create(
        model=modell, messages=[{"role": "user", "content": inhalt}], **zusatz)
    return antwort.choices[0].message.content, {
        "eingabe": antwort.usage.prompt_tokens, "ausgabe": antwort.usage.completion_tokens}


def ausfuehren(bildpfad, einst):
    return allein.ausfuehren(bildpfad, NAME, einst["modelle"]["gpt"], RAHMEN_ANTEIL,
                             anteil_zu_pixel, fragen, einst["max_kante"],
                             aufgabe=einst.get("aufgabe"), frist=einst.get("frist"))
