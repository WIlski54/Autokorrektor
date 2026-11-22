# Korrektor – Teilprojekt 2: Web-App (Prototyp)

Stand: 22.11.2026 · Status: Entwurf zur Durchsicht

## 1. Ziel und Abgrenzung

Eine lokal laufende Web-App, mit der eine Lehrkraft Fotos handgeschriebener Schülertexte stapelweise hochlädt, von einer KI Fehler vorschlagen lässt, die Korrekturzeichen über dem unveränderten Originalbild prüft, verschiebt, ändert und ergänzt, die Korrektur ausdrücklich bestätigt und als PDF ausgibt.

Der Prototyp soll zeigen, ob das Werkzeug einer Lehrkraft im Alltag Arbeit abnimmt.

**Grundlage:** Teilprojekt 1 (Machbarkeitstest). Über elf Fotos, vier Handschriften und drei Texte hat Gemini Carbon jeden bekannten Fehler gefunden, keine Falle ausgelöst, sehr selten etwas erfunden und die Zeichen im Mittel rund ein Zehntel Rahmenhöhe neben dem Wort platziert. Bekannte Schwächen: Laufzeit zwischen 10 Sekunden und mehreren Minuten, leicht unterschiedliche Ergebnisse von Durchlauf zu Durchlauf, wertlose Selbsteinschätzung der Sicherheit.

**Nicht Teil des Prototyps:** Login und mehrere Benutzer, Betrieb auf einem Server, Rückmeldetexte, Fehlerkategorien jenseits von R, Z und Gr als KI-Vorschlag, Mathematik, Kennzeichnung unsicherer Stellen, Noten, Fehlerquotient als Bewertung, Rangfolgen. Die Datenstruktur lässt die ersten fünf später zu.

## 2. Entscheidungen aus dem Brainstorming

| Thema | Entscheidung |
|---|---|
| Betrieb | lokal auf dem eigenen Rechner, eine Person, ohne Login; Datenzugriff so gekapselt, dass ein späterer Umzug auf einen Server kein Neubau ist |
| Arbeitseinheit | Aufgabe (Stapel) → Arbeit → Seite; eine Arbeit kann mehrere Seiten haben |
| Zuordnung | alle Fotos auf einmal hochladen, Arbeiten per Trennmarke zwischen Vorschaubildern bilden; zusätzlich einzelne Arbeit nachträglich hinzufügen |
| Darstellung | Bearbeiten: Rahmen und Etikett am Wort. Ausgabe: Unterstreichung im Text und Kürzel in einer angefügten Randspalte |
| Freigabe | Vorschläge einzeln bestätigen oder verwerfen, dazu „Rest bestätigen“; am Ende jeder Arbeit eine ausdrückliche Gesamtbestätigung, ohne die keine Ausgabe möglich ist |
| KI-Fehlerarten | R, Z, Gr, je Aufgabe schaltbar; weitere Kürzel nur für von Hand gesetzte Zeichen |
| Ausgabe | PDF je Arbeit, Sammel-PDF je Aufgabe, Fehlerübersicht je Arbeit, Stapelübersicht am Bildschirm mit Tabellenexport |
| Verfahren | Gemini Carbon als Voreinstellung; die übrigen getesteten Verfahren wählbar |
| Technik | Flask, einfaches JavaScript ohne Build-Werkzeug, SVG-Ebene über dem Bild, SQLite |

## 3. Datenmodell

Eine SQLite-Datei `daten/korrektor.db` und ein Bilderordner `daten/bilder/`. Beides liegt außerhalb des Repositorys (per `.gitignore`).

**aufgabe**
- `id`, `titel`, `fach`, `jahrgang`
- `kategorien`: Teilmenge von R, Z, Gr, die die KI prüfen soll
- `verfahren`: Name des Analyseverfahrens
- `vorschlag_in_ausgabe`: ob die richtige Schreibung in der Ausgabe erscheint (Voreinstellung: nein)
- `erstellt_am`

