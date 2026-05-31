---
name: Eitech FreeCAD Workbench
description: >
  Skill für die Entwicklung einer FreeCAD-Workbench für Eitech-Metallbaukastenmodelle.
  Aktiviere bei Fragen zu FreeCAD Assembly, Seilvisualisierung, Eitech-Makros,
  den Skripten rope.py, track.py, bom.py, edit_constraints.py, nuts_and_bolts.py
  oder der Eitech-Workbench-Entwicklung allgemein.
version: "2.0"
---

# Eitech FreeCAD Workbench

---

## Projektstand

### Fertig
- ✅ Seilvisualisierung Stufe 1 & 2 (`rope.py`)
- ✅ LCS-Konvention mit `radius`-Property
- ✅ DocumentObserver für Seilaktualisierung
- ✅ Makro: Constraints umbenennen (`rename_constraints.py`)
- ✅ Makro: Kaputte Links reparieren (`repair_links.py` v5)
- ✅ Makro: Raupenketten-Visualisierung (`track.py` v6)
- ✅ Makro: Stückliste (`bom.py` v1)
- ✅ Makro: Labels bereinigen (`fix_labels.py`)
- ✅ Makro: Bindungen editieren (`edit_constraints.py` v2)
- ✅ Makro: Schrauben/Muttern/Gewindestifte (`nuts_and_bolts.py` v0.5)

### Aktives Modell
C18 Raupenkran – Assembly `Zusammenbau_Seilmakro`

---

## Architektur

### LCS-Konvention
- **Bevorzugter Typ: `PartDesign::CoordinateSystem`** (= "Lokales Koordinatensystem" im PartDesign-Menü)
  - Landet sauber innerhalb des `PartDesign::Body` in der Baumansicht
  - Hat eigene `Shape`-Property → eigenständiges geometrisches Objekt
  - `Part::LocalCoordinateSystem` vermeiden: erscheint trotz Body-Mitgliedschaft visuell außerhalb
- **X-Achse = Längsachse / Drehachse**
- Namen: `LCS_rope_groove`, `LCS_winch`, `LCS_anchor`, `LCS_track`, `LCS_bolt`
- `LCS_bolt`: X-Achse zeigt von der Kopfauflagefläche weg in Schraubenrichtung
  - AttachmentOffset: 90° Rotation um Y nötig, damit X-Achse aus der Kreisfläche herauszeigt
  - Attachment auf die kreisförmige Stirnfläche am Schraubenende (MapMode 11)
- Property `radius` (Gruppe `Eitech`, Typ `App::PropertyLength`)
- **Wichtig**: `hasattr(obj, "radius")` → FALSCH → `"radius" in obj.PropertiesList`

### Globales Placement
```python
def get_global_placement(link_obj):
    placement = link_obj.Placement
    current = link_obj
    for _ in range(10):
        in_list = current.InList
        if not in_list: break
        parent = in_list[0]
        if not hasattr(parent, "Placement"): break
        if parent.TypeId == "Assembly::AssemblyObject":
            current = parent; continue
        placement = parent.Placement.multiply(placement)
        current = parent
    return App.Placement(placement)
```

