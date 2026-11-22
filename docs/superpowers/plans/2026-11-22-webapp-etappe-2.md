# Korrektor-Web-App, Etappe 2: Korrekturansicht und Freigabe – Umsetzungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die Leseansicht einer Arbeit wird zur Korrekturansicht: Vorschläge bestätigen, verwerfen, ändern, verschieben, eigene Zeichen setzen, „Rest bestätigen“ und die Gesamtbestätigung je Arbeit.

**Architecture:** Die Zustandsregeln aus Abschnitt 4 der Spezifikation liegen als reine Funktionen in `webapp/regeln.py`. Der Speicher bekommt die Schreibwege für Zeichen und Bestätigung; jede Änderung an Zeichen hebt die Gesamtbestätigung der Arbeit in derselben Transaktion auf. Die Oberfläche spricht mit JSON-Routen und speichert jede Änderung sofort.

**Tech Stack:** wie Etappe 1 (Flask, sqlite3, einfaches JavaScript ohne Build-Werkzeug und ohne externe Bibliotheken).

**Spezifikation:** `docs/superpowers/specs/2026-11-22-webapp-design.md` (Abschnitte 3, 4.1, 4.2, 4.3, 5.4, 5.5, 7, 9)

**Regeln für die Umsetzung:** wie in `docs/superpowers/plans/2026-11-22-webapp-etappe-1.md`. Die 238 vorhandenen Tests müssen grün bleiben.

## Schnittstellen (verbindlich)

### `webapp/regeln.py` (reine Funktionen, kein Speicher, kein Flask)

Ein Zeichen ist ein `dict` mit `kategorie, typ, x, y, breite, hoehe, gelesen, vorschlag, herkunft, status, bestaetigt_wie`. Jede Funktion gibt die zu setzenden Felder als `dict` zurück und wirft `RegelFehler(meldung)` bei einem unzulässigen Übergang.

```
einzeln_bestaetigen(z)   ki, offen                 -> {status: bestaetigt, bestaetigt_wie: einzeln}
verwerfen(z)             ki, offen oder bestaetigt -> {status: verworfen, bestaetigt_wie: None}
zurueckholen(z)          ki, verworfen oder bestaetigt -> {status: offen, bestaetigt_wie: None}
aendern(z, kategorie=None, vorschlag=None, erlaubte=...)
                         ki: geänderte Felder + {status: bestaetigt, bestaetigt_wie: geaendert};
                         hand: nur die geänderten Felder; ohne tatsächliche Änderung {}
verschieben(z, x, y, breite, hoehe, bildgroesse)
                         Rahmen ins Bild geklemmt, mindestens 4 px je Kante; Status unberührt
neues_handzeichen(kategorie, typ, x, y, breite, hoehe, vorschlag, erlaubte, bildgroesse)
                         -> vollständiges Zeichen mit herkunft hand, status bestaetigt, bestaetigt_wie None
loeschbar(z)             nur herkunft hand; sonst RegelFehler („KI-Vorschläge werden verworfen, nicht gelöscht“)
offene(zeichenliste)     -> ids der offenen Zeichen (für „Rest bestätigen“: status bestaetigt, bestaetigt_wie gesammelt)
bestaetigbar(seiten)     seiten: [{analyse_status, zeichen: [...]}] -> (True, "") oder (False, Grund)
zahlen(zeichenliste)     -> {einzeln, gesammelt, geaendert, verworfen, hand}
```

`erlaubte` ist die Menge zulässiger Kürzel: R, Z, Gr plus die eigenen Kürzel. Unzulässige Kategorie oder `typ` außer `wort`/`luecke` → `RegelFehler`.

### Speicher (Ergänzungen)

```
zeichen_eintrag(id) -> dict | None            mit seite_id, arbeit_id
zeichen_aendern(id, **felder)                 schreibt Felder und leert arbeit.bestaetigt_am und arbeit.bestaetigung
zeichen_anlegen(seite_id, zeichen) -> id      leert die Bestätigung der Arbeit
zeichen_loeschen(id)                          leert die Bestätigung der Arbeit
zeichen_viele_setzen(ids, **felder)           eine Transaktion; leert die Bestätigung der betroffenen Arbeit
arbeit_bestaetigen(arbeit_id, zahlen)         setzt bestaetigt_am (ISO-Zeit) und bestaetigung (JSON)
arbeit_kuerzel_setzen(arbeit_id, kuerzel)     ändert die Bestätigung nicht
kuerzel() -> [{kuerzel, bezeichnung}]         eigene Kürzel; Voreinstellung A Ausdruck, Sb Satzbau, T Tempus, W Wortwahl, I Inhalt
kuerzel_setzen(liste)                         R, Z, Gr sind als eigene Kürzel nicht zulässig; Kürzel 1–4 Zeichen, eindeutig
```

