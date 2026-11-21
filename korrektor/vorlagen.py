"""Zerlegt eine Vorlage mit Markierungen in Abschreibtext, Fehlerliste und Fallen."""
import re

MUSTER = re.compile(r"\[(R|Z|Gr):([^|\]]+)\|([^\]]+)\]|\{([^}]+)\}")


def parsen(markup: str) -> dict:
    teile, fehler, fallen = [], [], []
    pos = 0
    for m in MUSTER.finditer(markup):
        teile.append(markup[pos:m.start()])
        if m.group(1):
            fehler.append({
                "id": len(fehler) + 1,
                "kategorie": m.group(1),
                "falsch": m.group(2),
                "richtig": m.group(3),
            })
            teile.append(m.group(2))
        else:
            fallen.append(m.group(4))
            teile.append(m.group(4))
        pos = m.end()
    teile.append(markup[pos:])
    return {"soll_text": "".join(teile).strip(), "fehler": fehler, "fallen": fallen}
