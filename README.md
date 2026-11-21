# Korrektor – Machbarkeitstest

Vergleicht vier Verfahren zur Korrektur handgeschriebener Texte an selbst geschriebenen
Testseiten. Es werden keine Schülerarbeiten verwendet.

## Einrichten

1. `python -m venv .venv`, aktivieren, `pip install -r requirements.txt`
2. `.env.beispiel` nach `.env` kopieren und Schlüssel eintragen
3. Für Cloud Vision: `gcloud auth application-default login` und
   `gcloud auth application-default set-quota-project PROJEKT_ID`
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
   klicken; bei Funden außerhalb der Lösung zusätzlich „tatsächlich ein Fehler“ oder „erfunden“.
3. `python auswerten.py` schreibt `bericht.html`.

Fotos, Ergebnisse, Klicks und Bericht bleiben lokal und werden nicht ins Repository aufgenommen.
