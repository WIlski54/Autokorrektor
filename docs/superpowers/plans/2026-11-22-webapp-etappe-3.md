# Korrektor-Web-App, Etappe 3: Ausgabe und Übersicht – Umsetzungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bestätigte Arbeiten als PDF ausgeben (einzeln und als Sammel-PDF) und eine Stapelübersicht mit Fehlerarten und häufigen Fehlerwörtern anzeigen und als CSV exportieren.

**Architecture:** `webapp/ausgabe.py` zeichnet je Seite ein Bild aus Originalfoto, Unterstreichungen und angefügter Randspalte und fasst die Seiten mit Pillow zu einem PDF zusammen (keine neue Abhängigkeit). `webapp/uebersicht.py` berechnet die Zahlen der Stapelübersicht als reine Funktion über Daten aus dem Speicher. Beides hängt an neuen Routen; die Oberfläche bekommt Knöpfe und eine Übersichtsseite.

**Tech Stack:** wie bisher (Flask, sqlite3, Pillow, einfaches JavaScript).

**Spezifikation:** `docs/superpowers/specs/2026-11-22-webapp-design.md` (Abschnitte 4.2, 5.4, 5.6, 5.7, 8, 9)

**Regeln für die Umsetzung:** wie in den Plänen zu Etappe 1 und 2. Die 510 vorhandenen Tests müssen grün bleiben. Keine Note, kein Fehlerquotient als Bewertung, keine Rangfolge, keine Schülernamen. Die Ausgabe zeigt nicht, ob ein Zeichen von der KI stammt.

## Schnittstellen (verbindlich)

### `webapp/ausgabe.py`

```
seite_zeichnen(bild, zeichen, vorschlag_zeigen=False, kopf="", uebersicht=None) -> PIL.Image
arbeit_als_pdf(speicher, arbeit_id) -> bytes            RegelFehler, wenn die Arbeit nicht bestätigt ist
aufgabe_als_pdf(speicher, aufgabe_id) -> (bytes, enthalten, fehlend)   RegelFehler, wenn keine Arbeit bestätigt ist
randzeilen(zeichen) -> [[zeichen, ...], ...]            Zeichen nach Textzeilen gruppiert, je Zeile in Lesereihenfolge
```

- `bild` ist das aufrecht gedrehte Originalfoto als `PIL.Image`; es wird nicht verändert, die Ausgabe ist ein neues Bild.
- Berücksichtigt werden nur Zeichen mit Status `bestaetigt`.
- **Im Text:** `wort` als Unterstreichung in der Farbe der Kategorie knapp unter der Unterkante des Rahmens über dessen Breite; `luecke` als Einfügezeichen (nach oben offener Winkel) an der Unterkante der Lücke. Strichstärke abhängig von der Bildgröße (etwa 0,25 % der Bildbreite, mindestens 2 px).
- **Randspalte:** rechts angefügt, Breite 16 % der Bildbreite (mit „richtige Schreibung zeigen“ 28 %), weißer Grund, dünne Trennlinie. Je Textzeile stehen die Kürzel auf Höhe der Zeile nebeneinander in Lesereihenfolge. Zeichen gehören zur selben Textzeile, wenn sich ihre senkrechten Bereiche zu mehr als der Hälfte der kleineren Höhe überlappen. Ist „richtige Schreibung zeigen“ eingeschaltet, steht der Vorschlag klein neben dem Kürzel; passt er nicht, wird er mit „…“ gekürzt. Bei mehr Einträgen als Platz in einer Zeile wird umbrochen; überlappen dadurch zwei Zeilen, rückt die untere nach unten.
- **Kopf:** eine Zeile über dem Foto mit Aufgabentitel, Kürzel der Arbeit und „Seite n von m“.
- **Fehlerübersicht:** auf der letzten Seite einer Arbeit ein Kasten unter dem Foto mit der Anzahl je Kategorie (nur Kategorien mit mindestens einem Zeichen, R, Z, Gr zuerst, dann eigene Kürzel alphabetisch) und der Summe. Kein Quotient, keine Bewertung.
- **Farben:** je Kategorie wie in der Korrekturansicht (R rot, Z blau, Gr violett, eigene Kürzel petrol).
- **Schrift:** eine skalierbare Schrift mit Umlauten und ß; zuerst eine gängige Systemschrift versuchen (z. B. Segoe UI, Arial, DejaVu Sans), sonst die skalierbare Standardschrift von Pillow. Schriftgröße abhängig von der Bildbreite.
- **PDF:** je Seite ein Bild, Seitenfolge Arbeit für Arbeit in Stapelreihenfolge, jede Arbeit beginnt auf einer neuen Seite. Lange Kante der eingebetteten Bilder höchstens 2400 px (größere werden verkleinert), JPEG-Qualität etwa 85.

