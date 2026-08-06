## export_visible.py

Exportiert nur die im Baum sichtbaren Teile als GLB (statt wie beim
manuellen Export alles, inkl. unsichtbarer Hilfsteile). Berücksichtigt
außerdem Instanzfarben, die der GLB-Exporter sonst grundsätzlich
ignoriert.

### Architektur

Arbeitet ausschließlich LESEND am Original-Dokument - keine Kopie,
kein Löschen, keine Änderung an Sichtbarkeit/Rigid-Flags. Baut im
Scratch-Dokument die Assembly-GRUPPIERUNG als verschachtelte
`App::Part`-Container nach (rein organisatorisch, kein eigenes
Placement - die Blätter tragen bereits ihre volle, vorher berechnete
Weltposition), mit sichtbaren Blatt-Objekten als `App::Link` darin
(referenziert die Original-Geometrie, kein Kopieren der Shape); für
Teile mit Instanzfarbe zeigt der Link stattdessen auf eine eigens
angelegte, unabhängige Farbkopie. Alles wird unter einer einzigen
Top-Level-Gruppe zusammengefasst, benannt nach der gewählten
Export-Datei (nicht nach dem technischen Scratch-Dokumentnamen).

Frühere Ansätze (Datei-Kopie + Löschen unsichtbarer Teile + Rigid-
Cache-Rebuild durch Umschalten) haben sich als deutlich fehleranfälliger
erwiesen (siehe Erkenntnisse unten) und wurden zugunsten dieser
schlankeren, rein lesenden Variante verworfen.

### Auswahl-Logik

- Nur echte Assembly-Container (`Assembly::AssemblyObject`,
  `Assembly::AssemblyLink` - auch bei `Rigid=True`) werden immer
  durchlaufen, weil ihre Group-Kinder echte eigene Shape-/Placement-
  /Visibility-Daten haben.
- **Zweites, unabhängiges Container-Muster**: manche Sub-Baugruppen
  hängen als einfacher `App::Link` (kein `Rigid`) mit eigener,
  gültiger kombinierter Shape UND eigener Group im Baum. Ohne
  Sonderbehandlung würden solche Links als EIN unzerlegtes Blatt
  behandelt (sie haben ja selbst eine gültige Shape) - Kinder-Farben
  und -Sichtbarkeit gingen verloren. Erkennung über
  `is_part_wrapper_link()`: das `LinkedObject` ist selbst ein
  `App::Part`. Wichtig, gezielt zu prüfen statt pauschal "jeder
  `App::Link` mit Group" - das war zu grobmaschig und hat auch
  Links mit technischem/unrelated Group-Inhalt erwischt (massive
  Über-Zerlegung, kaputte Teilshapes, viele "Failed to get subshape"-
  Fehler beim Export).
- Manche Sub-Baugruppen-Links haben zudem gar keine eigene lokale
  Group (nur die verlinkte Quelle hat eine) - `get_effective_group()`
  fällt in dem Fall auf `LinkedObject.Group` zurück.
- Alle anderen Objekte (Bauteile mit interner Feature-Historie wie
  Fillets, Skript-Objekte) nutzen ihre eigene, fertige Shape direkt,
  falls vorhanden, statt in eine interne Feature-Gruppe (Sketch/Pad/
  Fold) abzusteigen - sonst würde z.B. ein gefastes Bauteil im
  Zwischenzustand vor dem letzten Feature landen.
- Sichtbarkeit wirkt NICHT hierarchisch: nur das eigene
  `Visibility`-Flag jedes Blatts zählt.
- Root-Erkennung über tatsächliche Group-Mitgliedschaft, nicht
  `InList` - `InList` fängt auch nicht-strukturelle Objektreferenzen
  ein (z.B. referenzieren SchlauchPfad-Skripte die Top-Level-Assembly
  als reinen Positionsbezug, ohne echte Tree-Elternschaft).

### Farbkorrektur

