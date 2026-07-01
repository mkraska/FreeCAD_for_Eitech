---
## paint.py – Farbeinfärbung (v1)

### Zweck
Nicht-modaler Farbdialog zum Einfärben von Teilen in Teiledateien und Assembly-Instanzen.
Ersetzt den FreeCAD Appearance-Dialog für den Eitech-Workflow.

### Datei
`C:/Users/kraska/AppData/Roaming/FreeCAD/v1-1/Macro/paint.py`

---

### Materialien

#### Zeile 1 – Gummi / Plastik (Shininess 0.05–1.0)
| Name    | Diffuse (R,G,B)              | Hinweis                        |
|---------|------------------------------|--------------------------------|
| Schwarz | (0.228, 0.228, 0.228)        | Aufgehellt für Kantensichtbarkeit |
| Rot     | (0.792, 0.148, 0.148)        |                                |
| Orange  | (1.000, 0.506, 0.008)        | Shininess=1.0, Specular warm-orange – verhindert Gelbstich |
| Gelb    | (0.784, 0.659, 0.000)        |                                |
| Blau    | (0.004, 0.329, 0.635)        |                                |
| Grau    | (0.678, 0.710, 0.741)        | Plastik-Grau                   |
| Weiss   | (1.000, 0.984, 0.941)        | Leicht vergilbt                |

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
- **Metalle**: Specular = eingefärbter Glanz (Farbe des Metalls), hohe Shininess
- **Nicht-Metalle** (Plastik, Gummi): Specular = neutrales Grau/Weiß, niedriger Glanz
- **Ausnahme Orange**: Specular warm-orange `(1.0, 0.847, 0.690)` + Shininess=1.0
  um Gelbstich bei niedrigem Shininess zu vermeiden
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

#### Wichtig: Appearance-Dialog vs. Python
- Der FreeCAD Appearance-Dialog schreibt bei Links ins **Original** (Bug in FreeCAD 1.1+)
- `ViewObject.OverrideMaterial = True` per Python schreibt **nur in die Instanz** → korrekt

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
