# Korrektor-Web-App, Etappe 1: Stapel und Analyse – Umsetzungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eine lokal laufende Flask-App, in der man Aufgaben anlegt, Fotos hochlädt, sie Arbeiten zuordnet, die Analyse im Hintergrund laufen lässt und den Fortschritt samt Vorschlägen sieht.

**Architecture:** Neues Paket `webapp/` neben dem vorhandenen `korrektor/`. Nur `speicher.py` kennt SQLite; die Warteschlange ruft über `analyse.py` die Verfahren aus Teilprojekt 1 auf und schreibt deren Funde als Zeichen in die Datenbank. Seiten werden serverseitig als HTML ausgeliefert, die Oberfläche nutzt einfaches JavaScript ohne Build-Werkzeug.

**Tech Stack:** Python ≥ 3.11, Flask, sqlite3 (Standardbibliothek), Pillow, pytest; vorhandene Verfahren (`korrektor.verfahren.*`).

**Spezifikation:** `docs/superpowers/specs/2026-11-22-webapp-design.md` (Abschnitte 3, 4.3, 5.1–5.4, 6, 7, 9)

**Regeln für die Umsetzung**

- Arbeitsverzeichnis ist die Projektwurzel. Tests: `.venv/Scripts/python.exe -m pytest -q`.
- Das Repository ist öffentlich. Dateien einzeln hinzufügen, nie `git add .`. `daten/`, `fotos/`, `ergebnisse/`, `.env` und Bilder bleiben draußen.
- Je Aufgabe: Test zuerst, fehlschlagen sehen, umsetzen, bestehen sehen, committen.
- Alle Texte der Oberfläche auf Deutsch. Keine Namen von Schülern, keine Bewertung, keine Rangfolge.
- Die bestehenden 49 Tests müssen grün bleiben.

## Dateiübersicht

| Datei | Aufgabe |
|---|---|
| `webapp/__init__.py` | `app_erzeugen(datenordner, verfahren_starter=None)`: Flask-App, Speicher und Warteschlange verdrahten |
| `webapp/speicher.py` | Klasse `Speicher`: einziger Ort mit SQL und Bilddateien |
| `webapp/analyse.py` | `seite_analysieren(speicher, seite_id, einst)`: Verfahren aufrufen, Funde als Zeichen speichern |
| `webapp/warteschlange.py` | Klasse `Warteschlange`: bis zu drei Seiten gleichzeitig, Zeitgrenze, Wiederaufnahme |
| `webapp/routen.py` | alle Seiten und JSON-Schnittstellen der Etappe 1 |
| `webapp/vorlagen/*.html` | `grundriss`, `aufgaben`, `aufgabe_formular`, `zuordnen`, `stapel`, `arbeit` |
| `webapp/statisch/app.css`, `zuordnen.js`, `stapel.js`, `arbeit.js` | Gestaltung und Verhalten |
| `start.py` | App starten, Browser öffnen |
| `korrektor/anweisung.py`, `korrektor/verfahren/*.py` | Anweisung um Fach, Jahrgang und Kategorien erweitern |
| `tests/webapp/test_*.py` | Tests je Baustein |

## Schnittstellen (verbindlich für alle Aufgaben)

**Datenbankschema** (`Speicher.schema_anlegen()`, alle Tabellen mit `id INTEGER PRIMARY KEY`):

- `aufgabe(titel, fach, jahrgang, kategorien TEXT '["R","Z","Gr"]', verfahren, vorschlag_in_ausgabe INTEGER, erstellt_am)`
- `ablage(aufgabe_id, bilddatei, breite, hoehe, reihenfolge, neue_arbeit INTEGER)`: hochgeladene, noch nicht zugeordnete Fotos
- `arbeit(aufgabe_id, kuerzel, reihenfolge, bestaetigt_am, bestaetigung TEXT)`
- `seite(arbeit_id, nummer, bilddatei, breite, hoehe, analyse_status, fehlermeldung, transkription, dauer_s, analysiert_am, lauf INTEGER DEFAULT 0, verworfen INTEGER DEFAULT 0)`
- `zeichen(seite_id, kategorie, typ, x, y, breite, hoehe, gelesen, vorschlag, herkunft, status, bestaetigt_wie, rahmen_ki TEXT)`
- `einstellung(schluessel TEXT UNIQUE, wert TEXT)`
- Fremdschlüssel mit `ON DELETE CASCADE`, `PRAGMA foreign_keys = ON`, `journal_mode = WAL`. Jede Methode öffnet eine eigene Verbindung (Threads der Warteschlange).