**arbeit**
- `id`, `aufgabe_id`, `kuerzel` (frei wählbar, Voreinstellung laufende Nummer), `reihenfolge`
- `bestaetigt_am` (leer, solange nicht bestätigt)
- `bestaetigung`: Zahlen zum Zeitpunkt der Bestätigung (einzeln bestätigt, gesammelt bestätigt, geändert, verworfen, selbst gesetzt)

**seite**
- `id`, `arbeit_id`, `nummer`, `bilddatei`, `breite`, `hoehe`
- `analyse_status`: `neu`, `wartet`, `laeuft`, `fertig`, `fehlgeschlagen`
- `fehlermeldung`, `transkription`, `dauer_s`, `analysiert_am`

**zeichen**
- `id`, `seite_id`
- `kategorie`: Kürzel (R, Z, Gr oder ein eigenes)
- `typ`: `wort` oder `luecke`
- `x`, `y`, `breite`, `hoehe`: Rahmen in Pixeln des aufrecht gedrehten Originalbildes
- `gelesen`, `vorschlag`
- `herkunft`: `ki` oder `hand`
- `status`: `offen`, `bestaetigt`, `verworfen`
- `bestaetigt_wie`: `einzeln`, `gesammelt`, `geaendert` oder leer
- `rahmen_ki`: der ursprünglich von der KI gelieferte Rahmen (unverändert, zur Nachvollziehbarkeit)

**einstellung**
- Liste der Kürzel für eigene Zeichen mit Bezeichnung (Voreinstellung: A Ausdruck, Sb Satzbau, T Tempus, W Wortwahl, I Inhalt), bearbeitbar.

Das Originalbild wird nie verändert. Verworfene Zeichen werden nicht gelöscht, sondern behalten den Status `verworfen`, damit Auswertungen zur Vorschlagsqualität möglich bleiben.

## 4. Zustände und Regeln

### 4.1 Zeichen

- Ein Vorschlag der KI entsteht mit `herkunft = ki`, `status = offen`.
- Bestätigen setzt `status = bestaetigt`, `bestaetigt_wie = einzeln`.
- „Rest bestätigen“ setzt alle offenen Zeichen der Arbeit auf `bestaetigt`, `bestaetigt_wie = gesammelt`.
- Verwerfen setzt `status = verworfen`.
- Ändern von Kürzel oder Vorschlag eines KI-Zeichens setzt `status = bestaetigt`, `bestaetigt_wie = geaendert`. Reines Verschieben oder Ändern der Größe lässt den Status unberührt.
- Ein von Hand gesetztes Zeichen entsteht mit `herkunft = hand`, `status = bestaetigt`. Löschen entfernt es.
- Ein verworfenes Zeichen lässt sich wieder auf `offen` zurückholen.

### 4.2 Gesamtbestätigung einer Arbeit

- Möglich, sobald alle Seiten der Arbeit den Analysestatus `fertig` haben und kein Zeichen der Arbeit mehr `offen` ist.
- Der Bestätigungsdialog nennt die fünf Zahlen aus `arbeit.bestaetigung` und verlangt eine ausdrückliche Bestätigung.
- Jede spätere Änderung an Zeichen der Arbeit (Status, Kürzel, Vorschlag, Position, Größe, neues oder gelöschtes Zeichen, Neuanalyse) leert `bestaetigt_am`. Die Arbeit muss erneut bestätigt werden.
- Nur bestätigte Arbeiten lassen sich ausgeben. Das Sammel-PDF enthält nur bestätigte Arbeiten und nennt die Zahl der fehlenden.

### 4.3 Analyse

