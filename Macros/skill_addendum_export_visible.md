## Export.py (vormals export_visible.py)

Exportiert nur die im Baum sichtbaren Teile als GLB (statt wie beim
manuellen Export alles, inkl. unsichtbarer Hilfsteile). Berücksichtigt
außerdem Instanzfarben, die der GLB-Exporter sonst grundsätzlich
ignoriert, und beschriftet Teile mit erkannter Instanzfarbe zusätzlich
mit dem passenden Eitech-Farbnamen (Debug-Hilfe, siehe unten).

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
- **Sichtbarkeit wirkt jetzt HIERARCHISCH** (korrigiert, vorher stand
  hier fälschlich "nicht hierarchisch, nur das Blatt zählt"): ein
  ausgeblendeter Knoten - Container ODER Blatt - blendet den
  kompletten Zweig aus, unabhängig vom `Visibility`-Flag seiner
  Kinder, genau wie FreeCADs eigene 3D-Ansicht. Bug gefunden an
  `Gleiter.FCStd`: eine ausgeblendete Rigid-"Vorlage" (die
  `Assembly::AssemblyObject`, aus der ein `Assembly::AssemblyLink`
  per "Make Rigid" erzeugt wurde) hatte selbst `Visibility=False`,
  aber ihre Kinder waren einzeln noch `Visibility=True` - die alte
  Blatt-only-Prüfung hat diese Kinder deshalb trotzdem exportiert,
  als unbemalte Geometrie-Duplikate exakt an derselben Weltposition
  wie die bemalten Rigid-Kopien (im Viewer als Farbfehler sichtbar,
  weil das falsche Duplikat das bemalte Original verdeckt hat). Bisher
  unauffällig, weil offenbar kein früher getestetes Modell diese
  Kombination (ausgeblendeter Container + einzeln sichtbare Kinder)
  hatte. Nach dem Fix an mehreren Modellen ohne Regression getestet.
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

**Vollständiges Material statt nur Diffuse** (v13-Fix): die Farbkopie
übernimmt jetzt ALLE Kanäle aus `ShapeMaterial` (Ambient, Diffuse,
Specular, Emissive, Shininess, Transparency) über `material_tuple()`,
nicht mehr nur `DiffuseColor`. `material_tuple()` liest jedes Feld
einzeln mit eigenem Try/Except und protokolliert per Konsolen-Warnung,
falls eines nicht lesbar ist (Standardwert als Fallback), statt bei
einem kaputten Feld die komplette Instanzfarbe stillschweigend zu
verwerfen. Wichtig zu wissen: `paint.py` dokumentiert, dass FreeCAD bei
`App::Link`-Instanzen mit `OverrideMaterial=True` LIVE nur Diffuse pro
Instanz rendert (FreeCAD/FreeCAD#19135, Ambient/Specular/Shininess
kommen dort immer aus der Quelldatei) - das betrifft aber nur den
Link-Override-Mechanismus auf geteilter Geometrie. Die hier erzeugte
Farbkopie ist ein eigenständiges `Part::Feature` ohne diesen
Mechanismus, das komplette gespeicherte Material wird dort tatsächlich
1:1 wirksam.

**Debug-Label** (neu in v13): Teile mit erkannter Instanzfarbe bekommen
den nächstgelegenen Namen aus der Eitech-Farbpalette (1:1 aus
`paint.py`s `ROW1`/`ROW2` übernommen, `nearest_color_name()`) an ihr
Export-Label angehängt, z.B. "Zylindersegment" -> "Zylindersegment
Rot". So sieht man im Viewer sofort, welche Farbe ein Teil laut
Datenmodell haben sollte, auch wenn Export/Viewer sie (noch) nicht
korrekt zeigen - ohne jedes Mal in FreeCAD nachschauen zu müssen. Teile
ganz ohne erkannte Farbe behalten ihr normales Label.

### Diagnose-Werkzeug

`diagnose_colors.py` (separates Skript, sollte dieselbe Matching-Logik
wie `Export.py` spiegeln) druckt jede gefundene Farbzuordnung mit
Container, Abstand, lokalem und Quell-Label - nützlich, um
Fehlzuordnungen sichtbar zu machen, ohne jedes Mal zu exportieren.
**Bekannter, noch offener Stand**: `diagnose_colors.py` ist zuletzt vor
dem `is_part_wrapper_link()`-Fix (v12) stehengeblieben und benutzt noch
die breitere, überholte Bedingung "jeder `App::Link` mit Group" statt
`is_part_wrapper_link()` - und hat auch die v13-Fixes (vollständiges
Material, hierarchische Sichtbarkeit) noch nicht übernommen. Vor der
nächsten Farbdiagnose per Skript erst wieder in Parität zu `Export.py`
bringen.

Geplante Erweiterung (noch nicht begonnen): dieselbe
Instanzfarb-Erkennung soll auch in `bom.py` (Stückliste) einfließen.

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
- Ein `App::Link` kann auf einen ANDEREN `App::Link` im selben Dokument
  zeigen (Kette, nicht nur `App::Link` -> "echtes" Objekt oder
  cross-file XLink) - z.B. `Zylindersegment032` -> `Zylindersegment020`
  -> `Zylindersegment001` -> `Body032` in `../Teile/Plastik.FCStd`
  (dreistufig, an `Gleiter.FCStd` gefunden). `obj.Shape` löst diese
  Kette transparent auf, `ViewObject.OverrideMaterial`/`ShapeMaterial`
  müssen aber jeweils direkt am BETROFFENEN Link-Objekt selbst gesetzt
  sein, nicht irgendwo in der Kette.