### FreeCAD-spezifische Erkenntnisse
- `hasattr(obj, "radius")` → FALSCH für `App::PropertyLength` mit custom group
- `"radius" in obj.PropertiesList` → RICHTIG
- `Part.makeCircle` macht immer CCW → Bögen als Polylinien aufbauen
- `App::Link.LinkedObject` kann wieder `App::Link` sein → Kette auflösen
- `part.Document.Objects` enthält nicht die Kinder des Body → `OutList` durchsuchen
- `Assembly::AssemblyLink` verlinkt Sub-Assemblies
- `Fold`-Objekte (`App::Link`): gebogene Teile, `LinkedObject.TypeId == "Part::FeaturePython"`
- `suppress_in_BOM` (`App::PropertyBool`, Gruppe Eitech): unterdrückt Teil in Stückliste
- Führende Leerzeichen in Labels möglich → immer `.strip()` verwenden
- `doc.Label` für Anzeige verwenden (nicht `doc.Name` = interner Name)
- `doc.UndoNames` gibt Liste der Undo-Schritte zurück (FreeCAD 1.1)
- `doc.UndoMode = 0` deaktiviert Undo-Aufzeichnung temporär
- `doc.openTransaction(name)` / `doc.commitTransaction()` → alle Änderungen als ein Undo-Schritt
- Gleichnamige Objekte erlaubt (Einstellung in Preferences) → interne Namen (`obj.Name`) sind eindeutig, Labels (`obj.Label`) nicht
- `id(obj)` ist UNZUVERLÄSSIG für FreeCAD-Objekte → immer `obj.Name` für Vergleiche verwenden
- FreeCAD 1.1 nutzt **PySide6**, nicht PySide2 → `from PySide6 import QtWidgets, QtCore`
- `Gui.Selection.getSelectionEx()` gibt bei Klick auf Fläche `doc=PartDoc obj=Feature` zurück, nicht Assembly-Kontext
- `getSelectionEx()` liefert immer das Feature (`PartDesign::Pad` etc.), nie den Assembly-Link
- **Zuverlässige Bauteilidentifikation in Assembly**: `Gui.Selection.getSelectionEx('', 0)` mit `resolve=0`
  - Liefert `SubElementNames=('Winkel_1_x_1L001.Pocket003.;#179:3;:G#1c0;CUT;...',)`
  - Aufbereitung: `full.split(';')[0]` → `'Winkel_1_x_1L001.Pocket003.'` → `.split('.')[0]` → `'Winkel_1_x_1L001'`
  - Damit sind auch mehrere Instanzen desselben Bodies eindeutig identifizierbar
  - Im SelectionObserver `sub`-Parameter: manchmal ohne Präfix (`'Edge29'`) – dann `getSelectionEx('',0)` im delayed callback aufrufen
- `doc` im Observer = Quelldokument des Teils (nicht Assembly), auch wenn Assembly aktiv ist
- Assembly-Kontext nur beim Doppelklick zuverlässig: `doc=AssemblyDoc obj=LinkInternalName`
- **Fixed Joint per Python**:
  - Joints sind `App::FeaturePython` in `Assembly::JointGroup`
  - Anlegen: `joints_group.newObject("App::FeaturePython", "Joint")`, dann `JointObject.Joint(joint, 0)`
  - Referenz-Syntax: `joint.Reference1 = (link_obj, ['EdgeXX', 'EdgeXX'])` – Edge **zweimal** in Liste!
  - `Detach=False` + Referenzen setzen → FreeCAD berechnet `Placement1/2` selbst aus den Edges
  - **NIEMALS** `TaskAssemblyCreateJoint()` aufrufen – startet endlosen Observer mit `ReferenceError`-Flut
- **Flächennormale an Kreiskante**: `raw_obj.Shape.ancestorsOfType(edge, Part.Face)` liefert angrenzende Flächen
  - `raw_obj` = selektiertes Objekt aus `getSelectionEx()`, `edge` = SubObject
  - **Zylinder/Kegel CoG-Methode**: `edge.Curve.Center` und `face.CenterOfGravity` liegen im **gleichen lokalen KS** von `raw_obj` – kein Transformieren nötig!
  - `vec_to_cog = cog - edge.Curve.Center` zeigt ins Material
  - `axis_local = edge.Curve.Axis` (auch lokal) → `dot = vec_to_cog.dot(axis_local)`
  - Wenn `dot > 0`: `axis_global` umdrehen (CoG zeigt in Richtung `real_axis` = Materialseite)
  - `real_axis` aus `getSelectionEx('',0)` ist in **Weltkoordinaten** → nur für Positionierung nutzen, nicht für CoG-Vergleich
  - Fehler: `link_pl.multVec(cog_local)` ist falsch – CoG schon im richtigen KS
