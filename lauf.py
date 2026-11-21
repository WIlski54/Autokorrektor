"""Startet die Verfahren für alle oder einzelne Fotos. Vorhandene Ergebnisse bleiben stehen."""
import argparse
import importlib
import json
import tomllib
from pathlib import Path

from dotenv import load_dotenv

from korrektor import ergebnis

WURZEL = Path(__file__).parent
# Verfahren -> Eintrag unter [modelle], der gesetzt sein muss
VERFAHREN = {"gemini": "gemini", "claude": "claude", "gpt": "gpt",
             "vision_kombi": "vision_analyse", "gemini_vision": "gemini"}


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
    bilder = sorted(p for p in (WURZEL / "fotos").glob("*")
                    if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    if args.bild:
        bilder = [b for b in bilder if b.name in args.bild]
    if not bilder:
        parser.error("keine passenden Fotos in fotos/ gefunden")

    for name in args.verfahren or list(VERFAHREN):
        if not einst["modelle"].get(VERFAHREN[name]):
            print(f"{name}: kein Modell eingetragen, übersprungen")
            continue
        modul = importlib.import_module(f"korrektor.verfahren.{name}")
        if not hasattr(modul, "ausfuehren"):
            print(f"{name}: noch nicht umgesetzt, übersprungen")
            continue
        for bildpfad in bilder:
            ziel = ergebnis.pfad(WURZEL, name, bildpfad.name)
            if ziel.exists() and not args.neu and not _ist_ausfall(ziel):
                print(f"{name} {bildpfad.name}: vorhanden")
                continue
            try:
                erg = modul.ausfuehren(bildpfad, einst)
            except Exception as fehler:  # z. B. defektes Foto
                print(f"{name} {bildpfad.name}: nicht ausführbar ({fehler})")
                continue
            ergebnis.speichern(WURZEL, erg)
            _klicks_loeschen(name, bildpfad)
            status = erg["fehlermeldung"] or f"{len(erg['funde'])} Funde"
            print(f"{name} {bildpfad.name}: {status} ({erg['dauer_s']} s)")


def _ist_ausfall(ziel):
    """Ausgefallene Läufe werden beim nächsten Start automatisch wiederholt."""
    return bool(json.loads(ziel.read_text(encoding="utf-8")).get("fehlermeldung"))


def _klicks_loeschen(name, bildpfad):
    """Ein neues Ergebnis hat andere Funde; alte Klicks dazu würden falsch zugeordnet."""
    datei = WURZEL / "pruefseite" / "klicks.json"
    if not datei.exists():
        return
    klicks = json.loads(datei.read_text(encoding="utf-8"))
    vorsilbe = f"{name}/{bildpfad.stem}/"
    bereinigt = {k: v for k, v in klicks.items() if not k.startswith(vorsilbe)}
    if len(bereinigt) != len(klicks):
        datei.write_text(json.dumps(bereinigt, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