`zeichen_ersetzen` (Neuanalyse) leert ebenfalls die Bestätigung der Arbeit, sobald es schreibt. `arbeiten()` und `arbeit()` liefern zusätzlich `bestaetigt_am`, `bestaetigung` (als `dict`) und `bestaetigbar`.

### Routen (alle Antworten JSON, außer wo angegeben)

Jede schreibende Antwort enthält `{"zeichen": <aktuelles Zeichen oder null>, "arbeit": {"offen", "bestaetigt_am", "bestaetigbar", "grund"}}`. Ein `RegelFehler` ergibt 409 mit `{"fehler": meldung}`, Unbekanntes 404, ungültige Eingaben 400.

| Methode und Pfad | Zweck |
|---|---|
| `POST /zeichen/<id>/bestaetigen` | einzeln bestätigen |
| `POST /zeichen/<id>/verwerfen` | verwerfen |
| `POST /zeichen/<id>/zurueckholen` | wieder offen |
| `POST /zeichen/<id>/aendern` | `{kategorie?, vorschlag?}` |
| `POST /zeichen/<id>/rahmen` | `{x, y, breite, hoehe}` |
| `POST /zeichen/<id>/loeschen` | nur eigene Zeichen |
| `POST /seite/<id>/zeichen` | eigenes Zeichen setzen `{kategorie, typ, x, y, breite, hoehe, vorschlag?}` |
| `POST /arbeit/<id>/rest-bestaetigen` | alle offenen Zeichen der Arbeit; Antwort mit `geaendert: [ids]` |
| `GET /arbeit/<id>/zahlen` | Zahlen für den Bestätigungsdialog und `bestaetigbar` |
| `POST /arbeit/<id>/bestaetigen` | Gesamtbestätigung; 409, wenn nicht bestätigbar |
| `POST /arbeit/<id>/kuerzel` | `{kuerzel}` umbenennen (1–20 Zeichen) |
| `POST /seite/<id>/neu-analysieren` | reiht eine fertige oder fehlgeschlagene Seite neu ein (prüft Hindernis) |
| `GET, POST /einstellungen/kuerzel` | HTML-Seite zum Bearbeiten der eigenen Kürzel |
| `GET /arbeit/<id>` | Korrekturansicht (ersetzt die Leseansicht) |

## Aufgaben

### Task 1: Regeln

**Files:** Create `webapp/regeln.py`; Test `tests/webapp/test_regeln.py`

- [ ] Tests je Funktion: jeder zulässige Übergang, jeder unzulässige (z. B. eigenes Zeichen verwerfen, KI-Zeichen löschen, bereits verworfenes bestätigen ohne Zurückholen, unbekanntes Kürzel); `aendern` ohne tatsächliche Änderung liefert `{}` und lässt ein offenes Zeichen offen; `verschieben` klemmt und erzwingt die Mindestgröße; `bestaetigbar` verneint bei offenem Zeichen, bei nicht fertiger Seite und bei einer Arbeit ohne Seiten, mit lesbarem Grund; `zahlen` zählt nach `bestaetigt_wie`, Status und Herkunft.
- [ ] Umsetzen, Commit.

### Task 2: Speicher

**Files:** Modify `webapp/speicher.py`; Test `tests/webapp/test_speicher.py`

- [ ] Tests: jede neue Methode; jede Schreibmethode an Zeichen leert `bestaetigt_am` und `bestaetigung` der Arbeit; `arbeit_kuerzel_setzen` leert sie nicht; `zeichen_ersetzen` leert sie; `kuerzel()` liefert die Voreinstellung und nach `kuerzel_setzen` die neue Liste; unzulässige Kürzel werden abgelehnt; `arbeiten()` liefert `bestaetigbar`.
- [ ] Umsetzen, Commit.

### Task 3: Routen

**Files:** Modify `webapp/routen.py`; Test `tests/webapp/test_routen_korrektur.py`

- [ ] Tests je Route: Erfolg, Regelverstoß (409), Unbekanntes (404), ungültige Eingabe (400); nach jeder Änderung an einem Zeichen einer bestätigten Arbeit ist die Arbeit nicht mehr bestätigt; `bestaetigen` der Arbeit scheitert mit offenem Zeichen und gelingt nach „Rest bestätigen“; die gespeicherten Zahlen stimmen (einzeln, gesammelt, geändert, verworfen, selbst gesetzt); `neu-analysieren` erhält bestätigte, verworfene und eigene Zeichen und hebt die Bestätigung auf; Kürzel-Einstellungen speichern und lehnen R, Z, Gr ab.
- [ ] Umsetzen, Commit.

