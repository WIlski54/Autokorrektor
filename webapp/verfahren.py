"""Die wählbaren Analyseverfahren: Anzeigename, nötige Schlüssel und Modelleintrag.

Die einzige Stelle, an der diese Zuordnung steht. Der Wert ist zugleich der Name des
Moduls unter `korrektor.verfahren`.
"""
import os

VERFAHREN = {
    "gemini": {
        "name": "Gemini Carbon (empfohlen)",
        "schluessel": ("GEMINI_API_KEY",),
        "modell": "gemini",
    },
    "gemini_vision": {
        "name": "Gemini Carbon mit Cloud-Vision-Rahmen",
        "schluessel": ("GEMINI_API_KEY", "GOOGLE_VISION_API_KEY"),
        "modell": "gemini",
    },
    "gpt": {
        "name": "GPT",
        "schluessel": ("OPENAI_API_KEY",),
        "modell": "gpt",
    },
    "claude": {
        "name": "Claude",
        "schluessel": ("ANTHROPIC_API_KEY",),
        "modell": "claude",
    },
}
VOREINSTELLUNG = "gemini"


def anzeigename(verfahren):
    eintrag = VERFAHREN.get(verfahren)
    return eintrag["name"] if eintrag else verfahren


def hindernis(verfahren, einst):
    """Warum mit diesem Verfahren keine Analyse starten kann; None, wenn alles da ist."""
    eintrag = VERFAHREN.get(verfahren)
    if eintrag is None:
        return f"Das Verfahren „{verfahren}“ ist nicht bekannt. Bitte in der Aufgabe ein anderes wählen."
    fehlend = [name for name in eintrag["schluessel"] if not os.environ.get(name, "").strip()]
    if fehlend:
        if len(fehlend) == 1:
            was = f"fehlt der Schlüssel {fehlend[0]}"
        else:
            was = f"fehlen die Schlüssel {' und '.join(fehlend)}"
        return (f"Für das Verfahren „{eintrag['name']}“ {was} in der Datei .env. "
                "Bitte dort eintragen und die App neu starten, oder in der Aufgabe ein "
                "anderes Verfahren wählen.")
    modelle = (einst or {}).get("modelle") or {}
    if not str(modelle.get(eintrag["modell"]) or "").strip():
        return (f"Für das Verfahren „{eintrag['name']}“ ist in einstellungen.toml unter "
                f"[modelle] kein Modell für „{eintrag['modell']}“ eingetragen.")
    kante = (einst or {}).get("max_kante")
    if type(kante) is not int or kante <= 0:
        return ("In einstellungen.toml fehlt der Eintrag max_kante (längste Bildkante in "
                "Pixeln, mit der Fotos an die Dienste gehen), etwa: max_kante = 2400. "
                "Bitte dort eintragen und die App neu starten.")
    return None