**Speicher** (Rückgaben als `dict`, Listen als `list[dict]`):

```
Speicher(datenordner)                      legt daten/korrektor.db und daten/bilder/ an
aufgabe_anlegen(titel, fach, jahrgang, kategorien, verfahren, vorschlag_in_ausgabe=False) -> id
aufgabe(id) -> dict | None                 kategorien als Liste
aufgabe_aendern(id, **felder)
aufgaben() -> list                         je Aufgabe zusätzlich: arbeiten, seiten, seiten_fertig, seiten_fehlgeschlagen, offen, bestaetigt
aufgabe_loeschen(id)                       entfernt auch alle Bilddateien der Aufgabe
bild_ablegen(aufgabe_id, dateiname, daten) -> ablage_id    dreht aufrecht, speichert als JPEG; ValueError bei unlesbarem Bild
ablage(aufgabe_id) -> list                 nach reihenfolge
ablage_ordnen(aufgabe_id, eintraege)       eintraege: [{"id", "neue_arbeit"}] in gewünschter Reihenfolge; fehlende ids werden gelöscht (samt Datei)
ablage_zu_arbeiten(aufgabe_id) -> [seite_id]   bildet Arbeiten nach den Trennmarken, Kürzel = fortlaufende zweistellige Nummer, leert die Ablage
arbeit_anlegen(aufgabe_id, bilder: [(dateiname, daten)]) -> [seite_id]   eine Arbeit aus mehreren Fotos
arbeiten(aufgabe_id) -> list               je Arbeit: seiten (Liste), offen, status_gesamt
arbeit(id) -> dict | None                  mit seiten und je Seite zeichen
seite(id) -> dict | None
seite_status(id, status, **felder)         felder: fehlermeldung, transkription, dauer_s, verworfen
seite_lauf_beginnen(id) -> lauf            erhöht lauf, setzt Status laeuft
zeichen_ersetzen(seite_id, lauf, zeichen) -> bool   schreibt nur, wenn lauf noch aktuell ist; ersetzt offene KI-Zeichen
seiten_unfertig() -> [seite_id]            Status wartet oder laeuft
bildpfad(bilddatei) -> Path
```

`status_gesamt` einer Arbeit: `fehlgeschlagen`, wenn eine Seite fehlgeschlagen ist; sonst `laeuft`, wenn eine Seite wartet oder läuft; sonst `fertig`; `neu`, wenn alle Seiten neu sind.

**Analyse:**

```
seite_analysieren(speicher, seite_id, einst) -> dict
```
Lädt Seite, Arbeit und Aufgabe, ruft `korrektor.verfahren.<aufgabe.verfahren>.ausfuehren(bildpfad, einst_mit_aufgabe)` auf und gibt `{"zeichen": [...], "transkription", "dauer_s", "verworfen", "fehlermeldung"}` zurück. Funde mit einer Kategorie, die in der Aufgabe nicht eingeschaltet ist, werden weggelassen. Jedes Zeichen: `kategorie, typ, x, y, breite, hoehe, gelesen, vorschlag, herkunft="ki", status="offen", rahmen_ki`.

`einst_mit_aufgabe` ist `einst` plus `{"aufgabe": {"fach", "jahrgang", "kategorien"}}`.

**Anweisung:** `korrektor.anweisung.anweisung(rahmenhinweis, aufgabe=None)`. Ohne `aufgabe` bleibt der Text wie bisher (Deutsch, Jahrgang 9, R, Z, Gr). Mit `aufgabe` nennt er Fach, Jahrgang und nur die eingeschalteten Kategorien. Die Verfahren reichen `einst.get("aufgabe")` durch.

**Warteschlange:**