- **Shape-Koordinatensystem von App::Link**: `link.Shape` ist ein Compound dessen KS nicht einfach über `link.Placement` in Weltkoord transformierbar ist → immer `ancestorsOfType` auf `raw_obj` nutzen
- **Schrauben-Body**: steht aufrecht entlang Z-Achse, Kopf bei Z=Schraubenlänge
  - Weltposition: `pos = center_global + axis_global * schrauben_laenge`
  - Weltrotation: `App.Rotation(App.Vector(0,0,1), -axis_global)` (Body-Z zeigt ins Material)
  - `axis_global` zeigt vom Material weg (= Kopfseite), ermittelt über Flächennormale der anliegenden ebenen Fläche
- `ViewObject.OverrideMaterial = True` + `ShapeMaterial.DiffuseColor` für pro-Instanz-Einfärbung von `App::Link`
- `ViewObject.Transparency` bei `App::Link` wirkt auf alle Instanzen (nicht pro-Instanz)

### SelectionObserver
```python
class MyObserver:
    def addSelection(self, doc, obj, sub, pnt):
        # doc=AssemblyDoc, obj=LinkName bei Doppelklick auf STEP-Teil
        # doc=PartDoc, obj=Feature bei Klick auf PartDesign-Teil
        # sub='LinkName.Feature.Face' enthält Pfad wenn aus Assembly
        pass
Gui.Selection.addObserver(MyObserver())
# Gui.SelectionObserver existiert NICHT in FreeCAD 1.1
```

---

## kette_visualisierung.py

### Kettengeometrie-Algorithmus
1. `convex_hull_ccw` (Graham Scan) → CCW-Reihenfolge
2. `tangente_aussen(m1,r1,m2,r2,cx,cy)` → Tangentenmittelpunkt am weitesten vom Schwerpunkt
3. Bogenwahl: Bogenmittelpunkt am weitesten vom Schwerpunkt = Außenbogen
4. `point_at_dist_2d` → analytische Position aus 2D-Segmenten
5. Wire: Bögen als Polylinien (5°/Segment)
6. Band+Außenrippen: 2D-Außenkontur → Face → extrude in normal-Richtung
7. Innenrippen: Zylinder per `get_rib_frames_2d`

### Properties am Ketten-Feature
```python
feature.addProperty("App::PropertyLength",    "kette_laenge", "Eitech", "...")
feature.addProperty("App::PropertyInteger",   "kette_n_inner","Eitech", "...")
feature.addProperty("App::PropertyStringList","kette_rollen", "Eitech", "...")
```

### GUI-Konfigurator
- Nicht-modal, vorhandene Ketten oben mit ✏/🗑
- ✏ Editieren: lädt Kette in Tab, entfernt Rollen aus linker Liste
- 🗑 Löschen: entfernt Kette, gibt Rollen zurück
- Suchtiefe-Spinner für Sub-Assemblies
- Wire-Vorschau (orange), Längenanzeige ±%

### Kettenparameter
```python
CHAIN_WIDTH=18.0, BAND_HEIGHT=1.5
OUTER_RIB_H=1.0, OUTER_RIB_W_BOT=2.0, OUTER_RIB_W_TOP=1.5
INNER_RIB_R=2.0, INNER_RIB_W=2.5, INNER_RIB_OFFSET=1.0
```

---

## stueckliste.py

### Objekttypen und Behandlung
| TypeId | Behandlung |
|--------|-----------|
| `App::Link` Label `Kette_*` | Länge aus `kette_laenge`-Property |
| `App::Link` "seil" im Label | → "Seil" |
| `App::Link` `LinkedObject.TypeId=="Part::FeaturePython"` | Fold = gebogenes Teil |
| `App::Link` Sub-Assembly | rekursiv in `Group` |
| `Part::Feature` "seil" im Label | → "Seil" |

