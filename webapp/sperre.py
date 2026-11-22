"""Einzelinstanz-Sperre: Je Datenordner läuft höchstens eine App.

Eine zweite Instanz würde über die Wiederaufnahme alle unfertigen Seiten noch einmal
analysieren. Unter Windows verhindert der belegte Port das nicht zuverlässig.
"""
import os
from pathlib import Path

DATEINAME = "korrektor.sperre"


def sperre_belegen(datenordner):
    """Belegt die Sperre des Datenordners; legt ihn bei Bedarf an.

    Gibt die geöffnete Sperrdatei zurück, None, wenn schon eine andere Instanz sie hält.
    Die Sperre gilt, solange die Datei offen ist: Der Aufrufer behält sie bis zum Ende.
    Endet der Prozess (auch durch einen Absturz), gibt das Betriebssystem sie frei.
    """
    ordner = Path(datenordner)
    ordner.mkdir(parents=True, exist_ok=True)
    datei = open(ordner / DATEINAME, "a+b")
    try:
        if os.name == "nt":
            import msvcrt
            datei.seek(0)
            msvcrt.locking(datei.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(datei.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        datei.close()
        return None
    return datei