- Die Analyse startet erst, wenn die Zuordnung der Fotos zu Arbeiten bestätigt wurde.
- Eine Warteschlange im selben Prozess arbeitet bis zu drei Seiten gleichzeitig ab.
- Zeitgrenze je Seite: 240 Sekunden. Bei Überschreitung oder Fehler: `fehlgeschlagen` mit Fehlermeldung und Knopf „erneut versuchen“.
- Beim Start der App werden Seiten mit Status `laeuft` oder `wartet` wieder eingereiht.
- Neuanalyse einer Seite: Offene KI-Zeichen werden ersetzt. Bestätigte, verworfene und von Hand gesetzte Zeichen bleiben erhalten. Neue Vorschläge, deren Rahmen einen erhaltenen Rahmen zu mehr als der Hälfte überdeckt, werden nicht angelegt.
- Die Anweisung an das Modell nennt Fach, Jahrgang und nur die eingeschalteten Kategorien.

## 5. Bildschirme

### 5.1 Aufgabenliste (Startseite)

Tabelle aller Aufgaben mit Titel, Fach, Jahrgang, Zahl der Arbeiten und Fortschritt (analysiert, geprüft, bestätigt). Knöpfe: neue Aufgabe, öffnen, löschen. Löschen fragt nach und entfernt Fotos und Zeichen.

Ein fester Hinweis: Der Prototyp ist für eigene Texte gedacht; vor echten Schülerarbeiten sind Verarbeitungsort, Auftragsverarbeitung und Genehmigung zu klären.

### 5.2 Aufgabe anlegen und bearbeiten

Titel, Fach, Jahrgang, Schalter für R, Z, Gr, Auswahl des Verfahrens, Schalter „richtige Schreibung in der Ausgabe zeigen“. Kategorien und Verfahren lassen sich nach Beginn der Analyse nur mit dem Hinweis ändern, dass bereits analysierte Seiten davon nicht betroffen sind.

### 5.3 Hochladen und zuordnen

- Auswahl mehrerer Dateien oder Ablegen per Ziehen. Erlaubt: JPG, PNG, WebP. Bilder werden aufrecht gedreht gespeichert.
- Vorschaureihe in Hochlade-Reihenfolge. Zwischen je zwei Bildern eine Trennmarke: aktiv heißt „hier beginnt eine neue Arbeit“. Anfangs ist jede Marke aktiv.
- Bilder lassen sich in der Reihe verschieben und entfernen.
- Jede Arbeit bekommt als Kürzel eine laufende Nummer, änderbar.
- „Analyse starten“ legt Arbeiten und Seiten an und reiht alle Seiten ein.
- „Arbeit hinzufügen“ in der Stapelansicht: Fotos einer einzelnen Arbeit auswählen, alle zusammen bilden eine Arbeit.

### 5.4 Stapelansicht

Kacheln aller Arbeiten einer Aufgabe mit Kürzel, Vorschaubild der ersten Seite, Seitenzahl, Analysestatus, Zahl offener Vorschläge und Bestätigungsstatus. Die Ansicht aktualisiert sich während der Analyse von selbst. Von hier aus: Arbeit öffnen, Arbeit hinzufügen, Stapelübersicht, Sammel-PDF.

### 5.5 Korrekturansicht

Links das Foto mit der Zeichenebene, rechts die Liste der Zeichen der aktuellen Seite.

- **Darstellung:** Rahmen und Etikett je Zeichen. Offen: gestrichelt und blass. Bestätigt: durchgezogen. Verworfen: ausgeblendet, über einen Schalter einblendbar. Farbe je Kategorie. `luecke` in eigener Form (schmaler Rahmen).
- **Auswählen:** Klick im Bild oder in der Liste hebt dasselbe Zeichen an beiden Stellen hervor.
- **Verschieben und Größe:** Ziehen des Rahmens, Ziehpunkte an den Ecken.
- **Ändern:** Kürzel und Vorschlag bearbeiten.
- **Selbst setzen:** Modus „Zeichen setzen“, Rahmen aufziehen, Kürzel aus R, Z, Gr und den eigenen Kürzeln wählen, optional Vorschlag eintragen.
- **Tastatur:** Sprung zum nächsten offenen Vorschlag; je eine Taste für Bestätigen, Verwerfen, Ändern; Pfeiltasten für Seite und Arbeit. Die Belegung steht sichtbar in der Ansicht.
- **Zoom:** vergrößern, verkleinern, einpassen.
- **Seiten:** Blättern innerhalb der Arbeit; Anzeige „Seite n von m“.
- **Arbeit wechseln:** vorherige und nächste Arbeit.
- **Fußleiste:** „Zeichen setzen“, „Rest bestätigen“, „Korrektur gesamt bestätigen“ (erst freigeschaltet nach Regel 4.2), „Seite neu analysieren“.
- Die vom Modell gemeldete Sicherheit wird nicht angezeigt.

