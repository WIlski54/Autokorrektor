"""Analyse im Hintergrund: bis zu `gleichzeitig` Seiten auf einmal, mit Zeitgrenze.

Jede Seite wird von einem Arbeiter des Pools betreut. Der eigentliche Aufruf läuft in
einem eigenen Daemon-Thread, damit ein hängender Aufruf den Arbeiter nicht über die
Zeitgrenze hinaus blockiert. Geschrieben wird nur vom Arbeiter und nur für den Lauf, den
er selbst begonnen hat; ein verspätetes Ergebnis schreibt deshalb nichts mehr.
"""
import atexit
import logging
import threading
import time
import weakref
from concurrent.futures import ThreadPoolExecutor

protokoll = logging.getLogger(__name__)

_schlangen = weakref.WeakSet()


def _alle_beenden():
    for schlange in list(_schlangen):
        schlange.beenden()


# Die Arbeiter des Pools sind keine Daemon-Threads; Python wartet beim Beenden auf sie.
# Damit die App nicht bis zu einer Zeitgrenze lang hängt, werden sie vorher freigegeben.
# Derselbe Haken, den concurrent.futures selbst benutzt; er läuft vor dessen Warten.
try:
    threading._register_atexit(_alle_beenden)
except (AttributeError, RuntimeError):
    atexit.register(_alle_beenden)


class Warteschlange:
    def __init__(self, speicher, analysieren, gleichzeitig=3, zeitgrenze_s=240):
        """`analysieren(seite_id)` liefert ein dict wie `analyse.seite_analysieren`."""
        self.speicher = speicher
        self.analysieren = analysieren
        self.zeitgrenze_s = zeitgrenze_s
        self._arbeiter = ThreadPoolExecutor(max_workers=gleichzeitig,
                                            thread_name_prefix="warteschlange")
        self._anstehend = set()  # eingereihte und laufende Seiten
        self._zustand = threading.Condition()
        self._halt = threading.Event()
        _schlangen.add(self)

    def einreihen(self, seite_id):
        """Setzt den Status `wartet` und startet die Bearbeitung.

        Eine Seite, die schon ansteht oder gerade läuft, wird nicht doppelt eingereiht.
        """
        with self._zustand:
            if seite_id in self._anstehend:
                return
            self._anstehend.add(seite_id)
        try:
            self.speicher.seite_status(seite_id, "wartet", fehlermeldung=None)
            if self._halt.is_set():  # App endet: die Seite wird beim nächsten Start aufgenommen
                raise RuntimeError("Warteschlange ist beendet")
            self._arbeiter.submit(self._bearbeiten, seite_id)
        except BaseException as fehler:
            self._erledigt(seite_id)
            if not self._halt.is_set():
                raise fehler

    def wiederaufnehmen(self):
        """Reiht nach einem Neustart alle Seiten ein, die noch warten oder als laufend gelten."""
        for seite_id in self.speicher.seiten_unfertig():
            self.einreihen(seite_id)

    def warten(self, timeout=None):
        """Nur für Tests: blockiert, bis alles abgearbeitet ist; False bei Zeitablauf."""
        with self._zustand:
            return self._zustand.wait_for(lambda: not self._anstehend, timeout)

    def beenden(self):
        """Gibt alle Arbeiter frei. Unfertige Seiten behalten ihren Status für den Neustart."""
        self._halt.set()
        self._arbeiter.shutdown(wait=False, cancel_futures=True)
        with self._zustand:
            self._anstehend.clear()
            self._zustand.notify_all()

    def _erledigt(self, seite_id):
        with self._zustand:
            self._anstehend.discard(seite_id)
            self._zustand.notify_all()

    def _bearbeiten(self, seite_id):
        lauf = None
        try:
            if self._halt.is_set():
                return
            lauf = self.speicher.seite_lauf_beginnen(seite_id)
            if lauf is None:  # Seite inzwischen gelöscht
                return
            ausgang = self._mit_zeitgrenze(seite_id)
            if ausgang is None:  # App endet
                return
            ergebnis, meldung = ausgang
            if meldung is None and not isinstance(ergebnis, dict):
                meldung = "Die Analyse hat kein verwertbares Ergebnis geliefert."
            if meldung is None:
                meldung = ergebnis.get("fehlermeldung")
            if meldung is not None:
                self._fehlgeschlagen(seite_id, lauf, meldung)
            elif self.speicher.zeichen_ersetzen(seite_id, lauf, ergebnis.get("zeichen") or []):
                self.speicher.seite_status(
                    seite_id, "fertig", lauf=lauf, fehlermeldung=None,
                    transkription=ergebnis.get("transkription") or "",
                    dauer_s=ergebnis.get("dauer_s"), verworfen=ergebnis.get("verworfen") or 0)
        except Exception as fehler:  # etwa Datenbank gesperrt: Seite nicht als laufend zurücklassen
            protokoll.exception("Seite %s konnte nicht bearbeitet werden", seite_id)
            try:
                self._fehlgeschlagen(seite_id, lauf, f"{type(fehler).__name__}: {fehler}")
            except Exception:
                protokoll.exception("Status der Seite %s ließ sich nicht setzen", seite_id)
        finally:
            self._erledigt(seite_id)

    def _fehlgeschlagen(self, seite_id, lauf, meldung):
        self.speicher.seite_status(seite_id, "fehlgeschlagen", lauf=lauf,
                                   fehlermeldung=str(meldung))

    def _mit_zeitgrenze(self, seite_id):
        """Gibt (Ergebnis, Fehlermeldung) zurück; None, wenn die App währenddessen endet."""
        fach = {}
        fertig = threading.Event()

        def aufruf():
            try:
                fach["ergebnis"] = self.analysieren(seite_id)
            except Exception as fehler:
                fach["meldung"] = f"{type(fehler).__name__}: {fehler}"
            finally:
                fertig.set()

        threading.Thread(target=aufruf, daemon=True, name=f"analyse-seite-{seite_id}").start()
        frist = time.monotonic() + self.zeitgrenze_s
        while not fertig.wait(min(0.25, max(0.0, frist - time.monotonic()))):
            if self._halt.is_set():
                return None
            if time.monotonic() >= frist:
                return None, (f"Zeitüberschreitung: Die Analyse hat länger als "
                              f"{self.zeitgrenze_s:g} Sekunden gedauert.")
        return fach.get("ergebnis"), fach.get("meldung")
