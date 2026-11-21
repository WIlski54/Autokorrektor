# Korrektor-Machbarkeitstest – Umsetzungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ein Messwerkzeug bauen, das vier Verfahren zur Korrektur handgeschriebener Texte (Gemini, Claude, GPT, Cloud Vision + Sprachmodell) an selbst geschriebenen Testseiten vergleicht und einen Bericht mit Lesetreue, Fundquote, erfundenen Fehlern und Platzierung liefert.

**Architecture:** Ein kleines Python-Paket `korrektor/`. Jedes Verfahren ist ein Modul mit derselben Schnittstelle `ausfuehren(bildpfad, einst) -> dict` und schreibt ein einheitliches Ergebnis-JSON. Reine Rechenlogik (Koordinaten, Zuordnung, Messgrößen) ist von den Netzaufrufen getrennt und per pytest abgedeckt; die Netzaufrufe werden mit einem echten Foto von Hand geprüft. Eine lokale Flask-Seite sammelt die Klicks zur Platzierung.

**Tech Stack:** Python ≥ 3.11, pytest, Pillow, Flask, python-dotenv, `anthropic`, `openai`, `google-genai`, `google-cloud-vision`.

**Spezifikation:** `docs/superpowers/specs/2026-11-21-machbarkeitstest-design.md`

> **Stand nach der Code-Durchsicht:** Tasks 1–8, 10 und 12–15 (Step 1–2) sind umgesetzt. Der Code weicht an einigen Stellen vom hier abgedruckten ab: Zuordnung in `korrektor/auswertung.py` (Kernvergleich, Mehrfachabdeckung, Dubletten), Klickfeld `urteil` statt `echt` auf der Prüfseite, robustere Verarbeitung kaputter Modellantworten, angepasste Testtexte A, B und D. Maßgeblich ist der Code im Repository. Offen sind Task 8 Step 1 (Modellkennungen), Task 9, Task 11 und Task 15 Step 3–5. In Task 11 gibt `aus_antwort`/`funde_bauen` unverändert eine Fundliste zurück; die dort abgedruckten Netzaufrufe passen weiterhin.

**Hinweise für die Umsetzung**

- Arbeitsverzeichnis ist immer die Projektwurzel `D:\KI Projekte\Korrektor`. Tests laufen mit `python -m pytest` (so liegt die Wurzel im Suchpfad).
- Das GitHub-Repository ist **öffentlich**. Niemals `.env`, Fotos, Ergebnisse oder die Verlagsbilder (`Text1.jpg`, `text2.jpg`, `text3.jpg`, `text4.jpg`) hinzufügen. `.gitignore` deckt das ab; trotzdem immer Dateien einzeln mit `git add <pfad>` aufnehmen, nie `git add .`.
- Es werden ausschließlich selbst geschriebene Texte an die Dienste geschickt.
- Vor Task 8 und 11 den Skill `claude-api` laden und Modellkennung sowie Aufrufform dagegen prüfen. Für Gemini, OpenAI und Cloud Vision vor dem jeweiligen Task die aktuelle Anbieterdokumentation aufrufen. Weicht eine Aufrufform ab, nur die Funktion `fragen` bzw. `vision_lesen` anpassen; die Schnittstelle bleibt.
- Abweichung von der Verzeichnisskizze der Spezifikation: Der Code liegt im Paket `korrektor/`, die Startskripte (`lauf.py`, `pruefseite.py`, `auswerten.py`, `vorlagen_bauen.py`) in der Wurzel.

## Dateiübersicht

| Datei | Aufgabe |
|---|---|
| `requirements.txt`, `einstellungen.toml`, `.env.beispiel` | Abhängigkeiten, Modellkennungen und Schwellen, Muster für Schlüssel |
| `korrektor/vorlagen.py` | Vorlage mit Markierungen in Abschreibtext und Lösung zerlegen |
| `vorlagen_bauen.py` | erzeugt aus `vorlagen/*.vorlage.txt` die Abschreibtexte und Lösungsdateien |
| `vorlagen/A…D.vorlage.txt` | die vier Testtexte mit markierten Fehlern und Fallen |
| `korrektor/ergebnis.py` | einheitliches Ergebnisformat, Rahmen beschneiden, speichern |
| `korrektor/koordinaten.py` | Umrechnung aller Koordinatenformate in Pixelrahmen |
| `korrektor/bild.py` | Foto laden, drehen, verkleinern, Ausschnitt |
| `korrektor/anweisung.py` | gemeinsame Anweisung an die Modelle, JSON aus Antwort lesen |
| `korrektor/verfahren/allein.py` | gemeinsamer Ablauf für Verfahren 1–3 |
| `korrektor/verfahren/gemini.py`, `claude.py`, `gpt.py` | je ein Netzaufruf |
| `korrektor/verfahren/vision_kombi.py` | Verfahren 4 |
| `lauf.py` | startet Verfahren für Fotos, überspringt Vorhandenes |
| `korrektor/auswertung.py` | Zuordnung, Messgrößen, Schwellen |
| `pruefseite.py` | lokale Seite für die Klicks |
| `korrektor/bericht.py`, `auswerten.py` | `bericht.html` erzeugen |
| `tests/` | pytest-Tests |

---

### Task 1: Grundgerüst

**Files:**
- Create: `requirements.txt`, `einstellungen.toml`, `.env.beispiel`, `korrektor/__init__.py`, `korrektor/verfahren/__init__.py`, `tests/__init__.py`

- [ ] **Step 1: Python-Version prüfen**

Run: `python --version`
Expected: 3.11 oder höher (wegen `tomllib`). Falls niedriger: abbrechen und melden.

- [ ] **Step 2: Dateien anlegen**

`requirements.txt`:
```
anthropic
openai
google-genai
google-cloud-vision
pillow
python-dotenv
flask
pytest
```

`einstellungen.toml`:
```toml
# Längste Bildkante in Pixeln, mit der Fotos an die Dienste gehen
max_kante = 2400

[modelle]
# Kennungen vor dem ersten Lauf gegen die Anbieterdokumentation prüfen.
# Ein leerer Eintrag schaltet das Verfahren ab.
gemini = "gemini-4-hydrogen"
claude = "claude-fable-5-2"
gpt = ""
vision_analyse = "claude-fable-5-2"

[vision]
# Unter diesem Vertrauenswert gilt ein Wort als unsicher gelesen
sicherheit_schwelle = 0.6

[schwellen]
gefunden_min = 0.85
erfunden_pro_seite_max = 1.0
platzierung_min = 0.90
```

`.env.beispiel`:
```
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
GEMINI_API_KEY=
GOOGLE_CLOUD_PROJECT=
```

`korrektor/__init__.py`, `korrektor/verfahren/__init__.py`, `tests/__init__.py`: leere Dateien.

- [ ] **Step 3: Umgebung einrichten**

Run:
```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements.txt
```
Expected: Installation ohne Fehler.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt einstellungen.toml .env.beispiel korrektor/__init__.py korrektor/verfahren/__init__.py tests/__init__.py
git commit -m "chore: Grundgerüst für den Machbarkeitstest"
```

---

### Task 2: Vorlagen zerlegen

Eine Vorlage ist ein Text mit Markierungen: `[R:falsch|richtig]`, `[Z:falsch|richtig]`, `[Gr:falsch|richtig]` für Fehler und `{Wort}` für Fallen. Abgeschrieben wird die Fassung mit den falschen Schreibungen.

**Files:**
- Create: `korrektor/vorlagen.py`, `vorlagen_bauen.py`
- Test: `tests/test_vorlagen.py`

- [ ] **Step 1: Test schreiben**

`tests/test_vorlagen.py`:
```python
from korrektor.vorlagen import parsen


def test_parsen_zerlegt_fehler_und_fallen():
    markup = "Das [R:Fahrad|Fahrrad] steht da, [Z:weil es|, weil es] {Rhythmus} hat."
    ergebnis = parsen(markup)
    assert ergebnis["soll_text"] == "Das Fahrad steht da, weil es Rhythmus hat."
    assert ergebnis["fehler"] == [
        {"id": 1, "kategorie": "R", "falsch": "Fahrad", "richtig": "Fahrrad"},
        {"id": 2, "kategorie": "Z", "falsch": "weil es", "richtig": ", weil es"},
    ]
    assert ergebnis["fallen"] == ["Rhythmus"]


def test_parsen_ohne_markierung():
    assert parsen("Nur Text.") == {"soll_text": "Nur Text.", "fehler": [], "fallen": []}
```

- [ ] **Step 2: Test laufen lassen**

Run: `python -m pytest tests/test_vorlagen.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'korrektor.vorlagen'`

- [ ] **Step 3: Umsetzen**

`korrektor/vorlagen.py`:
```python
"""Zerlegt eine Vorlage mit Markierungen in Abschreibtext, Fehlerliste und Fallen."""
import re

MUSTER = re.compile(r"\[(R|Z|Gr):([^|\]]+)\|([^\]]+)\]|\{([^}]+)\}")


def parsen(markup: str) -> dict:
    teile, fehler, fallen = [], [], []
    pos = 0
    for m in MUSTER.finditer(markup):
        teile.append(markup[pos:m.start()])
        if m.group(1):
            fehler.append({
                "id": len(fehler) + 1,
                "kategorie": m.group(1),
                "falsch": m.group(2),
                "richtig": m.group(3),
            })
            teile.append(m.group(2))
        else:
            fallen.append(m.group(4))
            teile.append(m.group(4))
        pos = m.end()
    teile.append(markup[pos:])
    return {"soll_text": "".join(teile).strip(), "fehler": fehler, "fallen": fallen}
```

`vorlagen_bauen.py`:
```python
"""Erzeugt aus vorlagen/<X>.vorlage.txt den Abschreibtext und die Lösungsdatei."""
import json
from pathlib import Path

from korrektor.vorlagen import parsen

ORDNER = Path(__file__).parent / "vorlagen"

