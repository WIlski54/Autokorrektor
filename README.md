# Korrektor – Machbarkeitstest

Vergleicht vier Verfahren zur Korrektur handgeschriebener Texte an selbst geschriebenen
Testseiten. Es werden keine Schülerarbeiten verwendet.

## Einrichten

1. `python -m venv .venv`, aktivieren, `pip install -r requirements.txt`
2. `.env.beispiel` nach `.env` kopieren und Schlüssel eintragen
3. Für Cloud Vision: im Google-Cloud-Projekt die „Cloud Vision API“ aktivieren, einen auf diese
   Schnittstelle beschränkten API-Schlüssel anlegen und als `GOOGLE_VISION_API_KEY` in `.env` eintragen
4. Modellkennungen in `einstellungen.toml` prüfen

## Testseiten herstellen

1. `python vorlagen_bauen.py` erzeugt `vorlagen/<X>.abschreiben.txt`.
2. Jeden Text von zwei Personen von Hand abschreiben, mit allen Fehlern. Über die
   Abschriften verteilt einbauen: eine kleine Skizze im Text, eine Durchstreichung, eine
   Silbentrennung am Zeilenende, ein Wort über den Rand; liniertes und kariertes Papier,
   Füller und Bleistift.
3. Jede Abschrift zweimal fotografieren: gerade und gleichmäßig beleuchtet, sowie schräg
   mit Schatten. Ablegen als `fotos/<Text>_<Schreiber>_<gerade|schraeg>.jpg`,
   z. B. `fotos/C_2_schraeg.jpg`.
4. Abschreibkontrolle: Abschrift mit `<X>.abschreiben.txt` vergleichen. Weicht sie ab,
   `vorlagen/loesung_<X>.json` nach `vorlagen/loesung_<X>_<Schreiber>.json` kopieren und
   dort die Fehlerliste anpassen. Die Abschrift bleibt, wie sie ist.

## Messen

1. `python lauf.py` schickt alle Fotos durch alle Verfahren (Vorhandenes wird übersprungen).
2. `python pruefseite.py`, dann http://127.0.0.1:5000: je Fund „sitzt“ oder „sitzt nicht“
   klicken; bei Funden, die nicht automatisch zugeordnet wurden, im Auswahlfeld angeben, ob sie
   erfunden sind, ein echter Fehler außerhalb der Lösung oder zu welchem Lösungsfehler sie gehören.
   Wird ein Foto neu berechnet, verfallen die Klicks dazu. Ausgefallene Läufe wiederholt
   `python lauf.py` beim nächsten Start von selbst.
3. `python auswerten.py` schreibt `bericht.html`.

Fotos, Ergebnisse, Klicks und Bericht bleiben lokal und werden nicht ins Repository aufgenommen.
