# Korrektor – Teilprojekt 1: Machbarkeitstest

Stand: 21.11.2026 · Status: Entwurf zur Durchsicht

## 1. Ziel und Abgrenzung

Das Gesamtvorhaben ist eine Web-App, in der eine Lehrkraft das Foto eines handgeschriebenen Schülertextes hochlädt, die KI Fehler findet und Korrekturzeichen als verschiebbare Maske über das unveränderte Originalbild legt. Die Lehrkraft muss jeden Fund freigeben (Letztes-Auge-Regel).

Dieses Dokument beschreibt nur **Teilprojekt 1**: einen Machbarkeitstest, der vor dem Bau der App mit Zahlen klärt,

1. ob Handschrift buchstabengetreu gelesen wird, ohne dass Fehler stillschweigend berichtigt werden,
2. ob Fehler zuverlässig gefunden und nicht erfunden werden,
3. ob die Korrekturzeichen am richtigen Wort bzw. an der richtigen Lücke landen,
4. welches Verfahren dafür am besten geeignet ist.

**Nicht Teil dieses Teilprojekts:** Dashboard, Editor zum Verschieben und Ändern, Benutzerverwaltung, Export, Mathematik, Bewertung oder Notenvorschläge, Fehlerarten jenseits von R, Z und Gr. Die Web-App bekommt nach dem Test einen eigenen Entwurf.

## 2. Rahmenbedingungen

- **Einsatzfall:** Deutsch, Jahrgang 9.
- **Fehlerarten:** Rechtschreibung (R), Zeichensetzung (Z), Grammatik (Gr).
- **Daten:** Es werden ausschließlich selbst geschriebene Texte verwendet. Keine echten Schülerarbeiten. Die Beispielbilder der Schulbuchverlage im Projektordner dienen nur als Wortlaut-Vorlage und werden nicht an die Dienste geschickt.
- **Zugänge:** Gemini (AI-Studio-Schlüssel), OpenAI (API-Schlüssel), Anthropic (API-Schlüssel, wird noch angelegt), Google Cloud Vision (Cloud-Projekt, wird noch angelegt).
- **Schlüssel** liegen in einer lokalen `.env`-Datei und werden nie weitergegeben oder in Ergebnisdateien geschrieben.

## 3. Testmaterial

### 3.1 Vorlagetexte

| Kürzel | Herkunft | Umfang |
|---|---|---|
| A | Eigener Text, angelehnt an Stil und Fehlerbild von `Text1.jpg` (Erzählung über Atome) | ca. 130 Wörter |
| B | Eigener Text, angelehnt an Stil und Fehlerbild von `text4.jpg` (Versuchsbeschreibung) | ca. 90 Wörter |
| C | Eigener Text, Erörterung auf Niveau Klasse 9 | ca. 130 Wörter |
| D | Eigener Text, Inhaltsangabe auf Niveau Klasse 9 | ca. 130 Wörter |
| H (optional) | Wortlaut von `text2.jpg` oder `text3.jpg` als Härtetest | wie Original |

Die Texte A bis D enthalten je 12 bis 15 Fehler. A und B übernehmen nicht den Wortlaut der Verlagsbilder, weil das Repository öffentlich ist; sie bilden nur deren Fehlerarten nach. C und D enthalten eingebaute Fehler mit Schwerpunkt Kommasetzung, Groß-/Kleinschreibung, Getrennt-/Zusammenschreibung und das/dass. Jeder Text enthält zusätzlich drei bis fünf **Fallen**: korrekt geschriebene, aber schwierige Wörter und Eigennamen, an denen erfundene Fehler sichtbar werden.

Text H zählt nicht für die Bestehensschwelle. Er prüft nur, ob ein Verfahren Unsicherheit meldet.

### 3.2 Lösungsdatei

Zu jedem Vorlagetext gibt es eine Lösungsdatei (JSON) mit:

- `soll_text`: der Text genau so, wie er abgeschrieben werden soll, also mit Fehlern,
- `fehler`: Liste mit Kennung, Kategorie (R, Z, Gr), falscher Schreibung und richtiger Schreibung; bei fehlenden Satzzeichen stehen die beiden Nachbarwörter als falsche Schreibung („Gefühl dass“) und mit Zeichen als richtige („Gefühl, dass“),
- `fallen`: Liste der korrekt geschriebenen Fallen-Wörter.

Die Lösungsdatei wird nicht von Hand gepflegt, sondern aus einer Vorlage mit Markierungen erzeugt (`[R:falsch|richtig]`, `{Falle}`).

### 3.3 Aufnahmen