### `webapp/uebersicht.py`

```
stapel(speicher, aufgabe_id) -> dict
als_csv(daten) -> str
```

`stapel` liefert nur aus bestätigten Arbeiten und nur bestätigte Zeichen:

```
{"arbeiten_gesamt", "arbeiten_bestaetigt",
 "kategorien": [{"kuerzel", "bezeichnung", "anzahl"}],          R, Z, Gr zuerst, dann eigene alphabetisch; nur mit anzahl > 0
 "woerter":    [{"gelesen", "vorschlag", "anzahl", "arbeiten"}], höchstens 20, nur Kategorie R mit typ wort;
                                                                 zusammengefasst ohne Beachtung der Groß-/Kleinschreibung,
                                                                 angezeigt in der häufigsten Schreibung; sortiert nach
                                                                 anzahl absteigend, dann alphabetisch; nur Einträge, die in
                                                                 mindestens 2 Arbeiten oder mindestens 2-mal vorkommen
 "arbeiten":   [{"kuerzel", "seiten", "je_kategorie": {kuerzel: anzahl}, "summe"}]}   in Stapelreihenfolge
```

`als_csv` gibt die Tabelle je Arbeit aus: Kopfzeile `Arbeit;Seiten;<Kürzel…>;Summe`, eine Zeile je bestätigter Arbeit in Stapelreihenfolge, Trennzeichen Semikolon, Zeilenende `\r\n`. Die Route liefert UTF-8 mit BOM, damit Excel Umlaute richtig liest. Zellen, die mit `=`, `+`, `-` oder `@` beginnen, bekommen ein vorangestelltes `'` (Schutz vor Formelausführung).

### Routen

| Methode und Pfad | Zweck |
|---|---|
| `GET /arbeit/<id>/pdf` | PDF der Arbeit als Download (`Arbeit-<Kürzel>.pdf`); nicht bestätigt → 409 mit verständlicher Fehlerseite |
| `GET /aufgabe/<id>/pdf` | Sammel-PDF (`<Titel>-Sammel.pdf`); keine Arbeit bestätigt → 409 mit Fehlerseite |
| `GET /aufgabe/<id>/uebersicht` | Stapelübersicht als HTML |
| `GET /aufgabe/<id>/uebersicht.csv` | Tabelle als CSV-Download |

Dateinamen im `Content-Disposition`-Kopf werden auf Buchstaben, Ziffern, Bindestrich und Unterstrich gesäubert.

## Aufgaben

### Task 1: Seite zeichnen

**Files:** Create `webapp/ausgabe.py`; Test `tests/webapp/test_ausgabe.py`

- [ ] Tests mit einem weißen Testbild und bekannten Rahmen: Ausgabebild ist um die Randspalte breiter (16 % bzw. 28 %) und um den Kopf höher; das Eingabebild bleibt unverändert; unter einem bestätigten `wort`-Rahmen liegt ein Strich in der Farbe der Kategorie über dessen Breite; offene und verworfene Zeichen hinterlassen keine farbigen Pixel; `luecke` zeichnet im Bereich der Lücke; `randzeilen` gruppiert zwei Zeichen derselben Textzeile und sortiert sie von links nach rechts, Zeichen verschiedener Zeilen von oben nach unten; die Randspalte enthält auf Höhe der Textzeile farbige Pixel; mit `uebersicht` ist das Bild um den Kasten höher; Text mit Umlauten löst keinen Fehler aus.
- [ ] Umsetzen, Commit.

