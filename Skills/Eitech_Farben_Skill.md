---
## paint.py – Farbeinfärbung (v2, Juli 2026)

### Zweck
Nicht-modaler Farbdialog zum Einfärben von Teilen in Teiledateien und Assembly-Instanzen.
Ersetzt den FreeCAD Appearance-Dialog für den Eitech-Workflow.

### Datei
`C:/Users/kraska/AppData/Roaming/FreeCAD/v1-1/Macro/paint.py`

---

### Materialien

#### Zeile 1 – Gummi / Plastik
Seit Juli 2026 einheitliches generisches Profil für **alle** Farben:
`Specular=(0.60,0.60,0.60)`, `Ambient=(0.30,0.30,0.30)`, `Shininess=0.25`.
Nur `Diffuse` unterscheidet sich je Farbe. Grund und Hintergrund siehe
Abschnitt "Bekanntes FreeCAD-Problem" weiter unten.

| Name    | Diffuse (R,G,B)              | Hinweis                        |
|---------|------------------------------|--------------------------------|
| Schwarz | (0.228, 0.228, 0.228)        | Aufgehellt für Kantensichtbarkeit |
| Rot     | (0.792, 0.148, 0.148)        |                                |
| Orange  | (1.000, 0.506, 0.008)        | Keine Sonderbehandlung mehr nötig (siehe unten) |
| Gelb    | (0.784, 0.659, 0.000)        |                                |
| Beige (C13) | (0.992, 0.729, 0.004)     | Aus HTML `#fdba01`; kommt nur in Kasten C13 vor |
| Blau    | (0.004, 0.329, 0.635)        |                                |
| Grau    | (0.678, 0.710, 0.741)        | Plastik-Grau                   |
| Weiss   | (1.000, 0.984, 0.941)        | Leicht vergilbt                |

**Warum Shininess=0.25 statt ursprünglich 0.05**: Bei niedrigem Shininess wird
das (neutral-graue) Specular-Glanzlicht breit/weich und überdeckt einen großen
Teil der Fläche → Farben wirken blass/verwaschen (an `Rot` beobachtet und
bestätigt). Bei 0.25 satter, ohne dass ein zusätzlicher Gelbstich-Workaround
für Orange nötig wäre (der alte `Shininess=1.0`+warmer-Specular-Sonderfall für
Orange ist damit obsolet und wurde entfernt).

#### Zeile 2 – Metall + Standard-Reset (Shininess 0.90)
Basiert auf FreeCAD-Standardmaterial: Diffuse (173,181,189), Ambient (85,85,85),
Specular (136,136,136), Shininess=90 (GUI) = 0.90 (intern).
Blaustich beibehalten, nur Helligkeit skaliert.

| Name          | Diffuse-Skala | Diffuse (R,G,B)              |
|---------------|---------------|------------------------------|
| Metall hell   | ×1.30         | (0.882, 0.923, 0.964)        |
| Metall mittel | ×1.00         | (0.678, 0.710, 0.741)        |
| Metall dunkel | ×0.65         | (0.441, 0.461, 0.482)        |
| Standard      | ×1.00         | wie Metall mittel – Reset    |

#### FreeCAD Shininess: GUI zeigt 0–100, intern 0–1 (Faktor 100)

---

### Physikalische Grundregeln für Materialien
- **Metalle**: Specular = eingefärbter Glanz (Farbe des Metalls), hohe Shininess (0.90)
- **Nicht-Metalle** (Plastik, Gummi): Specular = neutrales Grau, niedriger-moderater
  Glanz (0.25) – siehe generisches Profil oben; die früher pro Farbe individuell
  abgestimmten Specular/Ambient-Werte (inkl. Orange-Sonderfall) wurden zugunsten
  eines einheitlichen Profils aufgegeben, siehe unten warum
- **Schwarze Teile**: nie reines `(0,0,0)` – Kanten verschwinden; Minimum `(0.15,0.15,0.15)`

---

### Selektionslogik

#### Beim Klick auf Farbbutton
```python
Gui.Selection.getSelectionEx('', 0)  # resolve=0 → Link-Kontext
```
Alle in der **Selection View** gelisteten Objekte werden eingefärbt.
Mehrfachauswahl: im Strukturbaum Ctrl+Klick oder Shift+Klick.