- Jeder Text wird von zwei Personen abgeschrieben.
- Jede Abschrift wird zweimal aufgenommen: einmal gerade und gleichmäßig beleuchtet, einmal als schräges Handyfoto mit Schatten.
- Das ergibt bis zu 16 Bilder für A bis D. Für einen ersten Durchlauf reichen 8 (eine Aufnahme pro Abschrift).
- Über die Abschriften verteilt werden bewusst Störungen eingebaut: eine kleine Skizze im Text, eine Durchstreichung, eine Silbentrennung am Zeilenende, ein Wort über den Rand hinaus, wechselnd liniertes und kariertes Papier, Füller und Bleistift.
- **Abschreibkontrolle:** Nach dem Abschreiben wird jede Abschrift einmal mit dem `soll_text` verglichen. Weicht die Abschrift ab (versehentlich berichtigter oder neuer Fehler), wird die Lösungsdatei für diese Abschrift angepasst, nicht die Abschrift.

Dateinamen: `fotos/<Text>_<Schreiber>_<Aufnahme>.jpg`, z. B. `fotos/C_1_schraeg.jpg`.

## 4. Die vier Verfahren

| Nr. | Lesen und Position | Fehleranalyse |
|---|---|---|
| 1 | Gemini | Gemini |
| 2 | Claude | Claude |
| 3 | GPT | GPT |
| 4 | Cloud Vision | Sprachmodell mit Gegenprüfung |

**Verfahren 1 bis 3 (ein Modell macht alles):** Das Modell erhält das Foto und eine einheitliche Anweisung. Es soll den Text buchstabengetreu abschreiben, Fehler der Kategorien R, Z und Gr melden und zu jedem Fund die Position als Rahmen angeben. Die Anweisung ist für alle drei Modelle inhaltlich gleich; nur das Koordinatenformat wird an das jeweilige Modell angepasst und anschließend in Bildpixel umgerechnet.

**Verfahren 4 (zweistufig):**

1. Cloud Vision (`DOCUMENT_TEXT_DETECTION`, EU-Endpunkt) liefert Wörter und Einzelzeichen mit Rahmen und Vertrauenswert.
2. Die Wörter werden durchnummeriert. Das Sprachmodell erhält den nummerierten Text und meldet Fehler mit Bezug auf Wortnummern bzw. auf die Lücke nach einer Wortnummer. Die Position stammt aus den Rahmen von Schritt 1.
3. Gegenprüfung: Für jeden R-Fund erhält das Sprachmodell den Bildausschnitt des Wortes und buchstabiert ihn. Stimmt die Buchstabierung nicht mit der Lesung aus Schritt 1 überein oder liegt der Vertrauenswert unter einer Schwelle, wird der Fund als „unsicher gelesen“ gekennzeichnet.

Das Sprachmodell für Verfahren 4 ist einstellbar; Voreinstellung ist Claude.

**Modellwahl:** Je Anbieter wird das aktuell leistungsstärkste allgemein verfügbare Modell verwendet. Die genauen Modellkennungen werden bei der Umsetzung anhand der Anbieterdokumentation festgelegt, stehen in einer Einstellungsdatei und werden in jedem Ergebnis mitgeschrieben.

## 5. Einheitliches Ergebnisformat

Jedes Verfahren schreibt pro Bild eine JSON-Datei nach `ergebnisse/<Verfahren>/<Bildname>.json`:

```json
{
  "bild": "C_1_schraeg.jpg",
  "verfahren": "vision_kombi",
  "modelle": {"lesen": "…", "analyse": "…"},
  "bildgroesse": [2480, 3508],
  "transkription": "…",
  "funde": [
    {
      "id": 1,
      "kategorie": "R",
      "gelesen": "Fahrad",
      "vorschlag": "Fahrrad",
      "anker": {"typ": "wort", "rahmen": [412, 880, 190, 64]},
      "sicherheit": 0.92,
      "unsicher_gelesen": false
    },
    {
      "id": 2,
      "kategorie": "Z",
      "gelesen": "Gefühl dass",
      "vorschlag": "Gefühl, dass",
      "anker": {"typ": "luecke", "rahmen": [1310, 1122, 24, 64]},
      "sicherheit": 0.88,
      "unsicher_gelesen": false
    }
  ],
  "dauer_s": 7.4,
  "fehlermeldung": null
}
```

- `rahmen` ist immer `[x, y, breite, hoehe]` in Pixeln des Originalbildes.
- `anker.typ` ist `wort` (Fund betrifft ein Wort oder eine Wortgruppe) oder `luecke` (fehlendes Zeichen zwischen zwei Wörtern).
- Dieses Format wird später das Datenformat der Maske in der Web-App. Das Originalbild wird nie verändert.

## 6. Auswertung

### 6.1 Messgrößen

| Messgröße | Bedeutung | Ermittlung |
|---|---|---|
| Lesetreue | Anteil der Fehlerwörter, die so gelesen wurden, wie sie dastehen | automatisch: Wortabgleich zwischen `transkription` und `soll_text` |
| Gefunden | Anteil der Fehler aus der Lösungsdatei, die gemeldet wurden | automatisch: Zuordnung der Funde über Text und Reihenfolge |
| Erfunden | Meldungen ohne Entsprechung in der Lösungsdatei, pro Seite | automatisch, mit Durchsicht (siehe 6.2) |
| Fallen ausgelöst | Anteil der Fallen-Wörter, die fälschlich gemeldet wurden | automatisch |
| Platzierung | Anteil der zutreffenden Funde, deren Rahmen am richtigen Wort bzw. an der richtigen Lücke sitzt | von Hand auf der Prüfseite |

