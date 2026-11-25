# Präsentationsfilm

`aufnehmen.py` erzeugt einen stummen Film (Bildschirmaufnahme), der den Korrektor vom Anlegen
einer Aufgabe bis zur Stapelübersicht zeigt. Ein Skript bedient dabei die App im Browser;
der Film entsteht mit einem Befehl neu.

## Voraussetzungen

- die `.venv` des Projekts mit den Paketen der App
- `ffmpeg` im Suchpfad
- Playwright mit Chromium:

  ```
  .venv/Scripts/python.exe -m pip install -r film/requirements.txt
  .venv/Scripts/python.exe -m playwright install chromium
  ```

- die Fotos `fotos/E_1_gerade.jpg`, `B_1_gerade.jpg`, `B_2_gerade.jpg`, `B_3_gerade.jpg` und
  die dazu gespeicherten Ergebnisse in `ergebnisse/gemini/` (beides liegt nur lokal)

## Aufnehmen

```
.venv/Scripts/python.exe film/aufnehmen.py
```

Das dauert etwa sechs Minuten (Aufnahme in Echtzeit, danach der Schnitt). Es entstehen:

| Datei | Inhalt |
|---|---|
| `film/ausgabe/korrektor-demo.mp4` | der ganze Film, 1920×1080, 30 Bilder/s, H.264, ohne Ton, mit Kapitelmarken |
| `film/ausgabe/kapitel-01-….mp4` bis `kapitel-09-….mp4` | jedes Kapitel als eigene Datei |
| `film/ausgabe/standbilder/` | Standbilder zum Prüfen (je Kapitel Titelkarte, Anfang, Ende und die wichtigen Stellen) |
| `film/ausgabe/roh/` | die Rohaufnahme von Playwright |

`film/ausgabe/` und `film/daten_film/` stehen in `.gitignore`.

## Was der Film zeigt und was nicht

- Die Aufnahme läuft gegen eine **eigene Instanz** der App auf Port 5002 mit dem Datenordner
  `film/daten_film/`, der bei jedem Lauf neu angelegt wird. `daten/` und laufende Instanzen
  auf Port 5000 oder 5001 bleiben unberührt. Die Datei `.env` wird nicht gelesen.
- Die **Analyse kommt aus der Konserve**: Die App verarbeitet die Seiten wie sonst
  (`webapp/analyse.py` mit dem Kategorienfilter der Aufgabe), nur der Aufruf von Gemini
  Carbon ist ersetzt. Er gibt nach vier bis sieben Sekunden das früher erzeugte Ergebnis aus
  `ergebnisse/gemini/` zurück. Es geht nichts an einen KI-Dienst.
- Der Mauszeiger, der Ring beim Klicken und die Anzeige der gedrückten Taste oben in der
  Kopfleiste sind Einblendungen des Filmskripts, nicht Teil der App.
- Für den Beamer ist die **Darstellung vergrößert**, allein über eingespieltes CSS
  (`FILM_CSS`); der Code der App bleibt unberührt. Die Grundschrift ist von 16 auf 20 Pixel
  (Korrekturansicht, `SCHRIFT_KORREKTUR`) und auf 24 Pixel (alle anderen Seiten,
  `SCHRIFT_SEITEN`) gesetzt. Formular, Kacheln, Vorschaukarten und die Tabellen der
  Stapelübersicht nutzen die Breite; die Vorschaubilder werden dafür in 900 statt 300 Pixeln
  Breite geholt. Die Dialoge sind etwa 960 Pixel breit, die Fußleiste der Korrekturansicht
  bleibt einzeilig.
- Die aufgeklappte Liste eines Auswahlfelds erscheint in der Aufnahme nicht. Beim Kürzel des
  eigenen Zeichens zeigt der Film darum nur: Zeiger auf dem Feld, Fokusrahmen, dann der neue
  Wert.
- Das ausgegebene PDF zeigt der Film im eingebauten PDF-Betrachter von Chromium, die ganze
  Seite im Fenster (`#view=Fit`): Die Film-Instanz liefert die eben heruntergeladene Datei
  über eine eigene Adresse aus (`PDF_WEG = "betrachter"`). Mit `PDF_WEG = "bild"` erscheint
  stattdessen eine schlichte Seite, die die Seiten des PDF als Bild darstellt.

## Anpassen

Das Drehbuch steht in der Funktion `drehen`, Titel und Untertitel der Kapitel in `KAPITEL`.
Pausen sind in Sekunden angegeben (`r.pause(…)`); `r.marke("name")` merkt eine Stelle für ein
Standbild vor.

Zum Prüfen der Gestaltung gibt es einen **Probelauf**: Mit der Umgebungsvariablen
`FILM_PROBE=1` läuft das Drehbuch mit kurzen Pausen in knapp zwei Minuten durch, ohne
Schnitt; an jeder gemerkten Stelle entsteht ein Bildschirmfoto in `film/ausgabe/probe/`.