```
Warteschlange(speicher, analysieren, gleichzeitig=3, zeitgrenze_s=240)
einreihen(seite_id)        setzt Status wartet und startet die Bearbeitung
wiederaufnehmen()          reiht alle unfertigen Seiten neu ein
warten(timeout=None)       nur für Tests: blockiert, bis alles abgearbeitet ist
```
`analysieren(seite_id) -> dict` wie von `seite_analysieren`. Ablauf je Seite: `seite_lauf_beginnen`; Analyse in einem eigenen Thread mit Zeitgrenze; bei Ergebnis ohne Fehlermeldung `zeichen_ersetzen` und Status `fertig`; bei Fehlermeldung, Ausnahme oder Zeitüberschreitung Status `fehlgeschlagen` mit lesbarer Meldung. Ein verspätetes Ergebnis eines abgelaufenen Laufs wird verworfen (Prüfung über `lauf`).

**Routen:**

| Methode und Pfad | Zweck |
|---|---|
| `GET /` | Aufgabenliste mit Fortschritt und Prototyp-Hinweis |
| `GET, POST /aufgabe/neu` | Aufgabe anlegen, danach weiter zum Hochladen |
| `GET, POST /aufgabe/<id>/bearbeiten` | Einstellungen ändern |
| `POST /aufgabe/<id>/loeschen` | Aufgabe mit allen Daten löschen |
| `GET /aufgabe/<id>` | Stapelansicht (Kacheln) |
| `GET /aufgabe/<id>/stand` | JSON für die laufende Aktualisierung |
| `GET /aufgabe/<id>/hochladen` | Hochladen und Zuordnen |
| `POST /aufgabe/<id>/ablage` | Fotos hochladen; JSON mit angenommenen und abgelehnten Dateien |
| `POST /aufgabe/<id>/ablage/ordnen` | Reihenfolge, Trennmarken, Entfernen speichern |
| `POST /aufgabe/<id>/analyse-starten` | Ablage in Arbeiten umwandeln, alle Seiten einreihen |
| `POST /aufgabe/<id>/arbeit` | einzelne Arbeit aus mehreren Fotos hinzufügen und einreihen |
| `POST /seite/<id>/erneut` | fehlgeschlagene Seite neu einreihen |
| `GET /arbeit/<id>` | Arbeit ansehen: Foto mit Rahmen der Vorschläge und Liste (nur lesend) |
| `GET /bild/seite/<id>`, `GET /bild/ablage/<id>` | Bild; `?b=<Breite>` liefert ein Vorschaubild |

Vor `analyse-starten` und `arbeit` prüft die Route, ob der Schlüssel für das Verfahren der Aufgabe gesetzt ist, und meldet einen fehlenden Schlüssel sofort.

## Aufgaben

### Task 1: Anweisung mit Fach, Jahrgang und Kategorien

**Files:** Modify `korrektor/anweisung.py`, `korrektor/verfahren/allein.py`, `gemini.py`, `gpt.py`, `claude.py`, `gemini_vision.py`, `vision_kombi.py`; Test `tests/test_anweisung.py`, `tests/test_allein.py`

- [ ] Tests: ohne `aufgabe` enthält der Text „Deutsch“, „Jahrgang 9“ und alle drei Kategorien; mit `{"fach": "Englisch", "jahrgang": 7, "kategorien": ["R"]}` enthält er „Englisch“, „7“, die Zeile zu R, aber nicht die Zeilen zu Z und Gr; `allein.ausfuehren(..., aufgabe=...)` reicht `aufgabe` an `anweisung` durch (Schein-`fragen` prüft den Text).
- [ ] Umsetzen, alle Tests grün, Commit.

### Task 2: Speicher – Schema und Aufgaben

**Files:** Create `webapp/__init__.py` (zunächst leer), `webapp/speicher.py`; Test `tests/webapp/__init__.py`, `tests/webapp/test_speicher.py`

- [ ] Tests mit `tmp_path`: Anlegen und Lesen einer Aufgabe (Kategorien als Liste); `aufgabe_aendern`; `aufgaben()` liefert Zählwerte 0 für eine leere Aufgabe; `aufgabe(999)` ist `None`.
- [ ] Umsetzen, Commit.

### Task 3: Speicher – Ablage, Arbeiten, Seiten

**Files:** Modify `webapp/speicher.py`; Test `tests/webapp/test_speicher.py`

