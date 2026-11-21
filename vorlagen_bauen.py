"""Erzeugt aus vorlagen/<X>.vorlage.txt den Abschreibtext und die Lösungsdatei."""
import json
from pathlib import Path

from korrektor.vorlagen import parsen

ORDNER = Path(__file__).parent / "vorlagen"

for vorlage in sorted(ORDNER.glob("*.vorlage.txt")):
    name = vorlage.name.removesuffix(".vorlage.txt")
    daten = parsen(vorlage.read_text(encoding="utf-8"))
    (ORDNER / f"{name}.abschreiben.txt").write_text(daten["soll_text"] + "\n", encoding="utf-8")
    (ORDNER / f"loesung_{name}.json").write_text(
        json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{name}: {len(daten['fehler'])} Fehler, {len(daten['fallen'])} Fallen")
