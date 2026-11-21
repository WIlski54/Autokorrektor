"""Startet die Verfahren für alle oder einzelne Fotos. Vorhandene Ergebnisse bleiben stehen."""
import argparse
import importlib
import tomllib
from pathlib import Path

from dotenv import load_dotenv

from korrektor import ergebnis

WURZEL = Path(__file__).parent
# Verfahren -> Eintrag unter [modelle], der gesetzt sein muss
VERFAHREN = {"gemini": "gemini", "claude": "claude", "gpt": "gpt",
             "vision_kombi": "vision_analyse"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verfahren", choices=list(VERFAHREN), action="append",
                        help="mehrfach angebbar; ohne Angabe laufen alle")
    parser.add_argument("--bild", action="append",
                        help="Dateiname in fotos/, mehrfach angebbar; ohne Angabe alle")
    parser.add_argument("--neu", action="store_true", help="vorhandene Ergebnisse überschreiben")
    args = parser.parse_args()

    load_dotenv(WURZEL / ".env")
    einst = tomllib.loads((WURZEL / "einstellungen.toml").read_text(encoding="utf-8"))
    bilder = sorted((WURZEL / "fotos").glob("*.jpg"))
    if args.bild:
        bilder = [b for b in bilder if b.name in args.bild]
    if not bilder:
        parser.error("keine passenden Fotos in fotos/ gefunden")

    for name in args.verfahren or list(VERFAHREN):
        if not einst["modelle"].get(VERFAHREN[name]):
            print(f"{name}: kein Modell eingetragen, übersprungen")
            continue
        modul = importlib.import_module(f"korrektor.verfahren.{name}")
        for bildpfad in bilder:
            if ergebnis.pfad(WURZEL, name, bildpfad.name).exists() and not args.neu:
                print(f"{name} {bildpfad.name}: vorhanden")
                continue
            erg = modul.ausfuehren(bildpfad, einst)
            ergebnis.speichern(WURZEL, erg)
            status = erg["fehlermeldung"] or f"{len(erg['funde'])} Funde"
            print(f"{name} {bildpfad.name}: {status} ({erg['dauer_s']} s)")


if __name__ == "__main__":
    main()