for vorlage in sorted(ORDNER.glob("*.vorlage.txt")):
    name = vorlage.name.removesuffix(".vorlage.txt")
    daten = parsen(vorlage.read_text(encoding="utf-8"))
    (ORDNER / f"{name}.abschreiben.txt").write_text(daten["soll_text"] + "\n", encoding="utf-8")
    (ORDNER / f"loesung_{name}.json").write_text(
        json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{name}: {len(daten['fehler'])} Fehler, {len(daten['fallen'])} Fallen")
```

- [ ] **Step 4: Test laufen lassen**

Run: `python -m pytest tests/test_vorlagen.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add korrektor/vorlagen.py vorlagen_bauen.py tests/test_vorlagen.py
git commit -m "feat: Vorlagen mit Fehlermarkierungen zerlegen"
```

---

### Task 3: Die vier Testtexte

**Files:**
- Create: `vorlagen/A.vorlage.txt`, `vorlagen/B.vorlage.txt`, `vorlagen/C.vorlage.txt`, `vorlagen/D.vorlage.txt`
- Erzeugt: `vorlagen/*.abschreiben.txt`, `vorlagen/loesung_*.json`

- [ ] **Step 1: Vorlagen anlegen** (jeweils ein Absatz, UTF-8)

`vorlagen/A.vorlage.txt`:
```
Am Anfang war nichts da, überhaupt nichts. Doch [R:plözlich|plötzlich] gab es einen riesigen Knall und es wurde {unvorstellbar} hell. Langsam wurde das Licht dunkler, aber man hatte das [Z:Gefühl dass|Gefühl, dass] es nie ganz [R:weg ging|wegging]. In dem Gas schwebten winzige Teilchen, die man mit einem normalen Auge nicht sehen konnte. Damit wir nicht immer winzige Teilchen sagen [Z:müssen nennen|müssen, nennen] wir sie einfach Atome. Das kleinste Atom heißt Wasserstoff. [R:Irgendwan|Irgendwann] hatte das [R:licht|Licht] eine runde Form angenommen und wir können es Sonne nennen. Zwei {Wasserstoff-Atome} gerieten in den Sonnenkern. Sie merkten nur noch ganz [R:kurz, das sie|kurz, dass sie] [R:zusammen gequetscht|zusammengequetscht] wurden. Unter viel Druck und Hitze [Gr:verschmolzten|verschmolzen] sie zu einem [Gr:neuem|neuen] Atom. Am besten nennen wir es {Helium}. Alle anderen Atome wunderten sich und eines flüsterte: „Wo sind [R:den|denn] die beiden hin?“ {Wahrscheinlich} sind sie [R:mit einander|miteinander] verschmolzen.
```

`vorlagen/B.vorlage.txt`:
```
Im Experiment haben wir eine [R:Baterie|Batterie] mit einer {Leuchtdiode} verbunden. [R:Zu erst|Zuerst] haben wir den Pluspol und den Minuspol angeschlossen. Dann haben wir verschiedene Gegenstände zwischen die [R:enden|Enden] der Kabel gehalten. Bei der Holzkugel hat die Lampe nicht [Z:geleuchtet weil|geleuchtet, weil] Holz den Strom nicht [R:leited|leitet]. Der Nagel aus Eisen hat den {Stromkreis} [R:geschloßen|geschlossen] und die Diode war an. [R:Das selbe|Dasselbe] haben wir mit dem [Z:Radiergummi der|Radiergummi, der] {Büroklammer} und dem Bleistift gemacht. Am [R:ende|Ende] haben wir alle Ergebnisse in einer Tabelle aufgeschrieben. [R:Mann|Man] kann [R:sagen, das|sagen, dass] Metalle den Strom leiten und Kunststoffe [Gr:ihm|ihn] nicht leiten.
```

`vorlagen/C.vorlage.txt`:
```
Viele Schulen diskutieren {zurzeit} [Z:darüber ob|darüber, ob] Handys im Unterricht verboten werden sollten. Meiner Meinung nach spricht einiges [R:dafür, den|dafür, denn] die Geräte lenken stark ab. Wer ständig Nachrichten [Z:bekommt kann|bekommt, kann] sich kaum auf den Stoff konzentrieren. Außerdem zeigen [R:Studien, das|Studien, dass] die Leistungen sinken, wenn das {Smartphone} auf dem Tisch liegt. [R:Anderer seits|Andererseits] lassen sich Handys sinnvoll einsetzen, zum Beispiel beim [R:recherchieren|Recherchieren] oder beim Üben von Vokabeln. Ein generelles Verbot würde uns diese Möglichkeiten [R:weg nehmen|wegnehmen]. Wichtig ist [R:vorallem|vor allem], dass klare Regeln [Z:gelten an|gelten, an] die sich alle halten. Im [R:großen und ganzen|Großen und Ganzen] halte ich [Gr:ein|einen] {Kompromiss} für die beste Lösung. Die Lehrkraft [Z:entscheidet wann|entscheidet, wann] die Geräte benutzt werden dürfen. So lernen wir, {verantwortungsvoll} mit der Technik [R:um zu gehen|umzugehen], anstatt sie nur heimlich zu benutzen. Letztendlich profitiert davon die ganze [R:Klassengemeinschafft|Klassengemeinschaft].
```

`vorlagen/D.vorlage.txt`:
```
Die {Kurzgeschichte} „Der letzte Bus“ handelt von einem Jungen namens [Z:Jonas der|Jonas, der] nachts allein an einer Haltestelle wartet. Zu Beginn erfährt der [R:Leser, das|Leser, dass] Jonas nach einem Streit mit seinem Vater von {zu Hause} [R:weg gelaufen|weggelaufen] ist. Während er [Z:wartet setzt|wartet, setzt] sich eine alte Frau neben [Gr:ihm|ihn] und beginnt ein Gespräch. Sie erzählt ihm, dass sie als Jugendliche das [R:gleiche|Gleiche] getan hat und es bis [R:Heute|heute] bereut. Jonas hört zunächst nur [R:wiederwillig|widerwillig] zu, doch {allmählich} wird er nachdenklich. Als der Bus [R:schliesslich|schließlich] [Z:kommt steigt|kommt, steigt] er nicht ein. [R:Statt dessen|Stattdessen] ruft er seinen Vater an und bittet ihn, ihn [R:ab zu holen|abzuholen]. Die Geschichte endet damit, dass die beiden schweigend {nachhause} fahren. Der Autor will [R:zeigen, das|zeigen, dass] ein Gespräch mit einem Fremden manchmal mehr bewirkt als viele Vorwürfe.
```

- [ ] **Step 2: Abschreibtexte und Lösungen erzeugen**

Run: `python vorlagen_bauen.py`
Expected:
```
A: 12 Fehler, 4 Fallen
B: 12 Fehler, 3 Fallen
C: 14 Fehler, 4 Fallen
D: 13 Fehler, 4 Fallen
```

- [ ] **Step 3: Sichtprüfung**

`vorlagen/C.abschreiben.txt` öffnen: Der Text enthält keine Klammern mehr und die falschen Schreibungen („darüber ob“, „Anderer seits“).

- [ ] **Step 4: Commit**

```bash
git add vorlagen/
git commit -m "feat: vier Testtexte mit Lösungen"
```

---

### Task 4: Ergebnisformat

**Files:**
- Create: `korrektor/ergebnis.py`
- Test: `tests/test_ergebnis.py`

- [ ] **Step 1: Test schreiben**

`tests/test_ergebnis.py`:
```python
import json

from korrektor import ergebnis


def test_beschneiden_haelt_rahmen_im_bild():
    assert ergebnis.beschneiden([-10, 20, 50, 30], (100, 40)) == [0, 20, 40, 20]
    assert ergebnis.beschneiden([10, 10, 20, 20], (100, 100)) == [10, 10, 20, 20]


def test_fund_merkt_beschneidung():
    f = ergebnis.fund(1, "R", "Fahrad", "Fahrrad", "wort", [90, 0, 30, 10], (100, 100), 0.9)
    assert f["anker"] == {"typ": "wort", "rahmen": [90, 0, 10, 10]}
    assert f["rahmen_beschnitten"] is True
    assert f["unsicher_gelesen"] is False


def test_speichern_schreibt_nach_verfahren_und_bild(tmp_path):
    erg = ergebnis.ergebnis("C_1_gerade.jpg", "gemini", {"lesen": "m", "analyse": "m"}, (100, 200))
    ziel = ergebnis.speichern(tmp_path, erg)
    assert ziel == tmp_path / "ergebnisse" / "gemini" / "C_1_gerade.json"
    gelesen = json.loads(ziel.read_text(encoding="utf-8"))
    assert gelesen["funde"] == [] and gelesen["fehlermeldung"] is None
    assert gelesen["bildgroesse"] == [100, 200]
```

- [ ] **Step 2: Test laufen lassen**

Run: `python -m pytest tests/test_ergebnis.py -v`
Expected: FAIL mit `ImportError`

- [ ] **Step 3: Umsetzen**

`korrektor/ergebnis.py`:
```python
"""Einheitliches Ergebnisformat aller Verfahren (Spezifikation Abschnitt 5)."""
import json
from pathlib import Path


def beschneiden(rahmen, bildgroesse):
    """Hält einen Rahmen [x, y, breite, hoehe] innerhalb des Bildes."""
    x, y, b, h = rahmen
    bild_b, bild_h = bildgroesse
    x2 = min(max(x + b, 0), bild_b)
    y2 = min(max(y + h, 0), bild_h)
    x = min(max(x, 0), bild_b)
    y = min(max(y, 0), bild_h)
    return [round(x), round(y), round(x2 - x), round(y2 - y)]


def fund(nr, kategorie, gelesen, vorschlag, typ, rahmen, bildgroesse,
         sicherheit=None, unsicher=False):
    sauber = beschneiden(rahmen, bildgroesse)
    return {
        "id": nr,
        "kategorie": kategorie,
        "gelesen": gelesen,
        "vorschlag": vorschlag,
        "anker": {"typ": typ, "rahmen": sauber},
        "sicherheit": sicherheit,
        "unsicher_gelesen": unsicher,
        "rahmen_beschnitten": sauber != [round(v) for v in rahmen],
    }


def ergebnis(bild, verfahren, modelle, bildgroesse, transkription="", funde=None,
             dauer_s=0.0, nutzung=None, fehlermeldung=None):
    return {
        "bild": bild,
        "verfahren": verfahren,
        "modelle": modelle,
        "bildgroesse": list(bildgroesse),
        "transkription": transkription,
        "funde": funde or [],
        "dauer_s": round(dauer_s, 1),
        "nutzung": nutzung or {"eingabe": 0, "ausgabe": 0},
        "fehlermeldung": fehlermeldung,
    }


def pfad(wurzel, verfahren, bild):
    return Path(wurzel) / "ergebnisse" / verfahren / (Path(bild).stem + ".json")


def speichern(wurzel, erg):
    ziel = pfad(wurzel, erg["verfahren"], erg["bild"])
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text(json.dumps(erg, ensure_ascii=False, indent=2), encoding="utf-8")
    return ziel
```

- [ ] **Step 4: Test laufen lassen**

Run: `python -m pytest tests/test_ergebnis.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add korrektor/ergebnis.py tests/test_ergebnis.py
git commit -m "feat: einheitliches Ergebnisformat"
```

---

### Task 5: Koordinaten

Alle Rahmen im Ergebnis sind `[x, y, breite, hoehe]` in Pixeln des (aufrecht gedrehten) Originalfotos. Gemini liefert `[ymin, xmin, ymax, xmax]` auf 0–1000 normiert. Claude und GPT werden um Anteile 0–1 als `[x, y, breite, hoehe]` gebeten. Cloud Vision liefert Eckpunkte in Pixeln des verkleinert gesendeten Bildes.

**Files:**
- Create: `korrektor/koordinaten.py`
- Test: `tests/test_koordinaten.py`

- [ ] **Step 1: Test schreiben** (bekannte Rechtecke auf einem Bild 1000 × 2000)

`tests/test_koordinaten.py`:
```python
from korrektor import koordinaten as k

GROESSE = (1000, 2000)


def test_gemini_zu_pixel():
    assert k.gemini_zu_pixel([100, 200, 150, 500], GROESSE) == [200, 200, 300, 100]


def test_anteil_zu_pixel():
    assert k.anteil_zu_pixel([0.2, 0.1, 0.3, 0.05], GROESSE) == [200, 200, 300, 100]


def test_ecken_zu_rahmen_rechnet_verkleinerung_zurueck():
    ecken = [(100, 100), (250, 104), (250, 150), (100, 146)]
    assert k.ecken_zu_rahmen(ecken, 0.5) == [200, 200, 300, 100]


def test_vereinigen():
    assert k.vereinigen([[10, 10, 20, 10], [40, 5, 10, 20]]) == [10, 5, 40, 20]


def test_luecke_in_derselben_zeile():
    assert k.luecke([100, 50, 80, 40], [200, 52, 60, 40]) == [180, 50, 20, 40]


def test_luecke_am_zeilenende():
    assert k.luecke([900, 50, 80, 40], [20, 110, 60, 40]) == [980, 50, 12, 40]
    assert k.luecke([900, 50, 80, 40], None) == [980, 50, 12, 40]
```

- [ ] **Step 2: Test laufen lassen**

Run: `python -m pytest tests/test_koordinaten.py -v`
Expected: FAIL mit `ImportError`

- [ ] **Step 3: Umsetzen**

`korrektor/koordinaten.py`:
```python
"""Rechnet die Koordinatenformate der Dienste in [x, y, breite, hoehe] in Pixeln um."""


def gemini_zu_pixel(box, groesse):
    """Gemini: [ymin, xmin, ymax, xmax], normiert auf 0–1000."""
    ymin, xmin, ymax, xmax = box
    b, h = groesse
    return [xmin / 1000 * b, ymin / 1000 * h, (xmax - xmin) / 1000 * b, (ymax - ymin) / 1000 * h]


def anteil_zu_pixel(box, groesse):
    """Claude und GPT: [x, y, breite, hoehe] als Anteile 0–1."""
    x, y, breite, hoehe = box
    b, h = groesse
    return [x * b, y * h, breite * b, hoehe * h]


def ecken_zu_rahmen(ecken, faktor):
    """Cloud Vision: Eckpunkte im verkleinert gesendeten Bild; faktor = gesendet / original."""
    xs = [x / faktor for x, _ in ecken]
    ys = [y / faktor for _, y in ecken]
    return [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]


def vereinigen(rahmenliste):
    x1 = min(r[0] for r in rahmenliste)
    y1 = min(r[1] for r in rahmenliste)
    x2 = max(r[0] + r[2] for r in rahmenliste)
    y2 = max(r[1] + r[3] for r in rahmenliste)
    return [x1, y1, x2 - x1, y2 - y1]


def luecke(links, rechts):
    """Rahmen für die Lücke nach dem Wort `links`. `rechts` ist das Folgewort oder None."""
    lx, ly, lb, lh = links
    ende = lx + lb
    if rechts is not None:
        rx, ry, _, _ = rechts
        if rx > ende and abs(ry - ly) < lh * 0.6:
            return [ende, ly, rx - ende, lh]
    return [ende, ly, lh * 0.3, lh]
```

- [ ] **Step 4: Test laufen lassen**

Run: `python -m pytest tests/test_koordinaten.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add korrektor/koordinaten.py tests/test_koordinaten.py
git commit -m "feat: Koordinatenumrechnung"
```

---

### Task 6: Bild laden und Anweisung

**Files:**
- Create: `korrektor/bild.py`, `korrektor/anweisung.py`
- Test: `tests/test_bild.py`, `tests/test_anweisung.py`

- [ ] **Step 1: Tests schreiben**

`tests/test_bild.py`:
```python
import io

from PIL import Image

from korrektor import bild


def _foto(tmp_path, groesse):
    pfad = tmp_path / "foto.jpg"
    Image.new("RGB", groesse, "white").save(pfad)
    return pfad


def test_laden_verkleinert_und_meldet_originalgroesse(tmp_path):
    daten, groesse, faktor = bild.laden(_foto(tmp_path, (4000, 3000)), 2000)
    assert groesse == (4000, 3000)
    assert faktor == 0.5
    assert Image.open(io.BytesIO(daten)).size == (2000, 1500)


def test_laden_vergroessert_nicht(tmp_path):
    daten, groesse, faktor = bild.laden(_foto(tmp_path, (800, 600)), 2000)
    assert faktor == 1.0
    assert Image.open(io.BytesIO(daten)).size == (800, 600)


def test_ausschnitt_mit_rand(tmp_path):
    daten = bild.ausschnitt(_foto(tmp_path, (1000, 1000)), [100, 100, 200, 40], rand=0.25)
    assert Image.open(io.BytesIO(daten)).size == (220, 60)
```

`tests/test_anweisung.py`:
```python
import pytest

from korrektor.anweisung import RAHMEN_ANTEIL, anweisung, json_lesen


def test_anweisung_enthaelt_rahmenhinweis():
    text = anweisung(RAHMEN_ANTEIL)
    assert "buchstabengetreu" in text
    assert RAHMEN_ANTEIL in text


def test_json_lesen_mit_codezaun_und_vorrede():
    assert json_lesen('Hier:\n```json\n{"funde": []}\n```') == {"funde": []}


def test_json_lesen_ohne_json():
    with pytest.raises(ValueError):
        json_lesen("kein JSON")
```

- [ ] **Step 2: Tests laufen lassen**

Run: `python -m pytest tests/test_bild.py tests/test_anweisung.py -v`
Expected: FAIL mit `ImportError`

- [ ] **Step 3: Umsetzen**

`korrektor/bild.py`:
```python
"""Fotos laden: aufrecht drehen (EXIF), verkleinern, Ausschnitte bilden."""
import io

from PIL import Image, ImageOps


def offen(pfad):
    """Öffnet ein Foto so gedreht, wie ein Browser es anzeigt."""
    return ImageOps.exif_transpose(Image.open(pfad)).convert("RGB")


def als_jpeg(img, qualitaet=90):
    puffer = io.BytesIO()
    img.save(puffer, format="JPEG", quality=qualitaet)
    return puffer.getvalue()


def laden(pfad, max_kante):
    """Gibt (JPEG-Bytes, Originalgröße, Faktor gesendet/original) zurück."""
    img = offen(pfad)
    groesse = img.size
    faktor = min(1.0, max_kante / max(groesse))
    if faktor < 1.0:
        img = img.resize((round(groesse[0] * faktor), round(groesse[1] * faktor)), Image.LANCZOS)
    return als_jpeg(img), groesse, faktor


def ausschnitt(pfad, rahmen, rand=0.25):
    """Schneidet einen Rahmen [x, y, b, h] mit Rand (Anteil der Höhe) aus."""
    img = offen(pfad)
    x, y, b, h = rahmen
    r = h * rand
    kasten = (max(0, round(x - r)), max(0, round(y - r)),
              min(img.width, round(x + b + r)), min(img.height, round(y + h + r)))
    return als_jpeg(img.crop(kasten))
```

`korrektor/anweisung.py`:
```python
"""Gemeinsame Anweisung für die Verfahren 1–3 und JSON-Auslesen."""
import json

RAHMEN_GEMINI = ('"rahmen" ist [ymin, xmin, ymax, xmax], normiert auf 0 bis 1000 '
                 "bezogen auf Bildhöhe und Bildbreite.")
RAHMEN_ANTEIL = ('"rahmen" ist [x, y, breite, hoehe] als Anteile zwischen 0 und 1 '
                 "bezogen auf Bildbreite und Bildhöhe; x und y bezeichnen die linke obere Ecke.")

AUFGABE = """Du unterstützt eine Lehrkraft bei der Korrektur im Fach Deutsch, Jahrgang 9.
Auf dem Foto steht ein handgeschriebener Text.

1. Schreibe den Text buchstabengetreu ab: genau so, wie er dasteht, mit allen Fehlern.
   Berichtige nichts, ergänze keine Satzzeichen. Durchgestrichenes lässt du weg.
   Zeichnungen, Gedrucktes und Randnotizen ignorierst du.
2. Melde alle Fehler dieser Kategorien: R (Rechtschreibung, auch Groß-/Kleinschreibung und
   Getrennt-/Zusammenschreibung), Z (Zeichensetzung), Gr (Grammatik).
   Melde keine Stil-, Ausdrucks- oder Inhaltsfragen. Melde nur, was du sicher gelesen hast.
3. Gib zu jedem Fehler einen Rahmen an, der genau die betroffene Stelle im Foto umschließt.
   Betrifft der Fehler ein Wort oder eine Wortgruppe, ist "anker_typ" gleich "wort".
   Fehlt ein Satzzeichen, ist "anker_typ" gleich "luecke" und der Rahmen umschließt den
   Zwischenraum, in den das Zeichen gehört.
   {rahmenhinweis}

Antworte ausschließlich mit JSON in dieser Form:
{{"transkription": "...",
  "funde": [{{"kategorie": "R", "gelesen": "wie es dasteht", "vorschlag": "richtige Schreibung",
             "anker_typ": "wort", "rahmen": [0, 0, 0, 0], "sicherheit": 0.9}}]}}
Bei "luecke" enthalten "gelesen" und "vorschlag" die beiden Nachbarwörter, einmal ohne und
einmal mit dem Satzzeichen. "sicherheit" liegt zwischen 0 und 1."""


def anweisung(rahmenhinweis):
    return AUFGABE.format(rahmenhinweis=rahmenhinweis)


def json_lesen(text):
    """Liest das erste JSON-Objekt aus einer Modellantwort, auch mit Vorrede oder Codezaun."""
    anfang, ende = text.find("{"), text.rfind("}")
    if anfang == -1 or ende <= anfang:
        raise ValueError("Antwort enthält kein JSON-Objekt")
    return json.loads(text[anfang:ende + 1])
```

- [ ] **Step 4: Tests laufen lassen**

Run: `python -m pytest tests/test_bild.py tests/test_anweisung.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add korrektor/bild.py korrektor/anweisung.py tests/test_bild.py tests/test_anweisung.py
git commit -m "feat: Bildaufbereitung und gemeinsame Anweisung"
```

---

### Task 7: Gemeinsamer Ablauf für Verfahren 1–3

**Files:**
- Create: `korrektor/verfahren/allein.py`
- Test: `tests/test_allein.py`

- [ ] **Step 1: Test schreiben**

`tests/test_allein.py`:
```python
import json

from PIL import Image

from korrektor.koordinaten import anteil_zu_pixel
from korrektor.verfahren import allein

ANTWORT = json.dumps({
    "transkription": "Das Fahrad",
    "funde": [{"kategorie": "R", "gelesen": "Fahrad", "vorschlag": "Fahrrad",
               "anker_typ": "wort", "rahmen": [0.5, 0.1, 0.2, 0.05], "sicherheit": 0.9}],
})


def _foto(tmp_path):
    pfad = tmp_path / "C_1_gerade.jpg"
    Image.new("RGB", (1000, 2000), "white").save(pfad)
    return pfad


def test_erfolgreicher_lauf(tmp_path):
    def fragen(anweisung, jpeg, modell):
        return ANTWORT, {"eingabe": 10, "ausgabe": 5}

    erg = allein.ausfuehren(_foto(tmp_path), "claude", "modell-x", "hinweis",
                            anteil_zu_pixel, fragen, 2400)
    assert erg["verfahren"] == "claude" and erg["bild"] == "C_1_gerade.jpg"
    assert erg["modelle"] == {"lesen": "modell-x", "analyse": "modell-x"}
    assert erg["transkription"] == "Das Fahrad"
    assert erg["funde"][0]["anker"] == {"typ": "wort", "rahmen": [500, 200, 200, 100]}
    assert erg["nutzung"] == {"eingabe": 10, "ausgabe": 5}
    assert erg["fehlermeldung"] is None


def test_zweiter_versuch_nach_fehler(tmp_path):
    aufrufe = []

    def fragen(anweisung, jpeg, modell):
        aufrufe.append(1)
        if len(aufrufe) == 1:
            raise RuntimeError("Netz weg")
        return ANTWORT, {"eingabe": 1, "ausgabe": 1}

    erg = allein.ausfuehren(_foto(tmp_path), "gpt", "m", "h", anteil_zu_pixel, fragen, 2400)
    assert len(aufrufe) == 2 and erg["fehlermeldung"] is None


def test_ausfall_nach_zwei_fehlversuchen(tmp_path):
    def fragen(anweisung, jpeg, modell):
        return "kein JSON", {"eingabe": 1, "ausgabe": 1}

    erg = allein.ausfuehren(_foto(tmp_path), "gemini", "m", "h", anteil_zu_pixel, fragen, 2400)
    assert erg["funde"] == []
    assert "ValueError" in erg["fehlermeldung"]
```

- [ ] **Step 2: Test laufen lassen**

Run: `python -m pytest tests/test_allein.py -v`
Expected: FAIL mit `ImportError`

- [ ] **Step 3: Umsetzen**

`korrektor/verfahren/allein.py`:
```python
"""Gemeinsamer Ablauf für die Verfahren, in denen ein Modell alles allein macht."""
import time
from pathlib import Path

from korrektor import bild
from korrektor.anweisung import anweisung, json_lesen
from korrektor.ergebnis import ergebnis, fund


def aus_antwort(roh, bildgroesse, umrechnen):
    funde = []
    for nr, f in enumerate(roh.get("funde", []), 1):
        funde.append(fund(nr, f["kategorie"], f.get("gelesen", ""), f.get("vorschlag", ""),
                          f.get("anker_typ", "wort"), umrechnen(f["rahmen"], bildgroesse),
                          bildgroesse, f.get("sicherheit")))
    return roh.get("transkription", ""), funde


def ausfuehren(bildpfad, name, modell, rahmenhinweis, umrechnen, fragen, max_kante):
    """`fragen(anweisung, jpeg_bytes, modell)` liefert (Antworttext, Nutzung)."""
    bildpfad = Path(bildpfad)
    daten, groesse, _ = bild.laden(bildpfad, max_kante)
    modelle = {"lesen": modell, "analyse": modell}
    start = time.time()
    meldung = None
    for _ in range(2):
        try:
            text, nutzung = fragen(anweisung(rahmenhinweis), daten, modell)
            transkription, funde = aus_antwort(json_lesen(text), groesse, umrechnen)
            return ergebnis(bildpfad.name, name, modelle, groesse, transkription, funde,
                            time.time() - start, nutzung)
        except Exception as fehler:
            meldung = f"{type(fehler).__name__}: {fehler}"
    return ergebnis(bildpfad.name, name, modelle, groesse, dauer_s=time.time() - start,
                    fehlermeldung=meldung)
```

- [ ] **Step 4: Test laufen lassen**

Run: `python -m pytest tests/test_allein.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add korrektor/verfahren/allein.py tests/test_allein.py
git commit -m "feat: gemeinsamer Ablauf für Ein-Modell-Verfahren"
```

---

### Task 8: Netzaufrufe für Gemini, Claude, GPT und Startskript

Die drei Module enthalten nur den Netzaufruf und werden nicht per pytest geprüft, sondern in Task 9 mit einem echten Foto.

**Files:**
- Create: `korrektor/verfahren/gemini.py`, `korrektor/verfahren/claude.py`, `korrektor/verfahren/gpt.py`, `lauf.py`
- Modify: `einstellungen.toml` (Modellkennungen)

- [ ] **Step 1: Modellkennungen prüfen und eintragen**

Skill `claude-api` laden und die Kennung für Claude bestätigen. Für Gemini `https://ai.google.dev/gemini-api/docs/models` und für OpenAI `https://platform.openai.com/docs/models` aufrufen. Je Anbieter das leistungsstärkste allgemein verfügbare Modell mit Bildeingabe wählen und in `einstellungen.toml` unter `[modelle]` eintragen (`gpt` ist bisher leer).

- [ ] **Step 2: Module anlegen**

`korrektor/verfahren/gemini.py`:
```python
"""Verfahren 1: Gemini liest, verortet und analysiert."""
import os

from google import genai
from google.genai import types

from korrektor.anweisung import RAHMEN_GEMINI
from korrektor.koordinaten import gemini_zu_pixel
from korrektor.verfahren import allein

NAME = "gemini"


def fragen(anweisung, jpeg, modell):
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    antwort = client.models.generate_content(
        model=modell,
        contents=[types.Part.from_bytes(data=jpeg, mime_type="image/jpeg"), anweisung],
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    nutzung = antwort.usage_metadata
    return antwort.text, {"eingabe": nutzung.prompt_token_count or 0,
                          "ausgabe": nutzung.candidates_token_count or 0}


def ausfuehren(bildpfad, einst):
    return allein.ausfuehren(bildpfad, NAME, einst["modelle"]["gemini"], RAHMEN_GEMINI,
                             gemini_zu_pixel, fragen, einst["max_kante"])
```

`korrektor/verfahren/claude.py`:
```python
"""Verfahren 2: Claude liest, verortet und analysiert."""
import base64

import anthropic

from korrektor.anweisung import RAHMEN_ANTEIL
from korrektor.koordinaten import anteil_zu_pixel
from korrektor.verfahren import allein

NAME = "claude"


def fragen(anweisung, jpeg, modell, max_tokens=8000):
    """`jpeg` darf None sein; dann geht nur Text an das Modell."""
    inhalt = []
    if jpeg is not None:
        inhalt.append({"type": "image", "source": {
            "type": "base64", "media_type": "image/jpeg",
            "data": base64.b64encode(jpeg).decode()}})
    inhalt.append({"type": "text", "text": anweisung})
    antwort = anthropic.Anthropic().messages.create(
        model=modell, max_tokens=max_tokens,
        messages=[{"role": "user", "content": inhalt}])
    text = "".join(block.text for block in antwort.content if block.type == "text")
    return text, {"eingabe": antwort.usage.input_tokens,
                  "ausgabe": antwort.usage.output_tokens}


def ausfuehren(bildpfad, einst):
    return allein.ausfuehren(bildpfad, NAME, einst["modelle"]["claude"], RAHMEN_ANTEIL,
                             anteil_zu_pixel, fragen, einst["max_kante"])
```

`korrektor/verfahren/gpt.py`:
```python
"""Verfahren 3: GPT liest, verortet und analysiert."""
import base64

from openai import OpenAI

from korrektor.anweisung import RAHMEN_ANTEIL
from korrektor.koordinaten import anteil_zu_pixel
from korrektor.verfahren import allein

NAME = "gpt"


def fragen(anweisung, jpeg, modell):
    bild_url = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()
    antwort = OpenAI().chat.completions.create(
        model=modell,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": [
            {"type": "text", "text": anweisung},
            {"type": "image_url", "image_url": {"url": bild_url}},
        ]}],
    )
    return antwort.choices[0].message.content, {
        "eingabe": antwort.usage.prompt_tokens, "ausgabe": antwort.usage.completion_tokens}


def ausfuehren(bildpfad, einst):
    return allein.ausfuehren(bildpfad, NAME, einst["modelle"]["gpt"], RAHMEN_ANTEIL,
                             anteil_zu_pixel, fragen, einst["max_kante"])
```

`lauf.py`:
```python
"""Startet die Verfahren für alle oder einzelne Fotos. Vorhandene Ergebnisse bleiben stehen."""
import argparse
import importlib
import tomllib
from pathlib import Path

from dotenv import load_dotenv

from korrektor import ergebnis

WURZEL = Path(__file__).parent
# Verfahren -> Eintrag unter [modelle], der gesetzt sein muss
VERFAHREN = {"gemini": "gemini", "claude": "claude", "gpt": "gpt",
             "vision_kombi": "vision_analyse"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verfahren", choices=list(VERFAHREN), action="append",
                        help="mehrfach angebbar; ohne Angabe laufen alle")
    parser.add_argument("--bild", action="append",
                        help="Dateiname in fotos/, mehrfach angebbar; ohne Angabe alle")
    parser.add_argument("--neu", action="store_true", help="vorhandene Ergebnisse überschreiben")
    args = parser.parse_args()

    load_dotenv(WURZEL / ".env")
    einst = tomllib.loads((WURZEL / "einstellungen.toml").read_text(encoding="utf-8"))
    bilder = sorted((WURZEL / "fotos").glob("*.jpg"))
    if args.bild:
        bilder = [b for b in bilder if b.name in args.bild]
    if not bilder:
        parser.error("keine passenden Fotos in fotos/ gefunden")

    for name in args.verfahren or list(VERFAHREN):
        if not einst["modelle"].get(VERFAHREN[name]):
            print(f"{name}: kein Modell eingetragen, übersprungen")
            continue
        modul = importlib.import_module(f"korrektor.verfahren.{name}")
        for bildpfad in bilder:
            if ergebnis.pfad(WURZEL, name, bildpfad.name).exists() and not args.neu:
                print(f"{name} {bildpfad.name}: vorhanden")
                continue
            erg = modul.ausfuehren(bildpfad, einst)
            ergebnis.speichern(WURZEL, erg)
            status = erg["fehlermeldung"] or f"{len(erg['funde'])} Funde"
            print(f"{name} {bildpfad.name}: {status} ({erg['dauer_s']} s)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Prüfen, dass alles importierbar ist**

Run: `python -c "import korrektor.verfahren.gemini, korrektor.verfahren.claude, korrektor.verfahren.gpt; print('ok')"`
Expected: `ok`

Run: `python lauf.py --help`
Expected: Hilfetext mit `--verfahren`, `--bild`, `--neu`

- [ ] **Step 4: Commit**

```bash
git add korrektor/verfahren/gemini.py korrektor/verfahren/claude.py korrektor/verfahren/gpt.py lauf.py einstellungen.toml
git commit -m "feat: Netzaufrufe für Gemini, Claude und GPT sowie Startskript"
```

---

### Task 9: Erster echter Lauf (Haltepunkt, braucht Stephan)

**Voraussetzungen von Stephan:** `.env` aus `.env.beispiel` angelegt und mit den Schlüsseln gefüllt; mindestens ein eigenes Foto in `fotos/`, benannt nach dem Muster `<Text>_<Schreiber>_<Aufnahme>.jpg` mit Aufnahme `gerade` oder `schraeg`, z. B. `fotos/C_1_gerade.jpg`.

- [ ] **Step 1: Voraussetzungen prüfen**

Run: `python -c "from pathlib import Path; print(Path('.env').exists(), [p.name for p in Path('fotos').glob('*.jpg')])"`
Expected: `True` und mindestens ein Dateiname. Sonst anhalten und Stephan um Schlüssel und Foto bitten.

- [ ] **Step 2: Ein Foto durch die drei Verfahren schicken**

Run: `python lauf.py --verfahren gemini --verfahren claude --verfahren gpt --bild C_1_gerade.jpg`
Expected: drei Zeilen der Form `gemini C_1_gerade.jpg: 11 Funde (8.2 s)`, keine Fehlermeldung.

- [ ] **Step 3: Ergebnis ansehen**

`ergebnisse/claude/C_1_gerade.json` öffnen und prüfen: `transkription` ist gefüllt; jeder Fund hat `anker.rahmen` mit vier Zahlen innerhalb von `bildgroesse`; `rahmen_beschnitten` ist überwiegend `false`.

Wenn ein Verfahren eine Fehlermeldung liefert: Meldung lesen, Aufrufform in `fragen` gegen die aktuelle Anbieterdokumentation prüfen, korrigieren, mit `--neu` wiederholen. Wenn die Rahmen eines Verfahrens offensichtlich in einem anderen Format kommen (z. B. Pixel statt Anteile), den Rahmenhinweis in `korrektor/anweisung.py` schärfen, nicht die Umrechnung verbiegen.

- [ ] **Step 4: Commit** (nur falls Code geändert wurde)

```bash
git add korrektor/
git commit -m "fix: Netzaufrufe nach erstem echten Lauf angepasst"
```

---

### Task 10: Verfahren 4 – reine Logik

**Files:**
- Create: `korrektor/verfahren/vision_kombi.py` (zunächst ohne Netzaufrufe)
- Test: `tests/test_vision_kombi.py`

- [ ] **Step 1: Test schreiben**

`tests/test_vision_kombi.py`:
```python
from types import SimpleNamespace as N

from korrektor.verfahren import vision_kombi as vk


def _wort(text, x, y, b, h, sicherheit):
    ecken = [N(x=x, y=y), N(x=x + b, y=y), N(x=x + b, y=y + h), N(x=x, y=y + h)]
    return N(symbols=[N(text=z) for z in text], bounding_box=N(vertices=ecken),
             confidence=sicherheit)


def _annotation(*woerter):
    return N(pages=[N(blocks=[N(paragraphs=[N(words=list(woerter))])])])


WOERTER = [
    {"text": "Das", "rahmen": [100, 100, 60, 40], "sicherheit": 0.99},
    {"text": "Fahrad", "rahmen": [180, 100, 120, 40], "sicherheit": 0.95},
    {"text": "steht", "rahmen": [320, 100, 90, 40], "sicherheit": 0.5},
]


def test_woerter_aus_antwort_rechnet_auf_originalgroesse():
    annotation = _annotation(_wort("Das", 50, 50, 30, 20, 0.99))
    assert vk.woerter_aus_antwort(annotation, 0.5) == [
        {"text": "Das", "rahmen": [100, 100, 60, 40], "sicherheit": 0.99}]


def test_nummerierter_text():
    assert vk.nummerierter_text(WOERTER) == "[0]Das [1]Fahrad [2]steht"


def test_funde_bauen_wort_und_luecke():
    roh = {"funde": [
        {"kategorie": "R", "gelesen": "Fahrad", "vorschlag": "Fahrrad",
         "anker_typ": "wort", "wort_von": 1, "wort_bis": 1, "sicherheit": 0.9},
        {"kategorie": "Z", "gelesen": "Das Fahrad", "vorschlag": "Das, Fahrad",
         "anker_typ": "luecke", "wort_von": 0, "wort_bis": 0, "sicherheit": 0.7},
        {"kategorie": "R", "gelesen": "x", "vorschlag": "y",
         "anker_typ": "wort", "wort_von": 7, "wort_bis": 9},
    ]}
    funde = vk.funde_bauen(roh, WOERTER, (1000, 1000))
    assert len(funde) == 2
    assert funde[0]["anker"] == {"typ": "wort", "rahmen": [180, 100, 120, 40]}
    assert funde[0]["woerter"] == [1, 1]
    assert funde[1]["anker"] == {"typ": "luecke", "rahmen": [160, 100, 20, 40]}


def test_ist_unsicher():
    assert vk.ist_unsicher("Fahrad", "Fahrad", [0.95], 0.6) is False
    assert vk.ist_unsicher("Fahrad", " Fahrad. ", [0.95], 0.6) is False
    assert vk.ist_unsicher("Fahrad", "Fahrrad", [0.95], 0.6) is True
    assert vk.ist_unsicher("steht", "steht", [0.5], 0.6) is True
```

- [ ] **Step 2: Test laufen lassen**

Run: `python -m pytest tests/test_vision_kombi.py -v`
Expected: FAIL mit `ImportError`

- [ ] **Step 3: Umsetzen**

`korrektor/verfahren/vision_kombi.py`:
```python
"""Verfahren 4: Cloud Vision liest und verortet, ein Sprachmodell analysiert und prüft gegen."""
from korrektor.ergebnis import fund
from korrektor.koordinaten import ecken_zu_rahmen, luecke, vereinigen

NAME = "vision_kombi"

ANALYSE = """Du unterstützt eine Lehrkraft bei der Korrektur im Fach Deutsch, Jahrgang 9.
Unten steht ein handgeschriebener Text, den eine Texterkennung gelesen hat. Vor jedem Wort
und Satzzeichen steht seine Nummer in eckigen Klammern. Die Texterkennung kann sich verlesen
haben; melde nur, was nach einem echten Fehler des Schreibers aussieht.

Melde alle Fehler dieser Kategorien: R (Rechtschreibung, auch Groß-/Kleinschreibung und
Getrennt-/Zusammenschreibung), Z (Zeichensetzung), Gr (Grammatik).
Melde keine Stil-, Ausdrucks- oder Inhaltsfragen.

Betrifft der Fehler ein Wort oder eine Wortgruppe, ist "anker_typ" gleich "wort" und
"wort_von" bis "wort_bis" (einschließlich) nennen die betroffenen Nummern.
Fehlt ein Satzzeichen, ist "anker_typ" gleich "luecke" und "wort_von" sowie "wort_bis"
nennen beide die Nummer des Wortes VOR der Stelle, an die das Zeichen gehört.

Antworte ausschließlich mit JSON in dieser Form:
{"funde": [{"kategorie": "R", "gelesen": "wie es dasteht", "vorschlag": "richtige Schreibung",
            "anker_typ": "wort", "wort_von": 0, "wort_bis": 0, "sicherheit": 0.9}]}
Bei "luecke" enthalten "gelesen" und "vorschlag" die beiden Nachbarwörter, einmal ohne und
einmal mit dem Satzzeichen. "sicherheit" liegt zwischen 0 und 1.

Text:
"""

BUCHSTABIEREN = ("Auf dem Bild steht ein handgeschriebenes Wort oder eine kurze Wortgruppe. "
                 "Schreibe buchstabengetreu ab, was dasteht, auch wenn es falsch geschrieben ist. "
                 "Antworte nur mit dem Abgeschriebenen, ohne Anführungszeichen und ohne Erklärung.")


def woerter_aus_antwort(annotation, faktor):
    """Macht aus der Vision-Antwort eine flache Wortliste in Originalkoordinaten."""
    woerter = []
    for seite in annotation.pages:
        for block in seite.blocks:
            for absatz in block.paragraphs:
                for wort in absatz.words:
                    ecken = [(e.x, e.y) for e in wort.bounding_box.vertices]
                    woerter.append({
                        "text": "".join(zeichen.text for zeichen in wort.symbols),
                        "rahmen": ecken_zu_rahmen(ecken, faktor),
                        "sicherheit": wort.confidence,
                    })
    return woerter


def nummerierter_text(woerter):
    return " ".join(f"[{nr}]{wort['text']}" for nr, wort in enumerate(woerter))


def funde_bauen(roh, woerter, bildgroesse):
    funde = []
    for f in roh.get("funde", []):
        von = int(f["wort_von"])
        bis = int(f.get("wort_bis", von))
        if not 0 <= von <= bis < len(woerter):
            continue
        typ = f.get("anker_typ", "wort")
        if typ == "luecke":
            rechts = woerter[von + 1]["rahmen"] if von + 1 < len(woerter) else None
            rahmen = luecke(woerter[von]["rahmen"], rechts)
        else:
            rahmen = vereinigen([wort["rahmen"] for wort in woerter[von:bis + 1]])
        eintrag = fund(len(funde) + 1, f["kategorie"], f.get("gelesen", ""),
                       f.get("vorschlag", ""), typ, rahmen, bildgroesse, f.get("sicherheit"))
        eintrag["woerter"] = [von, bis]
        funde.append(eintrag)
    return funde


def ist_unsicher(ocr_text, buchstabiert, sicherheiten, schwelle):
    """Unsicher, wenn die Gegenlesung abweicht oder die Texterkennung selbst zweifelt."""
    gleich = ocr_text.strip() == buchstabiert.strip().strip(".,;:!?\"„“ ")
    return (not gleich) or min(sicherheiten) < schwelle
```

- [ ] **Step 4: Test laufen lassen**

Run: `python -m pytest tests/test_vision_kombi.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add korrektor/verfahren/vision_kombi.py tests/test_vision_kombi.py
git commit -m "feat: Logik für Cloud Vision plus Sprachmodell"
```

---

### Task 11: Verfahren 4 – Netzaufrufe (Haltepunkt, braucht Stephan)

**Voraussetzungen von Stephan:** Google-Cloud-Projekt mit freigeschalteter „Cloud Vision API“ und Abrechnung; `gcloud` installiert; einmalig angemeldet mit

```powershell
gcloud auth application-default login
```
```powershell
gcloud auth application-default set-quota-project PROJEKT_ID
```

**Files:**
- Modify: `korrektor/verfahren/vision_kombi.py` (am Dateiende ergänzen, Importe oben ergänzen)

- [ ] **Step 1: Aufrufform prüfen**

`https://cloud.google.com/vision/docs/handwriting` und die Seite zu regionalen Endpunkten aufrufen; bestätigen, dass `eu-vision.googleapis.com` für `document_text_detection` gilt. Skill `claude-api` für die Claude-Aufrufe laden.

- [ ] **Step 2: Netzaufrufe ergänzen**

Importe am Dateianfang von `korrektor/verfahren/vision_kombi.py` ersetzen durch:
```python
import time
from pathlib import Path

from google.cloud import vision

from korrektor import bild
from korrektor.anweisung import json_lesen
from korrektor.ergebnis import ergebnis, fund
from korrektor.koordinaten import ecken_zu_rahmen, luecke, vereinigen
from korrektor.verfahren import claude
```

Am Dateiende anfügen:
```python
def vision_lesen(jpeg):
    """Schickt das Bild an Cloud Vision (EU-Endpunkt) und gibt die Textannotation zurück."""
    client = vision.ImageAnnotatorClient(
        client_options={"api_endpoint": "eu-vision.googleapis.com"})
    antwort = client.document_text_detection(image=vision.Image(content=jpeg))
    if antwort.error.message:
        raise RuntimeError(antwort.error.message)
    return antwort.full_text_annotation


def gegenpruefen(funde, woerter, bildpfad, modell, schwelle):
    """Lässt jeden R-Fund am Bildausschnitt buchstabieren und kennzeichnet Zweifel."""
    nutzung = {"eingabe": 0, "ausgabe": 0}
    for f in funde:
        if f["kategorie"] != "R" or f["anker"]["typ"] != "wort":
            continue
        von, bis = f["woerter"]
        betroffen = woerter[von:bis + 1]
        ausschnitt = bild.ausschnitt(bildpfad, f["anker"]["rahmen"])
        text, verbrauch = claude.fragen(BUCHSTABIEREN, ausschnitt, modell, max_tokens=100)
        f["gegenlesung"] = text.strip()
        f["unsicher_gelesen"] = ist_unsicher(
            " ".join(wort["text"] for wort in betroffen), text,
            [wort["sicherheit"] for wort in betroffen], schwelle)
        nutzung["eingabe"] += verbrauch["eingabe"]
        nutzung["ausgabe"] += verbrauch["ausgabe"]
    return nutzung


def ausfuehren(bildpfad, einst):
    bildpfad = Path(bildpfad)
    modell = einst["modelle"]["vision_analyse"]
    modelle = {"lesen": "cloud-vision-document-text", "analyse": modell}
    daten, groesse, faktor = bild.laden(bildpfad, einst["max_kante"])
    start = time.time()
    meldung = None
    for _ in range(2):
        try:
            annotation = vision_lesen(daten)
            woerter = woerter_aus_antwort(annotation, faktor)
            text, nutzung = claude.fragen(ANALYSE + nummerierter_text(woerter), None, modell)
            funde = funde_bauen(json_lesen(text), woerter, groesse)
            zusatz = gegenpruefen(funde, woerter, bildpfad, modell,
                                  einst["vision"]["sicherheit_schwelle"])
            nutzung = {"eingabe": nutzung["eingabe"] + zusatz["eingabe"],
                       "ausgabe": nutzung["ausgabe"] + zusatz["ausgabe"]}
            return ergebnis(bildpfad.name, NAME, modelle, groesse, annotation.text, funde,
                            time.time() - start, nutzung)
        except Exception as fehler:
            meldung = f"{type(fehler).__name__}: {fehler}"
    return ergebnis(bildpfad.name, NAME, modelle, groesse, dauer_s=time.time() - start,
                    fehlermeldung=meldung)
```

- [ ] **Step 3: Tests laufen lassen**

Run: `python -m pytest -v`
Expected: alle Tests bestanden (die Logiktests aus Task 10 laufen weiter).

- [ ] **Step 4: Echter Lauf mit einem Foto**

Run: `python lauf.py --verfahren vision_kombi --bild C_1_gerade.jpg`
Expected: `vision_kombi C_1_gerade.jpg: 12 Funde (… s)` ohne Fehlermeldung. In `ergebnisse/vision_kombi/C_1_gerade.json` haben R-Funde ein Feld `gegenlesung`.

Bei `PermissionDenied` oder `DefaultCredentialsError`: anhalten, Stephan die beiden `gcloud`-Befehle oben ausführen lassen.

- [ ] **Step 5: Commit**

```bash
git add korrektor/verfahren/vision_kombi.py
git commit -m "feat: Netzaufrufe für Cloud Vision plus Sprachmodell"
```

---

### Task 12: Auswertung

Zuordnung: Ein Fund gehört zu einem Lösungsfehler, wenn sein Vorschlag die richtige Schreibung als zusammenhängende Wortfolge enthält oder umgekehrt. Erst werden Paare gleicher Kategorie gesucht, dann beliebige. Jeder Fund und jeder Fehler wird höchstens einmal vergeben.

Klicks der Prüfseite liegen in `pruefseite/klicks.json` als `{"<verfahren>/<bildname ohne Endung>/<fund-id>": {"sitzt": true, "echt": false}}`.

**Files:**
- Create: `korrektor/auswertung.py`
- Test: `tests/test_auswertung.py`

- [ ] **Step 1: Test schreiben**

`tests/test_auswertung.py`:
```python
import json

from korrektor import auswertung as a

LOESUNG = {
    "soll_text": "Das Fahrad steht da weil es Rhythmus hat.",
    "fehler": [
        {"id": 1, "kategorie": "R", "falsch": "Fahrad", "richtig": "Fahrrad"},
        {"id": 2, "kategorie": "Z", "falsch": "da weil", "richtig": "da, weil"},
    ],
    "fallen": ["Rhythmus"],
}


def _fund(nr, kategorie, gelesen, vorschlag):
    return {"id": nr, "kategorie": kategorie, "gelesen": gelesen, "vorschlag": vorschlag,
            "anker": {"typ": "wort", "rahmen": [0, 0, 10, 10]}}


def _ergebnis(funde, transkription, fehlermeldung=None):
    return {"bild": "C_1_gerade.jpg", "verfahren": "x", "transkription": transkription,
            "funde": funde, "dauer_s": 2.0, "nutzung": {"eingabe": 100, "ausgabe": 50},
            "fehlermeldung": fehlermeldung}


def test_enthaelt_und_passt():
    assert a.enthaelt(["a", "b", "c"], ["b", "c"]) and not a.enthaelt(["a", "b"], ["b", "a"])
    assert a.passt("das Fahrrad", "Fahrrad") and a.passt("da, weil", "steht da, weil es")
    assert not a.passt("Fahrrad", "da, weil") and not a.passt("", "Fahrrad")


def test_alles_gefunden():
    funde = [_fund(1, "R", "Fahrad", "Fahrrad"), _fund(2, "Z", "da weil", "da, weil")]
    klicks = {"x/C_1_gerade/1": {"sitzt": True}, "x/C_1_gerade/2": {"sitzt": False}}
    w = a.bild_auswerten(_ergebnis(funde, LOESUNG["soll_text"]), LOESUNG, klicks)
    assert (w["gefunden"], w["fehler_gesamt"], w["erfunden"]) == (2, 2, 0)
    assert (w["lesetreu"], w["lesetreue_gesamt"]) == (1, 1)
    assert (w["platz_sitzt"], w["platz_geprueft"], w["platz_offen"]) == (1, 2, 0)
    assert w["nach_kategorie"] == {"R": [1, 1], "Z": [1, 1], "Gr": [0, 0]}
    assert w["fallen"] == 0 and w["fallen_gesamt"] == 1


def test_nichts_gefunden_und_still_berichtigt():
    w = a.bild_auswerten(_ergebnis([], "Das Fahrrad steht da, weil es Rhythmus hat."),
                         LOESUNG, {})
    assert (w["gefunden"], w["erfunden"], w["lesetreu"]) == (0, 0, 0)


def test_gemischt_mit_erfundenem_fund_und_falle():
    funde = [_fund(1, "R", "Fahrad", "Fahrrad"), _fund(2, "R", "Rhythmus", "Rythmus"),
             _fund(3, "R", "hat", "hatt")]
    klicks = {"x/C_1_gerade/3": {"echt": True, "sitzt": True}}
    w = a.bild_auswerten(_ergebnis(funde, LOESUNG["soll_text"]), LOESUNG, klicks)
    assert (w["gefunden"], w["erfunden"], w["fallen"]) == (1, 1, 1)
    assert w["erfundene"] == [funde[1]]
    assert (w["platz_sitzt"], w["platz_geprueft"], w["platz_offen"]) == (1, 1, 1)


def test_ausfall_wird_gezaehlt():
    w = a.bild_auswerten(_ergebnis([], "", "RuntimeError: x"), LOESUNG, {})
    assert w["ausfall"] == 1


def test_kennzahlen_und_schwelle():
    summe = a.summieren([
        {"seiten": 1, "fehler_gesamt": 10, "gefunden": 9, "erfunden": 1, "lesetreu": 6,
         "lesetreue_gesamt": 8, "fallen": 0, "fallen_gesamt": 4, "platz_sitzt": 9,
         "platz_geprueft": 9, "platz_offen": 0, "ausfall": 0, "dauer_s": 2.0, "eingabe": 1,
         "ausgabe": 1, "nach_kategorie": {"R": [5, 6], "Z": [3, 3], "Gr": [1, 1]},
         "erfundene": []}] * 2)
    k = a.kennzahlen(summe)
    assert k["gefunden"] == 0.9 and k["erfunden_pro_seite"] == 1.0
    assert k["platzierung"] == 1.0 and k["lesetreue"] == 0.75
    assert summe["nach_kategorie"]["R"] == [10, 12]
    schwellen = {"gefunden_min": 0.85, "erfunden_pro_seite_max": 1.0, "platzierung_min": 0.9}
    assert a.bestanden(k, schwellen) is True
    assert a.bestanden({**k, "gefunden": 0.8}, schwellen) is False
    assert a.bestanden({**k, "platzierung": None}, schwellen) is False


def test_loesung_laden_bevorzugt_abschrift(tmp_path):
    ordner = tmp_path / "vorlagen"
    ordner.mkdir()
    (ordner / "loesung_C.json").write_text(json.dumps({"k": "allgemein"}), encoding="utf-8")
    (ordner / "loesung_C_2.json").write_text(json.dumps({"k": "abschrift"}), encoding="utf-8")
    assert a.loesung_laden(tmp_path, "C_1_gerade.jpg") == {"k": "allgemein"}
    assert a.loesung_laden(tmp_path, "C_2_schraeg.jpg") == {"k": "abschrift"}
    assert a.loesung_laden(tmp_path, "X_1_gerade.jpg") is None
```

- [ ] **Step 2: Test laufen lassen**

Run: `python -m pytest tests/test_auswertung.py -v`
Expected: FAIL mit `ImportError`

- [ ] **Step 3: Umsetzen**

`korrektor/auswertung.py`:
```python
"""Ordnet Funde den Lösungsfehlern zu und berechnet die Messgrößen (Spezifikation Abschnitt 6)."""
import json
import re
from pathlib import Path

KATEGORIEN = ("R", "Z", "Gr")
ZAEHLER = ("seiten", "fehler_gesamt", "gefunden", "erfunden", "lesetreu", "lesetreue_gesamt",
           "fallen", "fallen_gesamt", "platz_sitzt", "platz_geprueft", "platz_offen",
           "ausfall", "dauer_s", "eingabe", "ausgabe")


def tokens(text):
    """Wörter und Satzzeichen, Groß-/Kleinschreibung bleibt erhalten."""
    return re.findall(r"\w+|[,.;:!?]", text)


def woerter(text):
    return re.findall(r"\w+", text)


def enthaelt(lang, kurz):
    """True, wenn `kurz` als zusammenhängende Folge in `lang` vorkommt."""
    n = len(kurz)
    return n > 0 and any(lang[i:i + n] == kurz for i in range(len(lang) - n + 1))


def passt(vorschlag, richtig):
    v, r = tokens(vorschlag), tokens(richtig)
    return enthaelt(v, r) or enthaelt(r, v)


def zuordnen(funde, fehler):
    """Gibt {fund_id: fehler_id} zurück. Erst gleiche Kategorie, dann beliebig."""
    zuordnung, vergeben = {}, set()
    for gleiche_kategorie in (True, False):
        for f in funde:
            if f["id"] in zuordnung:
                continue
            for e in fehler:
                if e["id"] in vergeben:
                    continue
                if gleiche_kategorie and f["kategorie"] != e["kategorie"]:
                    continue
                if passt(f["vorschlag"], e["richtig"]):
                    zuordnung[f["id"]] = e["id"]
                    vergeben.add(e["id"])
                    break
    return zuordnung


def bild_auswerten(erg, loesung, klicks):
    funde, fehler = erg["funde"], loesung["fehler"]
    zuordnung = zuordnen(funde, fehler)
    stamm = f"{erg['verfahren']}/{Path(erg['bild']).stem}"

    def klick(f):
        return klicks.get(f"{stamm}/{f['id']}", {})

    offen = [f for f in funde if f["id"] not in zuordnung]
    echte = [f for f in offen if klick(f).get("echt") is True]
    erfundene = [f for f in offen if klick(f).get("echt") is not True]
    zutreffend = [f for f in funde if f["id"] in zuordnung] + echte
    geprueft = [f for f in zutreffend if "sitzt" in klick(f)]

    gelesen = woerter(erg["transkription"])
    lesbar = [e for e in fehler if e["kategorie"] in ("R", "Gr")]
    gefundene_ids = set(zuordnung.values())

    return {
        "seiten": 1,
        "fehler_gesamt": len(fehler),
        "gefunden": len(gefundene_ids),
        "erfunden": len(erfundene),
        "erfundene": erfundene,
        "lesetreu": sum(enthaelt(gelesen, woerter(e["falsch"])) for e in lesbar),
        "lesetreue_gesamt": len(lesbar),
        "fallen": sum(any(enthaelt(woerter(f["gelesen"]), woerter(falle)) for f in offen)
                      for falle in loesung["fallen"]),
        "fallen_gesamt": len(loesung["fallen"]),
        "platz_sitzt": sum(klick(f)["sitzt"] is True for f in geprueft),
        "platz_geprueft": len(geprueft),
        "platz_offen": len(zutreffend) - len(geprueft),
        "ausfall": 1 if erg["fehlermeldung"] else 0,
        "dauer_s": erg["dauer_s"],
        "eingabe": erg["nutzung"]["eingabe"],
        "ausgabe": erg["nutzung"]["ausgabe"],
        "nach_kategorie": {k: [sum(e["id"] in gefundene_ids for e in fehler if e["kategorie"] == k),
                               sum(e["kategorie"] == k for e in fehler)] for k in KATEGORIEN},
    }


def summieren(werte):
    summe = {name: sum(w[name] for w in werte) for name in ZAEHLER}
    summe["nach_kategorie"] = {
        k: [sum(w["nach_kategorie"][k][0] for w in werte),
            sum(w["nach_kategorie"][k][1] for w in werte)] for k in KATEGORIEN}
    return summe


def _anteil(teil, ganzes):
    return round(teil / ganzes, 3) if ganzes else None


def kennzahlen(summe):
    return {
        "gefunden": _anteil(summe["gefunden"], summe["fehler_gesamt"]),
        "erfunden_pro_seite": _anteil(summe["erfunden"], summe["seiten"]),
        "platzierung": _anteil(summe["platz_sitzt"], summe["platz_geprueft"]),
        "lesetreue": _anteil(summe["lesetreu"], summe["lesetreue_gesamt"]),
        "fallen": _anteil(summe["fallen"], summe["fallen_gesamt"]),
    }


def bestanden(k, schwellen):
    if None in (k["gefunden"], k["erfunden_pro_seite"], k["platzierung"]):
        return False
    return (k["gefunden"] >= schwellen["gefunden_min"]
            and k["erfunden_pro_seite"] <= schwellen["erfunden_pro_seite_max"]
            and k["platzierung"] >= schwellen["platzierung_min"])


def loesung_laden(wurzel, bildname):
    """Bevorzugt die Lösung für die einzelne Abschrift (loesung_C_2.json) vor loesung_C.json."""
    teile = Path(bildname).stem.split("_")
    kandidaten = [f"loesung_{teile[0]}.json"]
    if len(teile) > 1:
        kandidaten.insert(0, f"loesung_{teile[0]}_{teile[1]}.json")
    for name in kandidaten:
        datei = Path(wurzel) / "vorlagen" / name
        if datei.exists():
            return json.loads(datei.read_text(encoding="utf-8"))
    return None


def klicks_laden(wurzel):
    datei = Path(wurzel) / "pruefseite" / "klicks.json"
    return json.loads(datei.read_text(encoding="utf-8")) if datei.exists() else {}


def alles(wurzel):
    """Wertet alle Ergebnisse aus. Text H (Härtetest) zählt nicht mit.

    Rückgabe: {verfahren: {"gesamt": summe, "gerade": summe, "schraeg": summe,
                           "erfundene": [(bildname, fund), ...]}}
    """
    klicks = klicks_laden(wurzel)
    je_verfahren = {}
    for datei in sorted((Path(wurzel) / "ergebnisse").glob("*/*.json")):
        erg = json.loads(datei.read_text(encoding="utf-8"))
        loesung = loesung_laden(wurzel, erg["bild"])
        if loesung is None or erg["bild"].startswith("H_"):
            continue
        werte = bild_auswerten(erg, loesung, klicks)
        aufnahme = Path(erg["bild"]).stem.split("_")[-1]
        eintrag = je_verfahren.setdefault(erg["verfahren"],
                                          {"alle": [], "gerade": [], "schraeg": [], "erfundene": []})
        eintrag["alle"].append(werte)
        if aufnahme in ("gerade", "schraeg"):
            eintrag[aufnahme].append(werte)
        eintrag["erfundene"] += [(erg["bild"], f) for f in werte["erfundene"]]
    return {name: {"gesamt": summieren(e["alle"]),
                   "gerade": summieren(e["gerade"]) if e["gerade"] else None,
                   "schraeg": summieren(e["schraeg"]) if e["schraeg"] else None,
                   "erfundene": e["erfundene"]}
            for name, e in je_verfahren.items()}
```

- [ ] **Step 4: Test laufen lassen**

Run: `python -m pytest tests/test_auswertung.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add korrektor/auswertung.py tests/test_auswertung.py
git commit -m "feat: Zuordnung und Messgrößen"
```

---

### Task 13: Prüfseite

**Files:**
- Create: `pruefseite.py`
- Test: `tests/test_pruefseite.py`

- [ ] **Step 1: Test schreiben**

`tests/test_pruefseite.py`:
```python
import json

from PIL import Image

import pruefseite


def _aufbauen(tmp_path):
    (tmp_path / "fotos").mkdir()
    Image.new("RGB", (100, 50), "white").save(tmp_path / "fotos" / "C_1_gerade.jpg")
    (tmp_path / "vorlagen").mkdir()
    (tmp_path / "vorlagen" / "loesung_C.json").write_text(json.dumps({
        "soll_text": "Das Fahrad", "fallen": [],
        "fehler": [{"id": 1, "kategorie": "R", "falsch": "Fahrad", "richtig": "Fahrrad"}],
    }), encoding="utf-8")
    ziel = tmp_path / "ergebnisse" / "claude"
    ziel.mkdir(parents=True)
    fund = lambda nr, vorschlag: {"id": nr, "kategorie": "R", "gelesen": "x",
                                  "vorschlag": vorschlag,
                                  "anker": {"typ": "wort", "rahmen": [0, 0, 10, 10]}}
    (ziel / "C_1_gerade.json").write_text(json.dumps({
        "bild": "C_1_gerade.jpg", "verfahren": "claude", "bildgroesse": [100, 50],
        "funde": [fund(1, "Fahrrad"), fund(2, "Unsinn")]}), encoding="utf-8")
    pruefseite.WURZEL = tmp_path
    return pruefseite.app.test_client()


def test_daten_kennzeichnen_zuordnung(tmp_path):
    antwort = _aufbauen(tmp_path).get("/daten").get_json()
    funde = antwort["ergebnisse"][0]["funde"]
    assert [f["zugeordnet"] for f in funde] == [True, False]
    assert antwort["klicks"] == {}


def test_klick_wird_gespeichert(tmp_path):
    client = _aufbauen(tmp_path)
    client.post("/klick", json={"schluessel": "claude/C_1_gerade/2", "feld": "echt", "wert": True})
    client.post("/klick", json={"schluessel": "claude/C_1_gerade/2", "feld": "sitzt", "wert": False})
    gespeichert = json.loads((tmp_path / "pruefseite" / "klicks.json").read_text(encoding="utf-8"))
    assert gespeichert == {"claude/C_1_gerade/2": {"echt": True, "sitzt": False}}


def test_foto_wird_ausgeliefert(tmp_path):
    antwort = _aufbauen(tmp_path).get("/foto/C_1_gerade.jpg")
    assert antwort.status_code == 200 and antwort.mimetype == "image/jpeg"
```

- [ ] **Step 2: Test laufen lassen**

Run: `python -m pytest tests/test_pruefseite.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'pruefseite'`

- [ ] **Step 3: Umsetzen**

`pruefseite.py`:
```python
"""Lokale Prüfseite: zeigt Fotos mit Rahmen und speichert die Klicks zur Platzierung.

Start: python pruefseite.py   ->   http://127.0.0.1:5000
"""
import json
from pathlib import Path

from flask import Flask, Response, jsonify, request

from korrektor import bild
from korrektor.auswertung import klicks_laden, loesung_laden, zuordnen

WURZEL = Path(__file__).parent
app = Flask(__name__)

SEITE = """<!doctype html>
<html lang="de"><head><meta charset="utf-8"><title>Korrektor – Prüfseite</title>
<style>
  body { font-family: system-ui, sans-serif; margin: 0; display: grid;
         grid-template-columns: minmax(0, 1fr) 420px; height: 100vh; }
  #links { overflow: auto; padding: 12px; background: #f3f3f3; }
  #rechts { overflow: auto; padding: 12px; border-left: 1px solid #ccc; }
  #buehne { position: relative; }
  #buehne img { width: 100%; display: block; }
  .rahmen { position: absolute; border: 2px solid #d00; background: rgba(221,0,0,.12);
            box-sizing: border-box; cursor: pointer; }
  .rahmen.luecke { border-color: #06c; background: rgba(0,102,204,.18); }
  .rahmen.aktiv { border-width: 4px; background: rgba(255,200,0,.35); }
  .fund { border: 1px solid #ccc; border-radius: 6px; padding: 8px; margin: 8px 0; }
  .fund.aktiv { border-color: #e6a700; background: #fff8e0; }
  .fund.offen { border-left: 6px solid #888; }
  button { margin: 4px 4px 0 0; padding: 4px 10px; }
  button.gewaehlt { background: #2a7; color: #fff; }
  select { width: 100%; padding: 6px; margin-bottom: 8px; }
  small { color: #555; }
</style></head><body>
<div id="links"><div id="buehne"><img id="foto"></div></div>
<div id="rechts">
  <select id="auswahl"></select>
  <div id="stand"></div>
  <div id="liste"></div>
</div>
<script>
let daten, aktuell = 0;
const el = id => document.getElementById(id);
const stamm = e => e.verfahren + "/" + e.bild.replace(/\\.[^.]+$/, "");

async function laden() {
  daten = await (await fetch("/daten")).json();
  el("auswahl").innerHTML = daten.ergebnisse.map((e, i) =>
    `<option value="${i}">${e.bild} – ${e.verfahren} (${e.funde.length} Funde)</option>`).join("");
  el("auswahl").onchange = ev => { aktuell = +ev.target.value; zeigen(); };
  zeigen();
}

function zeigen() {
  const e = daten.ergebnisse[aktuell];
  if (!e) { el("liste").textContent = "Keine Ergebnisse vorhanden."; return; }
  el("foto").src = "/foto/" + encodeURIComponent(e.bild);
  document.querySelectorAll(".rahmen").forEach(r => r.remove());
  const [bb, bh] = e.bildgroesse;
  let offen = 0;
  el("liste").innerHTML = "";
  for (const f of e.funde) {
    const schluessel = stamm(e) + "/" + f.id;
    const klick = daten.klicks[schluessel] || {};
    const [x, y, b, h] = f.anker.rahmen;
    const r = document.createElement("div");
    r.className = "rahmen " + f.anker.typ;
    r.id = "r" + f.id;
    r.style.cssText = `left:${x / bb * 100}%;top:${y / bh * 100}%;` +
                      `width:${b / bb * 100}%;height:${h / bh * 100}%`;
    r.onclick = () => hervorheben(f.id, true);
    el("buehne").appendChild(r);

    const braucht_echt = !f.zugeordnet;
    const fertig = "sitzt" in klick || (braucht_echt && klick.echt === false);
    if (!fertig) offen++;
    const karte = document.createElement("div");
    karte.className = "fund" + (fertig ? "" : " offen");
    karte.id = "f" + f.id;
    karte.onmouseenter = () => hervorheben(f.id, false);
    karte.innerHTML = `<b>${f.id}. ${f.kategorie}</b> „${f.gelesen}“ → „${f.vorschlag}“
      ${f.unsicher_gelesen ? "<br><small>unsicher gelesen</small>" : ""}
      ${braucht_echt ? "<br><small>steht nicht in der Lösung:</small><br>" +
        knopf(schluessel, "echt", true, "tatsächlich ein Fehler", klick) +
        knopf(schluessel, "echt", false, "erfunden", klick) : ""}
      <br><small>Platzierung:</small><br>
      ${knopf(schluessel, "sitzt", true, "sitzt", klick)}
      ${knopf(schluessel, "sitzt", false, "sitzt nicht", klick)}`;
    el("liste").appendChild(karte);
  }
  el("stand").innerHTML = `<small>${offen} von ${e.funde.length} Funden noch offen` +
    (e.fehlermeldung ? ` · Ausfall: ${e.fehlermeldung}` : "") + `</small>`;
}

function knopf(schluessel, feld, wert, text, klick) {
  const gewaehlt = klick[feld] === wert ? "gewaehlt" : "";
  return `<button class="${gewaehlt}" onclick="klicken('${schluessel}','${feld}',${wert})">${text}</button>`;
}

async function klicken(schluessel, feld, wert) {
  await fetch("/klick", {method: "POST", headers: {"Content-Type": "application/json"},
                         body: JSON.stringify({schluessel, feld, wert})});
  (daten.klicks[schluessel] ||= {})[feld] = wert;
  zeigen();
}

function hervorheben(id, rollen) {
  document.querySelectorAll(".aktiv").forEach(n => n.classList.remove("aktiv"));
  el("r" + id).classList.add("aktiv");
  el("f" + id).classList.add("aktiv");
  (rollen ? el("f" + id) : el("r" + id)).scrollIntoView({block: "nearest"});
}

laden();
</script></body></html>"""


@app.get("/")
def seite():
    return SEITE


@app.get("/daten")
def daten():
    ergebnisse = []
    for datei in sorted((WURZEL / "ergebnisse").glob("*/*.json")):
        erg = json.loads(datei.read_text(encoding="utf-8"))
        loesung = loesung_laden(WURZEL, erg["bild"])
        zuordnung = zuordnen(erg["funde"], loesung["fehler"]) if loesung else {}
        for f in erg["funde"]:
            f["zugeordnet"] = f["id"] in zuordnung
        ergebnisse.append(erg)
    return jsonify({"ergebnisse": ergebnisse, "klicks": klicks_laden(WURZEL)})


@app.get("/foto/<name>")
def foto(name):
    pfad = WURZEL / "fotos" / Path(name).name
    return Response(bild.als_jpeg(bild.offen(pfad)), mimetype="image/jpeg")


@app.post("/klick")
def klick():
    eingang = request.get_json()
    klicks = klicks_laden(WURZEL)
    klicks.setdefault(eingang["schluessel"], {})[eingang["feld"]] = eingang["wert"]
    datei = WURZEL / "pruefseite" / "klicks.json"
    datei.parent.mkdir(exist_ok=True)
    datei.write_text(json.dumps(klicks, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
```

- [ ] **Step 4: Test laufen lassen**

Run: `python -m pytest tests/test_pruefseite.py -v`
Expected: 3 passed

- [ ] **Step 5: Im Browser prüfen**

Run: `python pruefseite.py` und `http://127.0.0.1:5000` öffnen.
Expected: Auswahlliste mit den Ergebnissen aus Task 9 und 11; Rahmen liegen über dem Foto und bleiben beim Verkleinern des Fensters an ihrer Stelle; Klick auf „sitzt“ färbt den Knopf grün und bleibt nach Neuladen der Seite erhalten.

- [ ] **Step 6: Commit**

```bash
git add pruefseite.py tests/test_pruefseite.py
git commit -m "feat: Prüfseite für die Platzierung"
```

---

### Task 14: Bericht

**Files:**
- Create: `korrektor/bericht.py`, `auswerten.py`
- Test: `tests/test_bericht.py`

- [ ] **Step 1: Test schreiben**

`tests/test_bericht.py`:
```python
from korrektor import bericht

SUMME = {"seiten": 2, "fehler_gesamt": 20, "gefunden": 18, "erfunden": 2, "lesetreu": 12,
         "lesetreue_gesamt": 16, "fallen": 1, "fallen_gesamt": 8, "platz_sitzt": 17,
         "platz_geprueft": 18, "platz_offen": 0, "ausfall": 0, "dauer_s": 14.0,
         "eingabe": 4000, "ausgabe": 900,
         "nach_kategorie": {"R": [10, 12], "Z": [6, 6], "Gr": [2, 2]}}
SCHWELLEN = {"gefunden_min": 0.85, "erfunden_pro_seite_max": 1.0, "platzierung_min": 0.9}


def test_prozent():
    assert bericht.prozent(0.9) == "90 %" and bericht.prozent(None) == "–"


def test_html_enthaelt_kennzahlen_und_urteil():
    fund = {"id": 3, "kategorie": "R", "gelesen": "Rhythmus", "vorschlag": "Rythmus"}
    auswertung = {"claude": {"gesamt": SUMME, "gerade": SUMME, "schraeg": None,
                             "erfundene": [("C_1_gerade.jpg", fund)]}}
    html = bericht.html(auswertung, SCHWELLEN, {("claude", "C_1_gerade.jpg", 3): "bericht_bilder/x.jpg"})
    assert "claude" in html and "90 %" in html and "bestanden" in html
    assert "Rythmus" in html and "bericht_bilder/x.jpg" in html
    assert "10/12" in html
```

- [ ] **Step 2: Test laufen lassen**

Run: `python -m pytest tests/test_bericht.py -v`
Expected: FAIL mit `ImportError`

- [ ] **Step 3: Umsetzen**

`korrektor/bericht.py`:
```python
"""Erzeugt bericht.html aus der Auswertung."""
from html import escape

from korrektor.auswertung import KATEGORIEN, bestanden, kennzahlen


def prozent(wert):
    return "–" if wert is None else f"{round(wert * 100)} %"


def _zeile(name, summe, schwellen, urteil):
    k = kennzahlen(summe)
    zellen = [
        escape(name), str(summe["seiten"]), prozent(k["lesetreue"]), prozent(k["gefunden"]),
        "–" if k["erfunden_pro_seite"] is None else f"{k['erfunden_pro_seite']:.1f}",
        prozent(k["platzierung"]) + (f" ({summe['platz_offen']} offen)" if summe["platz_offen"] else ""),
        prozent(k["fallen"]),
        " · ".join(f"{kat} {summe['nach_kategorie'][kat][0]}/{summe['nach_kategorie'][kat][1]}"
                   for kat in KATEGORIEN),
        str(summe["ausfall"]),
        f"{summe['dauer_s'] / summe['seiten']:.1f} s" if summe["seiten"] else "–",
        f"{summe['eingabe']} / {summe['ausgabe']}",
    ]
    if urteil:
        zellen.append("bestanden" if bestanden(k, schwellen) else "nicht bestanden")
    else:
        zellen.append("")
    return "<tr>" + "".join(f"<td>{z}</td>" for z in zellen) + "</tr>"


def html(auswertung, schwellen, ausschnitte):
    """`ausschnitte`: {(verfahren, bildname, fund_id): relativer Bildpfad}."""
    kopf = ["Verfahren", "Seiten", "Lesetreue", "Gefunden", "Erfunden/Seite", "Platzierung",
            "Fallen ausgelöst", "Nach Kategorie", "Ausfälle", "Dauer/Seite",
            "Tokens ein/aus", "Urteil"]
    zeilen, fehlgriffe = [], []
    for name, teil in sorted(auswertung.items()):
        zeilen.append(_zeile(name, teil["gesamt"], schwellen, True))
        for aufnahme in ("gerade", "schraeg"):
            if teil[aufnahme]:
                zeilen.append(_zeile(f"{name} – nur {aufnahme}", teil[aufnahme], schwellen, False))
        for bildname, fund in teil["erfundene"]:
            pfad = ausschnitte.get((name, bildname, fund["id"]))
            bild = f'<br><img src="{escape(pfad)}" style="max-height:80px">' if pfad else ""
            fehlgriffe.append(
                f"<li><b>{escape(name)}</b>, {escape(bildname)}: {escape(fund['kategorie'])} "
                f"„{escape(fund['gelesen'])}“ → „{escape(fund['vorschlag'])}“{bild}</li>")
    return f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8"><title>Korrektor – Bericht</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 24px; }}
  table {{ border-collapse: collapse; }}
  td, th {{ border: 1px solid #ccc; padding: 6px 10px; text-align: left; }}
  th {{ background: #eee; }}
  li {{ margin: 10px 0; }}
</style></head><body>
<h1>Korrektor – Machbarkeitstest</h1>
<p>Schwellen: mindestens {prozent(schwellen['gefunden_min'])} gefunden, höchstens
{schwellen['erfunden_pro_seite_max']:.1f} erfundene Fehler pro Seite, mindestens
{prozent(schwellen['platzierung_min'])} richtig platziert. Text H zählt nicht mit.
Die Platzierung berücksichtigt nur Funde, die auf der Prüfseite bewertet wurden.</p>
<table><tr>{''.join(f'<th>{k}</th>' for k in kopf)}</tr>
{''.join(zeilen)}</table>
<h2>Erfundene Fehler</h2>
<ul>{''.join(fehlgriffe) or '<li>keine</li>'}</ul>
</body></html>"""
```

`auswerten.py`:
```python
"""Berechnet die Messgrößen und schreibt bericht.html."""
import tomllib
from pathlib import Path

from korrektor import bild
from korrektor.auswertung import alles
from korrektor.bericht import html

WURZEL = Path(__file__).parent


def main():
    einst = tomllib.loads((WURZEL / "einstellungen.toml").read_text(encoding="utf-8"))
    auswertung = alles(WURZEL)
    ordner = WURZEL / "bericht_bilder"
    ordner.mkdir(exist_ok=True)
    ausschnitte = {}
    for name, teil in auswertung.items():
        for bildname, fund in teil["erfundene"]:
            ziel = ordner / f"{name}_{Path(bildname).stem}_{fund['id']}.jpg"
            ziel.write_bytes(bild.ausschnitt(WURZEL / "fotos" / bildname,
                                             fund["anker"]["rahmen"], rand=0.5))
            ausschnitte[(name, bildname, fund["id"])] = f"bericht_bilder/{ziel.name}"
    (WURZEL / "bericht.html").write_text(html(auswertung, einst["schwellen"], ausschnitte),
                                         encoding="utf-8")
    print(f"bericht.html geschrieben ({len(auswertung)} Verfahren)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Tests laufen lassen**

Run: `python -m pytest -v`
Expected: alle Tests bestanden

- [ ] **Step 5: Bericht erzeugen und ansehen**

Run: `python auswerten.py`
Expected: `bericht.html geschrieben (4 Verfahren)`; die Datei zeigt je Verfahren eine Zeile und die Liste der erfundenen Fehler mit Bildausschnitt.

- [ ] **Step 6: Commit**

```bash
git add korrektor/bericht.py auswerten.py tests/test_bericht.py
git commit -m "feat: Bericht mit Vergleichstabelle"
```

---

### Task 15: Anleitung und vollständiger Messlauf (braucht Stephan)

**Files:**
- Create: `README.md`

- [ ] **Step 1: Anleitung schreiben**

`README.md`:
````markdown
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
````

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: Anleitung für den Messlauf"
```

- [ ] **Step 3: Vollständiger Lauf** (sobald alle Fotos in `fotos/` liegen)

Run: `python lauf.py`
Expected: je Foto und Verfahren eine Zeile, höchstens vereinzelte Ausfälle.

- [ ] **Step 4: Platzierung bewerten**

Stephan klickt auf der Prüfseite alle Funde durch, bis bei jedem Eintrag „0 von n Funden noch offen“ steht.

- [ ] **Step 5: Bericht erzeugen und Ergebnis besprechen**

Run: `python auswerten.py`
Expected: `bericht.html` mit Urteil je Verfahren. Ergebnis mit Stephan gegen die Bestehensschwelle der Spezifikation (Abschnitt 7) durchgehen und entscheiden, ob und mit welchem Verfahren Teilprojekt 2 (Web-App) beginnt.
