# nuts_and_bolts.py – Dokumentation

**Version**: 0.5  
**Datei**: `C:/Users/kraska/AppData/Roaming/FreeCAD/v1-1/Macro/nuts_and_bolts.py`  
**Zweck**: Halbautomatisches Einfügen von Schrauben, Muttern und Gewindestiften in FreeCAD-Assemblies (Eitech-Metallbaukasten)

---

## Bedienungskonzept

### Grundprinzip

Der Dialog bleibt während der gesamten Arbeitssitzung offen (nicht-modal). Der Benutzer wählt einen Schraubentyp und klickt dann direkt in der 3D-Ansicht Löcher an – ohne Umwege über Menüs oder Dialoge. Die Schraube erscheint sofort mit korrekter Orientierung und optionaler Zufallsdrehung.

Muttern können wahlweise automatisch nach jeder Schraube eingefügt werden, oder nachträglich zu bereits gesetzten Schrauben hinzugefügt werden.

### Dialog-Layout

```
┌─────────────────────────────────┐
│  Schraube 6 Schlitz             │  ← Schrauben-Buttons (einer aktiv = blau)
│  Schraube 8 Schlitz             │
│  Schraube 12 Schlitz            │
│  Schraube 16 Schlitz            │
│  Gewindestift                   │
│─────────────────────────────────│
│  [ Mutter zu Schraube … ]       │  ← blau wenn aktiv
│─────────────────────────────────│
│  ☑ Zufällig drehen              │
│  ☑ Mutter automatisch einfügen  │  ← bei Gewindestift deaktiviert
│─────────────────────────────────│
│  Nachjustieren Schraube …       │
│  Nachjustieren Mutter …         │
│─────────────────────────────────│
│  Statuszeile                    │
└─────────────────────────────────┘
```

---

## Workflows

### 1. Schraube einfügen

1. Schraubentyp-Button klicken (wird blau markiert)
2. Lochrand (kreisförmige Kante) in der 3D-Ansicht anklicken
3. Schraube erscheint sofort an korrekter Position und Orientierung
4. Bei „Zufällig drehen": Schlitz/Kopf zufällig um ±90° in 10°-Schritten gedreht

**Schraube ist fertig.** Nächsten Lochrand anklicken für weitere Schraube.

### 2. Schraube mit Mutter einfügen (automatisch)

1. „Mutter automatisch einfügen" aktivieren
2. Schraubentyp wählen, Lochrand anklicken → Schraube erscheint
3. Vorschau-Mutter erscheint hinter der Schraubenspitze
4. **Auflagefläche der Mutter anklicken** (Fläche auf der Mutter aufliegen soll)
5. Mutter springt auf den Schnittpunkt der Schraubenachse mit der Fläche
6. Bei „Zufällig drehen": Mutter um ±30° in 10°-Schritten gedreht (realistisch für Kontermuttern)

**Tipp**: Wenn die Vorschau-Position nicht passt, einfach eine andere Fläche anklicken.

### 3. Mutter zu bestehender Schraube hinzufügen

1. „Mutter zu Schraube …" klicken (Button wird blau)
2. Irgendwo auf die Schraube in der 3D-Ansicht klicken
3. Vorschau-Mutter erscheint
4. Auflagefläche anklicken → Mutter wird gesetzt
5. Dialog wartet automatisch auf die nächste Schraube (Modus bleibt aktiv)
6. Nächste Schraube anklicken für weitere Mutter, oder anderen Schrauben-Button wählen um den Modus zu verlassen

### 4. Gewindestift einfügen

Wie Schraube, aber:
- „Mutter automatisch" ist deaktiviert (macht keinen Sinn)
- Kein Schraubenkopf → Schraube sitzt direkt am Lochrand
- Orientierung: LCS X-Achse zeigt ins Material (Einschraubrichtung)

---

## Orientierungslogik

### Problem
FreeCAD liefert beim Anklicken einer Kreiskante die Zylinderachse – aber nicht, von welcher Seite man anklickt (Kopfseite oder Materialseite). Diese Information muss aus der Bauteilgeometrie abgeleitet werden.

### Lösung: CoG-Methode
Der Schwerpunkt (Center of Gravity) der **Lochleibung** (Zylinderfläche des Lochs) liegt immer im Inneren des Bauteils. Der Vektor vom Lochrand-Mittelpunkt zum CoG zeigt also ins Material.

```
vec_to_cog = face.CenterOfGravity - edge.Curve.Center
```

Wenn dieser Vektor in die gleiche Richtung wie `axis_global` zeigt, muss `axis_global` umgedreht werden.

### Nachkorrektur nach recompute
Nach dem Einsetzen wird die tatsächliche LCS X-Achse in Weltkoordinaten berechnet und mit `vec_to_cog` verglichen. Falls falsch: 180°-Flip um eine **senkrechte** Achse (nicht die Längsachse – die würde die X-Achse nicht ändern).

---

## Technische Umsetzung

### Klassen und Funktionen