### Task 2: PDF je Arbeit und Sammel-PDF

**Files:** Modify `webapp/ausgabe.py`; Test `tests/webapp/test_ausgabe.py`

- [ ] Tests: `arbeit_als_pdf` einer bestätigten zweiseitigen Arbeit liefert ein PDF (`%PDF`) mit zwei Seiten; eine nicht bestätigte Arbeit wirft `RegelFehler`; `aufgabe_als_pdf` enthält nur bestätigte Arbeiten, liefert `enthalten` und `fehlend` und die Seitenzahl ist die Summe der Seiten; ohne bestätigte Arbeit `RegelFehler`; sehr große Bilder werden auf höchstens 2400 px Kante verkleinert. Die Seitenzahl im Test ohne zusätzliche Bibliothek ermitteln (z. B. Zählen der Seitenobjekte im PDF-Text).
- [ ] Umsetzen, Commit.

### Task 3: Stapelübersicht berechnen

**Files:** Create `webapp/uebersicht.py`; Test `tests/webapp/test_uebersicht.py`

- [ ] Tests: nur bestätigte Arbeiten und bestätigte Zeichen zählen; Reihenfolge der Kategorien; Zusammenfassen der Wörter ohne Groß-/Kleinschreibung mit häufigster Schreibung; Schwelle (mindestens 2-mal oder in 2 Arbeiten); höchstens 20 Einträge; Arbeiten in Stapelreihenfolge, nicht nach Fehlerzahl; `als_csv` mit Kopfzeile, Semikolon, `\r\n` und Formelschutz.
- [ ] Umsetzen, Commit.

### Task 4: Routen und Oberfläche

**Files:** Modify `webapp/routen.py`, `webapp/vorlagen/arbeit.html`, `webapp/statisch/arbeit.js`, `webapp/vorlagen/stapel.html`, `webapp/statisch/stapel.js`, `webapp/statisch/app.css`; Create `webapp/vorlagen/uebersicht.html`; Test `tests/webapp/test_routen_ausgabe.py`

- [ ] Tests je Route: Erfolg mit richtigem Inhaltstyp und Dateinamen; 409 bei nicht bestätigter Arbeit bzw. ohne bestätigte Arbeit; 404 bei Unbekanntem; CSV mit BOM; Übersichtsseite zeigt Zahlen und nennt „n von m Arbeiten bestätigt“; Host- und Origin-Schutz greift.
- [ ] Korrekturansicht: Knopf „PDF ausgeben“, nur aktiv bei bestätigter Arbeit, sonst mit Hinweis; wird sofort inaktiv, wenn die Bestätigung verfällt.
- [ ] Stapelansicht: Knöpfe „Sammel-PDF (n von m bestätigt)“ und „Stapelübersicht“; das Sammel-PDF ist inaktiv, solange keine Arbeit bestätigt ist; je bestätigter Arbeit ein Verweis „PDF“.
- [ ] Übersichtsseite: Zahlen je Kategorie, häufige Fehlerwörter, Tabelle je Arbeit in Stapelreihenfolge, Knopf „Als CSV speichern“, Hinweis, dass nur bestätigte Arbeiten einfließen. Keine Bewertung, keine Rangfolge.
- [ ] Commit.

### Task 5: Durchlauf im Browser und Abschluss

- [ ] Mit der vorhandenen Aufgabe „Versuchsbeschreibung“: zwei Arbeiten bestätigen, PDF einer Arbeit und Sammel-PDF erzeugen und ansehen (Unterstreichungen an den richtigen Wörtern, Randspalte auf Höhe der Zeilen, Fehlerübersicht), einmal mit und einmal ohne „richtige Schreibung zeigen“; Stapelübersicht und CSV prüfen.
- [ ] Alle Tests grün, unabhängige Durchsicht, Befunde beheben, README anpassen, Commit, Zusammenführen und Push.
