"""Verfahren 1: Gemini liest, verortet und analysiert."""
import os

from google import genai
from google.genai import types

from korrektor.anweisung import RAHMEN_GEMINI
from korrektor.koordinaten import gemini_zu_pixel
from korrektor.verfahren import allein

NAME = "gemini"


def fragen(anweisung, jpeg, modell):
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    antwort = client.models.generate_content(
        model=modell,
        contents=[types.Part.from_bytes(data=jpeg, mime_type="image/jpeg"), anweisung],
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    nutzung = antwort.usage_metadata
    return antwort.text, {"eingabe": nutzung.prompt_token_count or 0,
                          "ausgabe": nutzung.candidates_token_count or 0}


def ausfuehren(bildpfad, einst):
    return allein.ausfuehren(bildpfad, NAME, einst["modelle"]["gemini"], RAHMEN_GEMINI,
                             gemini_zu_pixel, fragen, einst["max_kante"])
