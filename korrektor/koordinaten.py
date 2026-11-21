"""Rechnet die Koordinatenformate der Dienste in [x, y, breite, hoehe] in Pixeln um."""


def gemini_zu_pixel(box, groesse):
    """Gemini: [ymin, xmin, ymax, xmax], normiert auf 0–1000."""
    ymin, xmin, ymax, xmax = box
    b, h = groesse
    return [xmin / 1000 * b, ymin / 1000 * h, (xmax - xmin) / 1000 * b, (ymax - ymin) / 1000 * h]


def anteil_zu_pixel(box, groesse):
    """Claude und GPT: [x, y, breite, hoehe] als Anteile 0–1."""
    x, y, breite, hoehe = box
    b, h = groesse
    return [x * b, y * h, breite * b, hoehe * h]


def ecken_zu_rahmen(ecken, faktor):
    """Cloud Vision: Eckpunkte im verkleinert gesendeten Bild; faktor = gesendet / original."""
    xs = [x / faktor for x, _ in ecken]
    ys = [y / faktor for _, y in ecken]
    return [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]


def vereinigen(rahmenliste):
    x1 = min(r[0] for r in rahmenliste)
    y1 = min(r[1] for r in rahmenliste)
    x2 = max(r[0] + r[2] for r in rahmenliste)
    y2 = max(r[1] + r[3] for r in rahmenliste)
    return [x1, y1, x2 - x1, y2 - y1]


def luecke(links, rechts):
    """Rahmen für die Lücke nach dem Wort `links`. `rechts` ist das Folgewort oder None."""
    lx, ly, lb, lh = links
    ende = lx + lb
    if rechts is not None:
        rx, ry, _, _ = rechts
        if rx > ende and abs(ry - ly) < lh * 0.6:
            return [ende, ly, rx - ende, lh]
    return [ende, ly, lh * 0.3, lh]