#### Objekttypen und Verhalten
| TypeId | Modus | Methode |
|--------|-------|---------|
| `App::Link` | `"link"` | `ViewObject.OverrideMaterial = True` + `ShapeMaterial` |
| `PartDesign::Body` | `"direct"` | `ViewObject.ShapeAppearance` |
| `PartDesign::Pad` etc. | `"direct"` | `ViewObject.ShapeAppearance` (Feature-Ebene) |

#### Reset
- **Link**: `OverrideMaterial = False` → Original aus Teiledatei wird wieder sichtbar
- **Body/Feature**: Standardmaterial setzen (Diffuse 0.678/0.710/0.741)

---

### Bekanntes FreeCAD-Problem: `App::Link`-Override ist unvollständig (Juli 2026)

**Symptom**: Zwei Teile mit unterschiedlicher Original-Farbe (z.B. weiß und rot),
beide über `paint.py` auf dieselbe Farbe gesetzt, sehen trotzdem sichtbar
unterschiedlich aus (z.B. "golden" vs. "orange" statt beide gleich "beige").

**Ursache (an der Konsole verifiziert)**: Bei `App::Link`-Instanzen wird trotz
`OverrideMaterial=True` **nur `DiffuseColor`** tatsächlich pro Instanz gerendert.
`SpecularColor`, `AmbientColor`, `EmissiveColor` und `Shininess` bleiben immer
von der Original-Teiledatei geerbt, unabhängig vom Override-Flag.

**Bestätigt als offizielles FreeCAD-Problem**:
[GitHub Issue FreeCAD/FreeCAD#19135](https://github.com/FreeCAD/FreeCAD/issues/19135)
("Materials: Linked object needs Material and Appearance overrides"),
eingereicht vom Hauptentwickler des Materials-Systems selbst, als "Feature"
(nicht "Bug") eingestuft → vollständiges Instanz-Override ist noch nicht
implementiert, nicht nur ein kleiner Fehler. Verwandt: #23444 (Linien/Punkte
werden beim Override grau), #14779, #15170 (weitere `ShapeAppearance`-Regressionen).

**⚠️ WICHTIGE GEFAHR – niemals `vp.ShapeAppearance` direkt auf einem Link setzen**:
`ShapeAppearance` (Property-Gruppe "Link", zusammen mit `OverrideMaterial`) sieht
aus wie die richtige, instanzbezogene Property – ist es aber **nicht**. An der
Konsole bestätigt: Ändert man `link.ViewObject.ShapeAppearance`, ändert sich
**auch das Original in der Quelldatei** – und zwar in beide Richtungen (Quelle
ändern färbt auch die Instanz um), **selbst bei `OverrideMaterial=True`**. Diese
Property ist schlicht mit der Quelle verklebt/aliasiert. Ein Fix-Versuch, der
`ShapeAppearance` zusätzlich setzt, wurde deshalb wieder verworfen – er hätte
bei jeder Farbzuweisung die Original-Teiledatei korrumpiert (mit Auswirkung auf
alle Stellen im Projekt, wo dieses Teil verwendet wird).

`ShapeMaterial` (Property-Gruppe "Object Style") ist dagegen tatsächlich
instanzbezogen und sicher – aber wie oben beschrieben wirkt davon eben nur
`DiffuseColor`.

**Workaround (aktueller Stand)**: Da nur `Diffuse` pro Instanz überschreibbar
ist, `Specular`/`Ambient`/`Shininess` aber ohnehin nicht, wurden diese Kanäle
stattdessen **an der Quelldatei selbst** auf ein einheitliches generisches
Profil normiert (siehe `normalize_plastik.py`) – die einzelnen Teiledateien
dürfen sich dadurch nur noch in ihrer eigenen "Hintergrundfarbe" (`Diffuse`,
nur sichtbar wenn man die Teiledatei direkt öffnet, ohne Override) unterscheiden.
`paint.py`s `ROW1` wurde entsprechend auf dasselbe Profil vereinheitlicht
(siehe Materialien-Tabelle oben). Sobald FreeCAD #19135 implementiert ist,
kann die alte pro-Farbe-Feinabstimmung (Orange-Sonderfall etc.) wieder
reaktiviert werden.