### Unterdrückung
- `suppress_in_BOM` (`App::PropertyBool`, Gruppe Eitech) → Teil nicht in BOM
- Prüfung über gesamte Link-Kette

### CSV-Export
- `utf-8-sig` (BOM) für Excel, Semikolon-getrennt
- Neben FCStd-Datei als `Dokumentname_Stueckliste.csv`

---

## Aktive Makros (GitHub Repository)

| Datei | Beschreibung |
|-------|-------------|
| `nuts_and_bolts.py` | Schrauben, Muttern, Gewindestifte einfügen |
| `edit_constraints.py` | Bindungen anzeigen, editieren, löschen (war: loeseBindungen.py) |
| `rope.py` | Seilvisualisierung (war: seil_visualisierung.py) |
| `track.py` | Kettenvisualisierung (war: kette_visualisierung.py) |
| `bom.py` | Stückliste (war: stueckliste.py) |

Nicht mehr aktiv: `bolts.py` (Vorläufer von nuts_and_bolts), `analyse_constraints.py` (ersetzt durch edit_constraints)

### Workflow
1. Makro aufrufen → Dialog „Bindungen" öffnet sich nicht-modal
2. Teil doppelklicken → Bindungen werden geladen, alle Partner hellgrün
3. **Del**-Button pro Bindung: Toggle – gedrückt (rot) = vorgemerkt zum Löschen, Partner verliert Farbe
4. **Edit**-Button: öffnet FreeCAD Joint-Dialog direkt (`c_obj.ViewObject.doubleClicked()`)
5. **Confirm Del**: löscht alle vorgemerkten Bindungen
6. `Alle`/`Keine`: alle Del-Buttons an/aus

### Farben
- **Grün** `(0,0.8,0)`: betrachtetes Teil
- **Hellgrün** `(0.7,1,0.7)`: alle Bindungspartner (außer vorgemerkten)
- **Del-Button rot**: wenn Bindung zum Löschen vorgemerkt
- Farben via `ViewObject.OverrideMaterial` + `ShapeMaterial.DiffuseColor`

### Instanz-Erkennung (SelectionObserver)
- Doppelklick auf STEP-Teil: `doc=Assembly obj=LinkInternalName` → direkt
- Doppelklick auf PartDesign-Body: `doc=PartDoc obj=Feature` → `_find_candidates_for_doc` sucht Links die auf dieses Dokument zeigen
- Bei einem Kandidat: direkt laden; bei mehreren: warten auf eindeutigen Klick

### Sub-Assembly
- Wenn keine Bindungen im aktiven Dokument: `_find_constraints_in_other_docs` folgt Link-Kette

### Undo
- Alle Löschungen in einer Transaktion: `doc.openTransaction(name)` / `doc.commitTransaction()`

---

### SCHRAUBEN_BODIES (nuts_and_bolts.py)
```python
SCHRAUBEN_BODIES = {
    "Schraube 6 Schlitz":  "Body",
    "Schraube 8 Schlitz":  "Body001",
    "Schraube 12 Schlitz": "Body002",
    "Schraube 16 Schlitz": "Body003",
    "Gewindestift":        "Body005",
}
# Mutter: Body004 / Label "Mutter" / LCS_nut = Local_CS002
# Alle in C:\Users\kraska\Documents\Eitech\CAD\Teile\Schrauben.FCStd
```

---

## repair_links.py
- Patcht `Document.xml` direkt (kein `doc.save()`)
- `SEARCH_PATHS = [".."]` rekursiv, Backup `.bak`

---

## Todo-Liste

### Ketten-Visualisierung
- [ ] Lücke in der Kette beheben (Wire-Bug am Übergang Gerade→Bogen)
- [ ] Feature als `App::FeaturePython` für Doppelklick-Editierung

### Stückliste
- [ ] Eitech-Teilenummern und offizielle Bezeichnungen als Properties
- [ ] Spalten Teilenummer + Bezeichnung in Spreadsheet