Wichtige Erkenntnis: **der GLB-Exporter (`ImportGui.export`)
berücksichtigt `OverrideMaterial`/`ShapeMaterial` grundsätzlich
NICHT** - auch nicht bei Direktexport der Originaldatei. Nur
`ShapeAppearance` wird tatsächlich exportiert. Gleichzeitig geht beim
starren XLink-Import (`Rigid=True`) die per `paint.py` gesetzte
Instanzfarbe der Quelldatei nicht automatisch in die lokale Kopie
über.

Um die korrekte Farbe zu finden, wird pro Rigid-Container das lokale
Kind mit dem **geometrisch nächstgelegenen** Kind in der Group des
verlinkten Quellobjekts (`LinkedObject.Group`) gepaart (`Placement.Base`-
Abstand, 0.01mm Toleranz). **Nicht** per Listenposition matchen -
nachgewiesen unzuverlässig: die lokale Group ist bei manchen Rigid-
Baugruppen eine unvollständige Kopie der Quelle (z.B. weniger
Elastikstellring-Instanzen lokal als in der Quelle vorhanden), wodurch
sich ab der ersten fehlenden Position jede weitere Listenposition
verschiebt. Es gibt in dieser FreeCAD-Version keine `Uid`-Eigenschaft
zum eindeutigen Identifizieren, und Labels sind nicht eindeutig
(mehrere "Nippel", "Elastikstellring schwarz" etc.) - Placement ist
der einzige verlässliche Schlüssel.

Für Objekte mit gefundener Instanzfarbe wird eine unabhängige Kopie
angelegt: ein frisches `Part::Feature` mit nur der reinen, kopierten
Shape (`base.Shape.copy()`), **nicht** über `copyObject()` - das hat
in einem Fall eine geteilte Material-Referenz vom Original mitgebracht
und dabei unbeabsichtigt Teile in einer bereits geöffneten Quelldatei
umgefärbt (nur im Speicher, nicht auf der Platte - Reload hat es
zurückgesetzt). Mehrere Instanzen mit identischer (Basisteil, Farbe)-
Kombination teilen sich dieselbe neue Kopie.

### Diagnose-Werkzeug

`diagnose_colors.py` (separates Skript, gleiche Matching-Logik wie
`export_visible.py`) druckt jede gefundene Farbzuordnung mit Container,
Abstand, lokalem und Quell-Label - nützlich, um Fehlzuordnungen
sichtbar zu machen, ohne jedes Mal zu exportieren.

### Weitere FreeCAD-Erkenntnisse aus der Entwicklung

- `App::Link` zwischen zwei Dokumenten setzt voraus, dass **beide**
  Dokumente einen Speicherort auf der Platte haben (`RuntimeError:
  Owner document not saved`, falls nicht) - das Scratch-Dokument muss
  daher sofort nach dem Anlegen per `saveAs()` gespeichert werden.
- Kopiert man die `.FCStd`-Datei für einen anderen Ansatz, muss die
  Kopie im **selben Ordner** wie das Original liegen - sonst laufen
  relative XLink-Pfade zu Geschwisterdateien (z.B. `Unterwagen.FCStd`)
  ins Leere und alle Links werden leer.
  Rigid-`AssemblyLink`-Objekte cachen ihre Shape offenbar aus der
  XLink-Quelldatei, nicht aus der lokalen Group - Umschalten von
  `Rigid` (aus/wieder ein) verwirft dadurch lokale Änderungen an der
  Group, statt sie zu übernehmen.
- `Std_Delete` (FreeCADs GUI-Löschbefehl) zeigt bei Abhängigkeiten
  einen interaktiven Bestätigungsdialog, der ein Skript mitten in der
  Ausführung anhält - in einem Fall mit spürbaren Nebenwirkungen auf
  eine gleichzeitig geöffnete, geteilte XLink-Quellinstanz. Für
  Skript-Automatisierung besser die rohe, nicht-interaktive
  `removeObject()`-API verwenden (ggf. rekursiv über `Group`, da sie
  Feature-Historie nicht automatisch mitlöscht).