- [ ] Tests: `bild_ablegen` speichert ein JPEG, liefert Breite und Höhe, dreht ein Bild mit EXIF-Orientierung 6 aufrecht und lehnt Nicht-Bilder mit `ValueError` ab; `ablage_ordnen` ändert Reihenfolge und Trennmarken und löscht weggelassene Einträge samt Datei; `ablage_zu_arbeiten` bildet aus fünf Fotos mit Trennmarken `[1,0,1,1,0]` drei Arbeiten mit 2, 1 und 2 Seiten, Kürzel `01`, `02`, `03`, und leert die Ablage; `arbeit_anlegen` setzt die Nummerierung fort; `aufgabe_loeschen` entfernt Zeilen aller Tabellen und alle Bilddateien.
- [ ] Umsetzen, Commit.

### Task 4: Speicher – Status, Lauf und Zeichen

**Files:** Modify `webapp/speicher.py`; Test `tests/webapp/test_speicher.py`

- [ ] Tests: `seite_lauf_beginnen` erhöht `lauf` und setzt `laeuft`; `zeichen_ersetzen` mit aktuellem Lauf schreibt und gibt `True` zurück, mit veraltetem Lauf schreibt nichts und gibt `False` zurück; beim Ersetzen bleiben Zeichen mit Status `bestaetigt` oder `verworfen` und mit Herkunft `hand` erhalten, offene KI-Zeichen verschwinden; ein neuer Vorschlag, dessen Rahmen einen erhaltenen zu mehr als der Hälfte überdeckt, wird nicht angelegt; `arbeiten()` liefert `offen` und `status_gesamt` nach der Regel oben; `seiten_unfertig()` liefert wartende und laufende Seiten.
- [ ] Umsetzen, Commit.

### Task 5: Analyse-Brücke

**Files:** Create `webapp/analyse.py`; Test `tests/webapp/test_analyse.py`

- [ ] Tests mit einem Schein-Verfahren (per `monkeypatch` als Modul `korrektor.verfahren.schein` eingehängt): Funde werden zu Zeichen mit `herkunft="ki"`, `status="offen"` und `rahmen_ki`; ein Fund der Kategorie Z entfällt, wenn die Aufgabe nur R prüft; `einst["aufgabe"]` enthält Fach, Jahrgang und Kategorien; eine Fehlermeldung des Verfahrens wird durchgereicht.
- [ ] Umsetzen, Commit.

### Task 6: Warteschlange

**Files:** Create `webapp/warteschlange.py`; Test `tests/webapp/test_warteschlange.py`

- [ ] Tests mit Schein-`analysieren`: Erfolg führt zu Status `fertig` und gespeicherten Zeichen; Rückgabe mit Fehlermeldung und geworfene Ausnahme führen zu `fehlgeschlagen` mit Meldung; Zeitüberschreitung (`zeitgrenze_s=0.2`, Schein schläft 1 s) führt zu `fehlgeschlagen`, und das verspätete Ergebnis schreibt keine Zeichen; höchstens `gleichzeitig` Analysen laufen parallel (Zähler im Schein); `wiederaufnehmen()` reiht eine Seite mit Status `laeuft` neu ein.
- [ ] Umsetzen, Commit.

### Task 7: App-Gerüst, Aufgabenliste und Aufgabenformular

**Files:** Modify `webapp/__init__.py`; Create `webapp/routen.py`, `webapp/vorlagen/grundriss.html`, `aufgaben.html`, `aufgabe_formular.html`, `webapp/statisch/app.css`, `start.py`; Test `tests/webapp/test_routen.py`

- [ ] Tests mit dem Flask-Testclient und Schein-Analyse: Startseite zeigt den Prototyp-Hinweis und eine angelegte Aufgabe; Anlegen per Formular leitet zum Hochladen weiter und speichert Kategorien und Verfahren; ohne Titel oder ohne Kategorie erscheint eine Fehlermeldung; Bearbeiten ändert die Werte; Löschen entfernt die Aufgabe.
- [ ] `start.py` lädt `.env` und `einstellungen.toml`, erzeugt die App mit `datenordner="daten"`, ruft `wiederaufnehmen()` auf, öffnet den Browser und startet auf `127.0.0.1:5001`.
- [ ] `.claude/launch.json` um den Eintrag `webapp` ergänzen.
- [ ] Umsetzen, Commit.

### Task 8: Hochladen und Zuordnen

