"""Berechnet die Messgrößen und schreibt bericht.html."""
import tomllib
from pathlib import Path

from korrektor import bild
from korrektor.auswertung import alles
from korrektor.bericht import html

WURZEL = Path(__file__).parent


def main():
    einst = tomllib.loads((WURZEL / "einstellungen.toml").read_text(encoding="utf-8"))
    auswertung = alles(WURZEL)
    ordner = WURZEL / "bericht_bilder"
    ordner.mkdir(exist_ok=True)
    ausschnitte = {}
    for name, teil in auswertung.items():
        for bildname, fund in teil["erfundene"]:
            ziel = ordner / f"{name}_{Path(bildname).stem}_{fund['id']}.jpg"
            try:
                ziel.write_bytes(bild.ausschnitt(WURZEL / "fotos" / bildname,
                                                 fund["anker"]["rahmen"], rand=0.5))
            except (OSError, ValueError):  # Foto fehlt oder Rahmen unbrauchbar
                continue
            ausschnitte[(name, bildname, fund["id"])] = f"bericht_bilder/{ziel.name}"
    (WURZEL / "bericht.html").write_text(html(auswertung, einst["schwellen"], ausschnitte),
                                         encoding="utf-8")
    print(f"bericht.html geschrieben ({len(auswertung)} Verfahren)")


if __name__ == "__main__":
    main()