### Seilvisualisierung
- [ ] Seilmakro-Observer: `Object not found` wenn falsches Dokument aktiv
- [ ] Stufe 3: Seil als Zylinder

### nuts_and_bolts.py
- [ ] Undo-Transaktionen (`openTransaction`/`commitTransaction`)
- [ ] Undo-Bug: bei Undo werden zufällig neue Schrauben eingefügt
- [ ] Schraubendatei-Pfad relativ statt absolut
- [ ] Observer-Umschaltung bei Moduswechsel

### Workbench-Struktur
- [ ] Workbench-Grundstruktur (Toolbar, Menü, Icons)

---

## Performance-Analyse FreeCAD Assembly Solver

### Messungen (Fahrgestell-Assembly, ~100 Links, ~100 Joints)
- `doc.recompute()` Baseline: **1.3s**
- Nach Einfügen eines Joints: **4-9s subjektiv** (asynchroner Solver-Thread blockiert UI)
- Mit 94 GroundedJoints zusätzlich: **99s** – kontraproduktiv
- Suppress-Optimierung (38 Q2.w≈0 Joints): **kaum Verbesserung**
- Reference1↔Reference2 tauschen bei Q2.w≈0: **kein Vorteil**

### Erkenntnisse
- FreeCAD Assembly Solver läuft **asynchron** nach `recompute()` weiter in C++ Thread
- Dieser Thread blockiert die UI und produziert `Solve failed: invalid vector subscript`
- Die `Solve failed` Meldungen kommen von Joints mit `Offset2.Yaw=180°` (manueller Flip)
  → erzeugt Q2.w≈0 in Placement2 → numerische Singularität im Solver
- Q2.w≈0 Joints sind aber **korrekt platzierte Teile** – nur falsche Ausgangsorienterung
- GroundedJoints werden vom Solver **nicht** aus dem Gleichungssystem herausgenommen
- Flaschenhals ist die **schiere Anzahl Joints** (~100) – nicht behebbar mit Python

### Was nicht funktioniert
- `GroundedJoint` auf alle Links → langsamer (mehr Constraints = mehr Solver-Arbeit)
- `Suppressed=True` auf problematischen Joints → Teile wandern weg, Assembly zerrissen
- Reference1↔Reference2 tauschen → kein Effekt auf Performance
- `Std_ToggleFreeze` auf App::Link → ändert nur ShapeCache, nicht Placement

### Was hilft
- **Subassembly-Strategie**: jede Subassembly in sich starr → wenige Joints auf oberster Ebene
- **Schrauben/Muttern ohne Joint**: nur Placement setzen + `Selectable=False` → kein Solver-Trigger (implementiert als Checkbox in nuts_and_bolts_fast.py, aber Mutter-Vorschau fehlt noch)

### Offene Experimente
- [ ] Assembly in `App::Part` / `Part::Compound` konvertieren – Gruppen für gemeinsame Bewegungen, kein Solver
- [ ] `setEditorMode('Placement', 1)` – respektiert der Solver ReadOnly? (noch nicht getestet)
- [ ] Joints mit Q2.w≈0 korrekt reparieren (Offset2 umschreiben ohne Geometrie zu ändern)

### GroundedJoint API
```python
import JointObject
gj = joints_group.newObject('App::FeaturePython', 'GroundedJoint')
JointObject.GroundedJoint(gj, link)  # link als zweites Argument!
# Properties: ObjectToGround, Label, Visibility
# TypeId: App::FeaturePython (wie alle anderen Joints)
```


### edit_constraints.py – v2
(Abschnitt weiter oben im Skill)

---

## FreeCAD-Version
FreeCAD 1.1, Assembly Workbench
Makros: `C:/Users/kraska/AppData/Roaming/FreeCAD/v1-1/Macro/`
Projektordner: `C:/Users/kraska/Documents/Eitech/CAD/`