### Task 4: Korrekturansicht – anzeigen, auswählen, entscheiden

**Files:** Modify `webapp/vorlagen/arbeit.html`, `webapp/statisch/arbeit.js`, `webapp/statisch/app.css`; Test `tests/webapp/test_routen_korrektur.py`

- [ ] Darstellung: offen gestrichelt und blass, bestätigt durchgezogen, verworfen ausgeblendet (Schalter „Verworfene zeigen“), eigene Zeichen in eigener Farbe; `luecke` in eigener Form.
- [ ] Liste rechts mit Zustand je Zeichen und den Knöpfen Bestätigen, Verwerfen, Zurückholen; Auswahl in Bild und Liste gekoppelt.
- [ ] Tastatur: `N` oder `Tab` nächster offener Vorschlag, `B` oder `Enter` bestätigen, `V` oder `Entf` verwerfen, `Z` zurückholen, `E` ändern, Pfeile links/rechts Seite, `Bild auf/ab` Arbeit. Die Belegung steht sichtbar in der Ansicht. Tasten wirken nicht, solange ein Eingabefeld den Fokus hat.
- [ ] Nach Bestätigen oder Verwerfen springt die Auswahl zum nächsten offenen Vorschlag; ist auf der Seite keiner mehr offen, zur nächsten Seite mit offenen Vorschlägen.
- [ ] Zähler „n offen“ und Zustand der Arbeit aktualisieren sich aus der Antwort der Route. Schlägt das Speichern fehl, erscheint eine Meldung und der vorherige Zustand wird wiederhergestellt.
- [ ] Commit.

### Task 5: Korrekturansicht – verschieben, ändern, selbst setzen

**Files:** Modify `webapp/statisch/arbeit.js`, `webapp/vorlagen/arbeit.html`, `webapp/statisch/app.css`

- [ ] Verschieben per Ziehen des Rahmens, Größe über vier Eckpunkte (Zeigerereignisse, auch Stift und Finger); gespeichert wird beim Loslassen; die Umrechnung zwischen Bildschirm und Bildpixeln stimmt bei jedem Zoom.
- [ ] Ändern: kleines Formular am Zeichen oder in der Liste mit Kürzel (R, Z, Gr und eigene) und Vorschlag.
- [ ] Selbst setzen: Modus „Zeichen setzen“ (Taste `S`), Rahmen aufziehen, Kürzel wählen, optional Vorschlag; Abbrechen mit `Esc`. Sehr kleine Rahmen (unter 6 px Kante) werden nicht angelegt.
- [ ] Eigene Zeichen lassen sich löschen (Knopf und `Entf`).
- [ ] Commit.

### Task 6: Gesamtbestätigung, Neuanalyse, Stapelansicht, Kürzel

**Files:** Modify `webapp/vorlagen/arbeit.html`, `arbeit.js`, `stapel.html`, `stapel.js`, `aufgaben.html`; Create `webapp/vorlagen/kuerzel.html`

- [ ] Fußleiste der Korrekturansicht: „Zeichen setzen“, „Rest bestätigen“ (mit Rückfrage, die die Zahl nennt), „Korrektur gesamt bestätigen“ (erst freigeschaltet, wenn bestätigbar; sonst mit dem Grund als Hinweis), „Seite neu analysieren“ (mit Rückfrage).
- [ ] Bestätigungsdialog nennt die fünf Zahlen und verlangt eine ausdrückliche Bestätigung; danach zeigt die Ansicht „bestätigt am …“. Jede spätere Änderung entfernt die Anzeige sofort.
- [ ] Kürzel der Arbeit in der Korrekturansicht umbenennbar.
- [ ] Stapelansicht zeigt je Arbeit den Bestätigungsstatus und insgesamt „n von m Arbeiten bestätigt“; die Aufgabenliste ebenso.
- [ ] Seite „Eigene Kürzel“ unter den Einstellungen, von der Aufgabenliste erreichbar.
- [ ] Commit.

### Task 7: Durchlauf im Browser und Abschluss

- [ ] Mit der vorhandenen Aufgabe „Versuchsbeschreibung“: Vorschläge einzeln bestätigen und verwerfen (Maus und Tastatur), einen ändern, einen verschieben und in der Größe ändern, ein eigenes Zeichen setzen und löschen, „Rest bestätigen“, Gesamtbestätigung, danach ein Zeichen verschieben und prüfen, dass die Bestätigung verfällt; eine Seite neu analysieren und prüfen, dass Entschiedenes erhalten bleibt.
- [ ] Alle Tests grün, unabhängige Durchsicht, Befunde beheben, README anpassen, Commit, Zusammenführen und Push.