**`normalize_plastik.py`** (einmaliges Normalisierungsskript, kein Dauer-Makro):
- Geht durch alle `PartDesign::Body`/`Part::Feature`-Objekte einer Teiledatei
  (z.B. `Plastik.FCStd`)
- Setzt `Specular`/`Ambient`/`Emissive`/`Shininess` auf das generische Profil
- Lässt `Diffuse` pro Teil unverändert (auch bei Mehrfach-Material-Listen,
  jeder Listeneintrag behält seine eigene `Diffuse`)
- Speichert nichts automatisch – Ergebnis erst prüfen, dann selbst speichern
- Für Metall-Teiledateien bräuchte es ein analoges Skript mit dem
  Metall-Profil (`ROW2`/`MAT_STANDARD`-Werte) – noch nicht gebaut

#### Wichtig: Appearance-Dialog vs. Python
- Der FreeCAD Appearance-Dialog schreibt bei Links ins **Original** (Bug in FreeCAD 1.1+)
- `ViewObject.OverrideMaterial = True` per Python + `ShapeMaterial` schreibt
  **nur in die Instanz** → korrekt, aber wirkt eben nur für `DiffuseColor`
  (siehe oben)

---

### GUI
- **Schwebender Dialog** (`Qt.Tool | Qt.WindowStaysOnTopHint`), nicht-modal
- **Statuszeile**: zeigt aktuell selektiertes Objekt + Modus (blau=Link, grün=Body/Feature)
- **Kugel-Icons**: Phong-ähnliche Beleuchtung via `QRadialGradient` – kein externes Bild
  - Ambient=0.45 im Rendering für hellere Darstellung
  - Glanzpunkt: kleiner und schärfer bei hoher Shininess
- **`_SphereButton`**: `QLabel`-Subklasse statt `QPushButton` – kein internes Qt-Padding
- Buttons: 32×32px, Icon 32×32px (füllt Button vollständig)

#### Kugel-Rendering
```python
def make_sphere_pixmap(diffuse, shininess, size=32):
    # Diffuse-Gradient von Lichtquelle (oben-links) nach ambient-dunkel
    # Specular-Gradient: weißer Punkt, Größe ~ (1-shininess), Alpha ~ shininess
    # Rand: schwarze Ellipse mit 80% Deckkraft
```

---

### SelectionObserver (für Statusanzeige)
```python
class _PaintSelObserver:
    def addSelection(self, doc, obj, sub, pnt):
        # Versucht Link via _find_link_from_event zu identifizieren
        # Falls kein Link: prüft ob obj in _DIRECT_TYPES
        # Aktualisiert _selected_objs und Statusanzeige

    def clearSelection(self, doc):
        # Leert _selected_objs
```

`_find_candidates_for_doc`: sucht App::Links im aktiven Dokument die auf
ein bestimmtes Part-Dokument zeigen (bis 4 Ebenen tief).

---

### FCMat-Materialbibliothek
Parallel entwickelt, aber **im laufenden Betrieb nicht verwendet** –
`paint.py` ist direkter und sofort wirksam.

FCMat-Dateien liegen in `%APPDATA%\FreeCAD\Material\Eitech\`.
Format: YAML (FreeCAD 1.1+), Schlüssel `AppearanceModels: Basic Rendering:`.
UUID des Basic-Rendering-Modells: `f006c7e4-35b7-43d5-bbf9-c5d572309e6e`.

Wichtig: FCMat-Änderungen wirken **nicht automatisch** auf bereits zugewiesene Teile –
Werte werden beim Zuweisen in die FCStd-Datei kopiert (keine lebende Verknüpfung).
Assemblies erben Änderungen an Teiledateien automatisch via App::Link.

---

### WebGL-Export (XHTML)
- FreeCAD exportiert über Datei → Exportieren → XHTML
- Verwendet x3dom-Bibliothek; Bug: URLs sind `http://` statt `https://`
  → manuell ersetzen damit GitHub Pages funktioniert
- Nach Export: Farbdarstellung in FreeCAD kann gestört sein (Beleuchtung abgeschaltet)
  → Datei schließen und neu öffnen behebt das Problem
  → In Development-Version gefixt
- Dateigröße bei komplexen Modellen sehr groß (Linsenkopfschrauben mit Gewinde → 68 MB)
- GitHub Pages liefert automatisch gzip-komprimiert aus