**Files:** Modify `webapp/routen.py`; Create `webapp/vorlagen/zuordnen.html`, `webapp/statisch/zuordnen.js`; Test `tests/webapp/test_routen.py`

- [ ] Tests: Hochladen von zwei Bildern und einer Textdatei nimmt zwei an und nennt die abgelehnte Datei; `ablage/ordnen` speichert Reihenfolge und Trennmarken; `analyse-starten` bildet Arbeiten, reiht alle Seiten ein und leitet zur Stapelansicht; bei fehlendem Schlüssel für das Verfahren kommt eine Meldung und nichts wird eingereiht; `POST /aufgabe/<id>/arbeit` mit zwei Bildern legt eine Arbeit mit zwei Seiten an.
- [ ] Oberfläche: Ablegen per Ziehen und Dateiauswahl, Vorschaureihe, Trennmarke zwischen je zwei Bildern (Klick schaltet um, sichtbar als Lücke mit Beschriftung der Arbeitsnummer), Bilder per Ziehen umordnen, Entfernen, Anzeige „n Fotos in m Arbeiten“, Knopf „Analyse starten“. Jede Änderung wird sofort über `ablage/ordnen` gespeichert.
- [ ] Umsetzen, Commit.

### Task 9: Stapelansicht mit laufender Aktualisierung

**Files:** Modify `webapp/routen.py`; Create `webapp/vorlagen/stapel.html`, `webapp/statisch/stapel.js`; Test `tests/webapp/test_routen.py`

- [ ] Tests: `/aufgabe/<id>/stand` liefert je Arbeit Kürzel, Seitenzahl, `status_gesamt`, `offen` und je Seite Status und Fehlermeldung; `POST /seite/<id>/erneut` reiht eine fehlgeschlagene Seite neu ein und lehnt eine fertige ab; Bildrouten liefern JPEG, mit `?b=300` ein verkleinertes Bild, bei unbekannter Nummer 404.
- [ ] Oberfläche: Kacheln mit Vorschaubild, Kürzel, Seitenzahl, Status, Zahl offener Vorschläge; Gesamtfortschritt; alle zwei Sekunden Abfrage von `stand`, solange etwas wartet oder läuft; bei fehlgeschlagenen Seiten Meldung und „erneut versuchen“; „Arbeit hinzufügen“ mit Dateiauswahl.
- [ ] Umsetzen, Commit.

### Task 10: Arbeit ansehen (nur lesend)

**Files:** Modify `webapp/routen.py`; Create `webapp/vorlagen/arbeit.html`, `webapp/statisch/arbeit.js`; Test `tests/webapp/test_routen.py`

- [ ] Tests: `/arbeit/<id>` liefert die Seite mit den Zeichen als eingebettete JSON-Daten; unbekannte Arbeit ergibt 404; Text aus `gelesen` und `vorschlag` mit `<` erscheint maskiert.
- [ ] Oberfläche: Foto mit Rahmen und Etikett je Vorschlag (gestrichelt, Farbe je Kategorie, eigene Form für `luecke`), Liste rechts, gegenseitiges Hervorheben, Blättern zwischen Seiten und Arbeiten. Kein Bearbeiten; ein Hinweis nennt Etappe 2.
- [ ] Umsetzen, Commit.

### Task 11: Durchlauf im Browser und Abschluss

- [ ] App starten, Aufgabe „Versuchsbeschreibung“ (Deutsch, 9, R/Z/Gr, Gemini Carbon) anlegen, die Fotos `B_1_gerade`, `B_1_schraeg`, `B_2_gerade`, `B_3_gerade` aus `fotos/` hochladen, zwei davon zu einer Arbeit verbinden, Analyse starten, Fortschritt beobachten, jede Arbeit öffnen und die Rahmen prüfen.
- [ ] Eine Aufgabe mit dem Schein eines fehlenden Schlüssels prüfen (Verfahren `claude` ohne Schlüssel): Meldung erscheint, nichts wird eingereiht.
- [ ] App beenden, während eine Analyse läuft, neu starten: die Seite wird wieder aufgenommen.
- [ ] Alle Tests grün, unabhängige Durchsicht des Codes, Befunde beheben, Commit und Push.
- [ ] README um den Abschnitt „Web-App starten“ ergänzen.