| Name | Typ | Zweck |
|------|-----|-------|
| `SchraubenDialog` | Klasse | Haupt-Dialog, erbt von `QDialog` |
| `SchraubenObserver` | Klasse | `SelectionObserver` für Klick-Events |
| `schraube_einfuegen()` | Funktion | Schraube berechnen, Link anlegen, Joint erstellen |
| `mutter_einfuegen()` | Funktion | Mutter positionieren und Joint erstellen |
| `fixed_joint_erstellen()` | Funktion | FreeCAD Fixed Joint per Python-API anlegen |
| `get_selected_circular_edge()` | Funktion | Kreiskante aus Selektion extrahieren |
| `lcs_placement_im_body()` | Funktion | LCS-Placement aus Body-Hierarchie lesen |
| `lcs_attachment_edge_name()` | Funktion | Edge-Name des LCS-Attachments ermitteln |
| `get_global_placement()` | Funktion | Welt-Placement eines Assembly-Links berechnen |

### Modi des Dialogs

```
'schraube'                   → wartet auf Lochrand-Klick
'warte_schraube_fuer_mutter' → wartet auf Klick auf bestehende Schraube
'warte_flaeche'              → Vorschau aktiv, wartet auf Flächen-Klick
```

### Joint-Struktur

```
Reference1 = Bauteil (Lochrand-Edge)       ← Bauteil bewegt sich nicht
Reference2 = Schraube/Mutter (LCS-Edge)   ← Schraube/Mutter folgt dem Bauteil
Offset2.Yaw = Zufallswinkel               ← dreht Schraube/Mutter um Längsachse
Offset2.Z   = Mutter-Abstand              ← verschiebt Mutter entlang Achse
```

Diese Reihenfolge (Bauteil=Ref1, Schraube=Ref2) ist entscheidend: nur so dreht `Offset2` die Schraube und nicht das Bauteil.

### Schrauben-Datei

`C:\Users\kraska\Documents\Eitech\CAD\Teile\Schrauben.FCStd`

| Body | Label | LCS |
|------|-------|-----|
| Body | Schraube 6 Schlitz | LCS_bolt = Edge46 |
| Body001 | Schraube 8 Schlitz | LCS_bolt = Edge56 |
| Body002 | Schraube 12 Schlitz | LCS_bolt = Edge80 |
| Body003 | Schraube 16 Schlitz | LCS_bolt = Edge102 |
| Body004 | Mutter | LCS_nut = Local_CS002/Edge21 |
| Body005 | Gewindestift | LCS_bolt = Edge22 |

**LCS-Konvention**: Ursprung am Kopfende (bzw. Einschraubende beim Gewindestift), X-Achse zeigt ins Material des Bauteils (Einschraubrichtung).

### LCS AttachmentOffset

| Schraubentyp | Achse | Winkel | Ergebnis |
|-------------|-------|--------|----------|
| Schlitzschrauben | (0, +1, 0) | 90° | X-Achse zeigt in -Z (ins Material) |
| Gewindestift | (0, -1, 0) | 90° | X-Achse zeigt in +Z (ins Material) |

Der unterschiedliche Offset ist geometrisch bedingt: die Kante am Gewindestift ist anders orientiert als bei Schlitzschrauben.

**Warum das ein Problem ist**: Das LCS wird nicht direkt als Joint-Referenz verwendet – stattdessen wird die nächstgelegene Kreiskante (`lcs_attachment_edge_name`) als Referenz genutzt. Dadurch geht die Orientierungsinformation des LCS verloren.

**Kompensation durch Nachkorrektur**: Nach dem Einfügen wird die tatsächliche LCS X-Achse in Weltkoordinaten berechnet (`actual_pl.Rotation.multiply(p1.Rotation).multVec(App.Vector(1,0,0))`) und mit `cog_vec_welt` verglichen. Falls die X-Achse nicht ins Material zeigt, wird die Schraube um 180° um eine senkrechte Achse geflippt.

**Getestet, nicht umsetzbar**: LCS direkt als Joint-Referenz (`joint.Reference2 = (link, ["LCS", "LCS"])`). FreeCAD akzeptiert den Namen syntaktisch, aber `Placement2` wird im Body-KS der Schrauben-Datei berechnet statt in Weltkoordinaten → falsche Schraubenposition. Edge-Referenz bleibt der richtige Weg.

### Vorschau-Mutter

Die Vorschau-Mutter ist ein normaler Assembly-Link ohne Joint:
```python
vorschau_pos = achse_ursprung - achse_richtung * (schrauben_laenge + MUTTER_VORSCHAU_ABSTAND)
```
Beim Bestätigen (Flächen-Klick) wird derselbe Link wiederverwendet und ein Joint angelegt. So entstehen keine doppelten Mutter-Links.

---

## Bekannte Einschränkungen

- **Undo**: Bei Undo-Operationen können unerwartete Schrauben eingefügt werden (fehlende `openTransaction`/`commitTransaction`)
- **Performance**: Bei großen Assemblies (~100 Joints) dauert jedes Einfügen 4-9 Sekunden durch den asynchronen FreeCAD-Solver
- **Schraubendatei-Pfad**: Hardcodiert, nicht relativ zum Projektordner
- **Nur eine Mutter pro Schraube** im automatischen Modus; zweite Mutter (Kontermutter) über „Mutter zu Schraube"

---

## Abhängigkeiten

- FreeCAD 1.1 mit Assembly Workbench
- PySide6 (in FreeCAD 1.1 eingebaut)
- `JointObject` (FreeCAD Assembly-Modul)
- Schrauben-Datei muss in FreeCAD geöffnet sein