Jede Änderung wird sofort gespeichert.

### 5.6 Stapelübersicht

- Zahl der bestätigten Zeichen je Kategorie über alle bestätigten Arbeiten.
- Die am häufigsten falsch geschriebenen Wörter (nach `gelesen`, mit Häufigkeit und Vorschlag).
- Tabelle je Arbeit: Kürzel und Zahl der Zeichen je Kategorie, alphabetisch bzw. in Stapelreihenfolge, ohne Rangfolge und ohne Bewertung.
- Export der Tabelle als CSV.

### 5.7 Ausgabe

- **PDF je Arbeit:** je Seite das Originalfoto, darüber die bestätigten Zeichen als Unterstreichung (`wort`) bzw. Einfügezeichen (`luecke`), rechts eine angefügte Randspalte mit dem Kürzel auf Höhe der Stelle. Mehrere Zeichen in einer Zeile stehen in der Randspalte nebeneinander in Lesereihenfolge. Ist „richtige Schreibung zeigen“ eingeschaltet, steht der Vorschlag klein neben dem Kürzel.
- **Fehlerübersicht je Arbeit:** Anzahl je Kategorie als Kasten am Ende der letzten Seite.
- **Sammel-PDF:** alle bestätigten Arbeiten der Aufgabe hintereinander, jede beginnt auf einer neuen Seite.
- Die Ausgabe zeigt nicht, ob ein Zeichen von der KI stammt.

## 6. Aufbau und Technik

```
Korrektor/
  korrektor/            vorhandenes Paket (Verfahren, Bild, Koordinaten, Einrasten)
  webapp/
    __init__.py         Flask-App erzeugen
    speicher.py         Datenzugriff (einzige Stelle mit SQL)
    regeln.py           Zustandsregeln aus Abschnitt 4 (reine Funktionen)
    warteschlange.py    Analyse im Hintergrund
    analyse.py          Brücke zu den Verfahren: Seite -> Zeichen
    ausgabe.py          PDF-Erzeugung
    uebersicht.py       Zahlen für Stapelübersicht und CSV
    routen/             Seiten und JSON-Schnittstellen
    vorlagen/           HTML-Vorlagen
    statisch/           JavaScript und CSS
  daten/                Datenbank und Bilder (nicht im Repository)
  start.py              startet die App und öffnet den Browser
```

- **Datenzugriff:** Nur `speicher.py` kennt SQLite. Alle anderen Bausteine arbeiten mit einfachen Datenobjekten. Das ist die Naht für einen späteren Umzug auf einen Server.
- **Regeln:** Die Zustandsübergänge aus Abschnitt 4 liegen als reine Funktionen in `regeln.py` und sind ohne Datenbank und Browser prüfbar.
- **Verfahren:** Die Verfahren aus Teilprojekt 1 werden über ihre bestehende Schnittstelle genutzt. Die gemeinsame Anweisung wird so erweitert, dass Fach, Jahrgang und Kategorien einfließen.
- **Oberfläche:** HTML-Vorlagen, einfaches JavaScript, SVG-Ebene über dem Bild mit Prozentkoordinaten, sodass Zoom und Fenstergröße keine Umrechnung brauchen.
- **PDF:** serverseitig erzeugt, ohne Browser.
- **Schlüssel:** weiter in der lokalen `.env`.