Alle Messgrößen werden je Verfahren insgesamt sowie getrennt nach Kategorie (R, Z, Gr) und nach Aufnahmeart (gerade, schräg) ausgewiesen.

### 6.2 Prüfseite

Eine lokale HTML-Seite zeigt je Bild und Verfahren das Foto mit den eingezeichneten Rahmen und einer Fundliste. Pro Fund gibt es zwei Angaben per Klick:

- Platzierung: „sitzt“ oder „sitzt nicht“,
- nur bei Funden ohne Entsprechung in der Lösungsdatei: „tatsächlich ein Fehler“ oder „erfunden“. Damit werden Fehler berücksichtigt, die beim Abschreiben unbemerkt entstanden sind.

Die Klicks werden in einer JSON-Datei gespeichert, die das Auswertungsskript einliest.

### 6.3 Bericht

Das Auswertungsskript erzeugt `bericht.html` mit einer Vergleichstabelle der vier Verfahren, der Aufschlüsselung nach Kategorie und Aufnahmeart, Laufzeiten und Tokenverbrauch (als Grundlage für die Kosten) sowie einer Liste der auffälligsten Fehlgriffe mit Bildausschnitt.

## 7. Bestehensschwelle

Der Test gilt als bestanden, wenn das beste Verfahren über die Texte A bis D

- mindestens 85 % der Fehler findet,
- höchstens einen erfundenen Fehler pro Seite meldet,
- mindestens 90 % der zutreffenden Funde richtig platziert.

Die Lesetreue hat keine eigene Schwelle, wird aber als wichtigste Erklärungsgröße berichtet. Liegt das beste Verfahren deutlich unter den Schwellen, wird der Ansatz überdacht, bevor Teilprojekt 2 beginnt.

## 8. Aufbau und Technik

```
Korrektor/
  vorlagen/        Vorlagetexte und Lösungsdateien
  fotos/           Aufnahmen der Abschriften
  verfahren/       ein Python-Modul je Verfahren
  ergebnisse/      Ergebnisdateien je Verfahren und Bild
  pruefseite/      HTML-Prüfseite und gespeicherte Klicks
  auswertung.py    Messgrößen und Bericht
  lauf.py          startet Verfahren für alle oder einzelne Bilder
  einstellungen.toml   Modellkennungen, Schwellen
  .env             Schlüssel (nicht weitergeben)
```

- Sprache: Python. Jedes Verfahren ist ein eigenes Modul mit derselben Schnittstelle: Bildpfad hinein, Ergebnis im Format aus Abschnitt 5 heraus. Dadurch lässt sich jedes Verfahren einzeln testen und später unverändert in die Web-App übernehmen.
- Die gemeinsame Anweisung an die Modelle liegt an einer Stelle und wird von allen Verfahren verwendet.
- `lauf.py` überspringt Bilder, für die schon ein Ergebnis vorliegt, damit ein Abbruch nichts kostet.

## 9. Fehlerbehandlung

- Schlägt ein Aufruf fehl, wird er einmal wiederholt. Bleibt er erfolglos, wird eine Ergebnisdatei mit `fehlermeldung` und leerer Fundliste geschrieben.
- Liefert ein Modell kein auswertbares JSON, gilt dasselbe. Solche Ausfälle werden im Bericht je Verfahren gezählt.
- Rahmen außerhalb des Bildes werden auf die Bildgrenzen beschnitten und im Bericht als Auffälligkeit vermerkt.

## 10. Prüfung der Testwerkzeuge selbst

- Das Auswertungsskript wird mit drei erfundenen Ergebnisdateien geprüft, deren richtige Messwerte von Hand feststehen: alles gefunden, nichts gefunden, gemischt mit erfundenen Funden.
- Die Koordinatenumrechnung je Verfahren wird an einem Testbild mit bekannten Rechtecken geprüft.

## 11. Voraussetzungen und offene Punkte

Von Stephan zu erledigen:

- Anthropic-API-Schlüssel anlegen,
- Google-Cloud-Projekt anlegen und die Vision-Schnittstelle freischalten,
- Vorlagetexte abschreiben (lassen) und fotografieren.

Vor einem späteren Schuleinsatz, nicht für diesen Test, zu klären:

- Einordnung nach dem AI Act (Anhang III Nr. 3, Ausnahme nach Art. 6 Abs. 3) und aktuelle Anwendungsfristen,
- Verarbeitungsort, Auftragsverarbeitung und Trainingsausschluss bei jedem verwendeten Dienst; die Zusage zur reinen EU-Verarbeitung beim Cloud-Vision-EU-Endpunkt im Original nachlesen,
- Übertragbarkeit: Erwachsenenschrift ist leichter lesbar als Schülerschrift. Ein bestandener Test heißt „lohnt sich weiterzumachen“, nicht „funktioniert in der Klasse“.