## 7. Fehlerbehandlung

- Fehlgeschlagene Analyse: Status, lesbare Meldung, „erneut versuchen“. Der Rest des Stapels läuft weiter.
- Unbrauchbare Einzelfunde des Modells werden verworfen und je Seite gezählt (wie in Teilprojekt 1).
- Nicht lesbare oder zu große Dateien werden beim Hochladen mit Dateiname abgelehnt, die übrigen angenommen.
- Fehlt ein Schlüssel für das gewählte Verfahren, meldet die App das beim Start der Analyse und nicht erst je Seite.
- Speichern eines Zeichens schlägt fehl: Die Oberfläche zeigt eine Meldung und stellt den vorherigen Zustand wieder her.

## 8. Datenschutz und rechtlicher Rahmen

- Arbeiten tragen keine Namen, nur Nummer oder Kürzel.
- Alle Daten liegen lokal. An den Analysedienst geht nur das Bild der Seite mit der Anweisung.
- Löschen einer Aufgabe oder Arbeit entfernt Fotos und Zeichen endgültig.
- Fester Hinweis in der App auf den Prototyp-Charakter.
- Menschliche Aufsicht: Einzelprüfung oder ausdrückliche Sammelbestätigung, dazu Gesamtbestätigung je Arbeit; die App hält fest, wie bestätigt wurde. Keine Bewertung durch die App.
- Vor einem Schuleinsatz zu klären (nicht Teil des Prototyps): Einordnung nach dem AI Act, Bezug von Carbon über eine Schnittstelle mit EU-Verarbeitung und Auftragsverarbeitungsvertrag, Trainingsausschluss, Genehmigung der Schulleitung.

## 9. Prüfung

- **Regeln:** Tests für jeden Zustandsübergang aus Abschnitt 4, insbesondere: Gesamtbestätigung verfällt bei jeder Änderung; Ausgabe nur für bestätigte Arbeiten; Neuanalyse erhält bestätigte, verworfene und eigene Zeichen.
- **Datenzugriff:** Tests gegen eine Datenbank im Arbeitsspeicher, einschließlich Löschen mit allen abhängigen Daten und Bilddateien.
- **Warteschlange:** Tests mit einem Schein-Verfahren (sofortige Antwort, Fehler, Zeitüberschreitung, Wiederaufnahme nach Neustart).
- **Ausgabe:** Tests, dass das PDF je Seite die richtige Zahl an Markierungen an den erwarteten Stellen enthält und die Randspalte die Kürzel in Lesereihenfolge führt.
- **Oberfläche:** Durchlauf im Browser je Etappe mit den Fotos aus Teilprojekt 1: hochladen, zuordnen, analysieren, bearbeiten, bestätigen, ausgeben.

## 10. Etappen

Jede Etappe ist für sich benutzbar und bekommt einen eigenen Umsetzungsplan.

1. **Stapel und Analyse:** Datenmodell, Aufgabenliste, Aufgabe anlegen, Hochladen und Zuordnen, Warteschlange, Stapelansicht. Ergebnis: Fotos rein, Vorschläge in der Datenbank, Fortschritt sichtbar.
2. **Korrekturansicht und Freigabe:** Anzeigen, Auswählen, Verschieben, Ändern, Setzen, Tastatur, „Rest bestätigen“, Gesamtbestätigung, Neuanalyse.
3. **Ausgabe und Übersicht:** PDF je Arbeit, Sammel-PDF, Fehlerübersicht, Stapelübersicht mit CSV.

## 11. Später im Blick

- Weitere Fehlerkategorien als KI-Vorschlag (Ausdruck, Satzbau, Tempus, Wortwahl), nach eigenen Testtexten.
- Rückmeldetext je Arbeit mit Bearbeitung und Freigabe.
- Kennzeichnung unsicherer Stellen durch zweiten Lesedurchgang oder Abgleich mit der Texterkennung.
- Betrieb auf einem Server mit Login.
