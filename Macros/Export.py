# -*- coding: utf-8 -*-
"""
Export.py (v13, vormals export_visible.py / export_visible_v13.py)

Exportiert alle sichtbaren Objekte als GLB. Arbeitet NICHT auf einer
Kopie der .FCStd-Datei und verändert das Original-Dokument an KEINER
Stelle - es wird nur gelesen. Baut im Scratch-Dokument die Assembly-
GRUPPIERUNG nach (als App::Part, rein organisatorisch), mit sichtbaren
Blatt-Objekten als App::Link mit korrekt berechneter Weltplatzierung
darin (referenziert die Original-Geometrie, dupliziert sie nicht); für
Teile mit Instanzfarbe zeigt der Link stattdessen auf eine eigens
angelegte, unabhängige Farbkopie.

v13-Änderungen gegenüber v12 (export_visible.py), beide an Gleiter.FCStd
(Zylindersegment032-035) gefunden und dort verifiziert behoben, per
Nachtest auch an weiteren Modellen ohne Regression bestätigt:
- BUGFIX Farbkopie: collect_source_colors() hat bisher nur DiffuseColor
  aus ShapeMaterial in color_map übernommen - Ambient/Specular/
  Emissive/Shininess gingen verloren, make_colored_copy() hat sie durch
  FreeCAD-Standardwerte ersetzt (sichtbar als leicht abweichende Farbe
  im Export/Viewer). Jetzt wird das komplette Material (alle Kanäle)
  übernommen, über material_tuple(), das jedes Feld einzeln mit
  eigenem Try/Except liest und eine Konsolen-Warnung ausgibt, falls
  eines fehlschlägt (statt die ganze Instanzfarbe stillschweigend zu
  verwerfen). Wichtig: das betrifft NUR die für den Export neu
  angelegte, unabhängige Part::Feature-Kopie - die von paint.py
  dokumentierte FreeCAD-Einschränkung (App::Link-Instanzen rendern bei
  OverrideMaterial=True live nur Diffuse pro Instanz, siehe FreeCAD/
  FreeCAD#19135) gilt dort nicht, weil es sich um ein eigenständiges
  Objekt ohne Link-Override-Mechanik handelt - das gespeicherte
  Material kann also 1:1 übernommen werden.
- BUGFIX Sichtbarkeit (der eigentliche Fund hinter dem obigen Symptom):
  Sichtbarkeit wird jetzt an JEDEM Knoten geprüft, nicht mehr nur an
  Blättern - siehe Abschnitt "Auswahl-Logik" unten für die Begründung.
  Ohne diesen Fix wurden ausgeblendete Rigid-"Vorlagen" trotzdem voll
  durchlaufen und lieferten unbemalte Geometrie-Duplikate exakt über
  den bemalten Rigid-Kopien - das eigentliche Problem, die abweichende
  Farbe oben war nur ein Nebenbefund an denselben Objekten.
- NEU: Label-Anreicherung zur Fehlersuche. Exportierte Teile mit
  erkannter Instanzfarbe bekommen den nächstgelegenen Namen aus der
  Eitech-Farbpalette (aus paint.py übernommen) an ihr Label angehängt,
  z.B. "Zylindersegment" -> "Zylindersegment Rot". So sieht man im
  Viewer sofort, welche Farbe ein Teil laut Datenmodell haben sollte,
  auch wenn der Export/Viewer sie (noch) nicht korrekt anzeigt - ohne
  jedes Mal wieder in FreeCAD nachschauen zu müssen.

Vorgeschichte (deutlich aufwändigerer, fehleranfälliger Ansatz):
Frühere Versionen haben mit einer echten Kopie der .FCStd-Datei
gearbeitet, dort unsichtbare Teile per removeObject()/Std_Delete
gelöscht und bei Rigid-Baugruppen den eingefrorenen Shape-Cache
(_Part_ShapeCache) durch Umschalten von Rigid neu aufgebaut. Das
brachte mehrere handfeste Probleme: Std_Delete zeigt bei Abhängig-
keiten einen interaktiven Dialog, der das Skript anhält und (vermut-
lich dadurch) sogar auf eine bereits offene, geteilte XLink-Quell-
instanz kaskadieren konnte; der Rigid-Cache cached offenbar aus der
XLink-Quelldatei statt aus der lokalen Group, wodurch erneutes Ein-
schalten von Rigid alle lokalen Änderungen wieder verwarf; Joints
mussten in einer fragilen Reihenfolge relativ zu alldem gelöscht
werden, um nicht kaskadierend andere Shapes zu zerstören. All das
entfällt komplett, wenn man gar nichts am Original ändert, sondern
nur einzeln die sichtbaren Blätter mit korrekter Weltplatzierung in
ein eigenes Scratch-Dokument exportiert.

Auswahl-Logik (bewährt, unverändert):
- Nur echte Assembly-Container (Assembly::AssemblyObject,
  Assembly::AssemblyLink - auch bei Rigid=True) werden immer
  durchlaufen, weil ihre Group-Kinder echte eigene Shape-/Placement-
  /Visibility-Daten haben.
- Alle anderen Objekte (Bauteile mit interner Feature-Historie wie
  Fillets, Skript-Objekte) nutzen ihre eigene, fertige Shape direkt,
  falls vorhanden, statt in eine interne Feature-Gruppe abzusteigen.
- Sichtbarkeit wirkt jetzt (ab v13) hierarchisch, wie in FreeCADs
  eigener 3D-Ansicht: ein ausgeblendeter Knoten - Container UND Blatt -
  blendet den kompletten Zweig aus, unabhängig vom Visibility-Flag
  seiner Kinder. Vorher (v12) wurde nur das Blatt-Flag geprüft ("Sicht-
  barkeit wirkt NICHT hierarchisch") - das war für die bisher getesteten
  Modelle unauffällig, aber falsch: an Gleiter.FCStd hat es dazu geführt,
  dass die ausgeblendete Rigid-"Vorlage" Assembly003 trotzdem voll
  durchlaufen wurde und ihre einzeln noch sichtbar-geflaggten, unbemalten
  Kinder als Duplikate exakt über den bemalten Rigid-Kopien exportiert
  hat.
- Root-Erkennung über tatsächliche Group-Mitgliedschaft, nicht
  InList (InList fängt auch nicht-strukturelle Objektreferenzen ein,
  z.B. Schlauch-Skripte, die die Assembly als Positionsbezug nutzen).

Farbkorrektur:
Der GLB-Exporter berücksichtigt OverrideMaterial/ShapeMaterial
GRUNDSÄTZLICH NICHT - nur ShapeAppearance wird exportiert. Instanz-
farben (per paint.py gesetzt) werden entweder direkt am Blatt-Objekt
gefunden (OverrideMaterial dort gesetzt), oder - beim Rigid-XLink-
Import - über ein Matching der Weltposition (Placement.Base)
zwischen lokalem Kind und Quell-Kind: jedes lokale Kind wird mit dem
geometrisch nächstgelegenen Quell-Kind gepaart (Toleranz 0.01mm),
NICHT per Listenposition. Per Diagnose bestätigt: die lokale Group
ist bei Rigid-Import teils eine unvollständige Kopie der Quelle -
Positions-Matching war deshalb grundsätzlich unzuverlässig.
Die Farbkopie wird als frisches Part::Feature mit nur der reinen Shape
angelegt (NICHT über copyObject() - das brachte offenbar eine geteilte
Material-Referenz vom Original mit und hat in einem Fall sogar Teile
in der noch offenen Quelldatei umgefärbt).

Manche Sub-Baugruppen sind als einfacher App::Link (kein Rigid-
AssemblyLink) OHNE eigene lokale Group eingebunden - ihre Kinder
existieren nur im verlinkten Quelldokument. Für diesen Fall fällt
get_effective_group() auf LinkedObject.Group zurück UND erzwingt die
Zerlegung (force_container), da so ein Link oft trotzdem eine eigene,
gültige Shape hat und sonst fälschlich als unzerlegtes Blatt behandelt
würde (Kinder-Farben/-Sichtbarkeit gingen dann verloren).

Reicht aber NICHT: auch App::Link-Objekte mit einer vollständigen,
nicht-leeren EIGENEN Group (Fallback wird also gar nicht gebraucht)
wurden trotzdem nicht zerlegt, weil sie weder Assembly::AssemblyLink/
-Object sind noch eine fehlende eigene Shape haben. Erster Versuch
(PAUSCHAL jeder App::Link mit Group wird zerlegt) war zu grobmaschig -
hat auch technische/andere Group-Vorkommen erwischt und zu massiver
Über-Zerlegung mit kaputten Teilshapes geführt. Stattdessen gezielt:
is_part_wrapper_link() prüft, ob das LinkedObject selbst ein
App::Part ist (das konkrete Muster für so eingebundene Sub-
Baugruppen) - nur dann wird zwangsweise zerlegt.

Aufruf: Makro im FreeCAD-Makro-Menü ausführen, während das zu
exportierende Dokument aktiv ist.
"""

import os
import tempfile
import FreeCAD as App
import ImportGui
from PySide6 import QtWidgets


ASSEMBLY_CONTAINER_TYPES = {"Assembly::AssemblyObject", "Assembly::AssemblyLink"}

# Eitech-Farbpalette (Diffuse-Werte 1:1 aus paint.py, ROW1+ROW2 übernommen) -
# dient NUR zur Beschriftung exportierter Teile mit erkannter Instanzfarbe,
# damit man im Viewer sofort sieht, welche Farbe ein Teil laut Datenmodell
# haben sollte, auch wenn Export/Viewer sie (noch) nicht korrekt zeigen.
# Keine exakte Farbverwaltung, nur eine Lesehilfe zur Fehlersuche.
NAMED_COLORS = [
    ("Schwarz", (0.228000, 0.228000, 0.228000)),
    ("Rot", (1.000000, 0.000000, 0.000000)),
    ("Orange", (1.000000, 0.505882, 0.007843)),
    ("Gelb", (1.000000, 1.000000, 0.000000)),
    ("Beige (C13)", (0.992157, 0.729412, 0.003922)),
    ("Blau", (0.003922, 0.329412, 0.635294)),
    ("Grau", (0.678431, 0.709804, 0.741176)),
    ("Weiss", (1.000000, 0.984314, 0.941176)),
    ("Metall (hell)", (0.881961, 0.922745, 0.963529)),
    ("Metall (mittel)", (0.678431, 0.709804, 0.741176)),
    ("Metall (dunkel)", (0.440980, 0.461373, 0.481765)),
]


def nearest_color_name(rgb):
    """Nächstgelegener Name aus NAMED_COLORS (per quadrierter Distanz auf
    den ersten drei Diffuse-Kanälen) - keine exakte Farbverwaltung, nur
    eine Lesehilfe zur Beschriftung."""
    best_name, best_dist = None, None
    for name, ref in NAMED_COLORS:
        d = sum((a - b) ** 2 for a, b in zip(rgb[:3], ref))
        if best_dist is None or d < best_dist:
            best_dist, best_name = d, name
    return best_name


def is_part_wrapper_link(obj):
    """True, wenn obj ein App::Link ist, dessen LinkedObject selbst
    ein App::Part ist (das Muster für nicht-Rigid eingebundene Sub-
    Baugruppen wie Oberwagen_Rahmen). Bewusst NICHT pauschal jeder
    App::Link mit Group - das hat sich als zu grobmaschig erwiesen
    und andere, technische Group-Vorkommen mit erwischt (massive
    Über-Zerlegung, kaputte Teilshapes)."""
    if obj.TypeId != "App::Link":
        return False
    linked = getattr(obj, "LinkedObject", None)
    return linked is not None and linked.TypeId == "App::Part"


def get_effective_group(obj):
    """Liefert (Kinder-Liste, force_container). Normalerweise die
    eigene Group, force_container=False. Manche Sub-Baugruppen sind
    aber als einfacher App::Link OHNE eigene lokale Group eingebunden
    (kein Rigid-AssemblyLink) - deren Kinder existieren dann NUR im
    verlinkten Quelldokument (LinkedObject.Group), ohne lokales
    Gegenstück. In dem Fall wird direkt in die Quell-Group
    abgestiegen (Kinder leben im anderen Dokument, aber
    App::Link.Placement ist bereits die volle Transformation für
    alles darunter, die Formel bleibt dieselbe) - UND force_container
    wird True, denn so ein Link hat oft trotzdem eine eigene, gültige
    (kombinierte) Shape und würde sonst fälschlich als unzerlegtes
    Blatt behandelt, obwohl wir hier explizit zerlegen wollen."""
    group = getattr(obj, "Group", None)
    if group:
        return group, False
    if obj.TypeId == "App::Link":
        linked = getattr(obj, "LinkedObject", None)
        if linked is not None:
            linked_group = getattr(linked, "Group", None)
            if linked_group:
                return linked_group, True
    return None, False


def get_top_level_objects(doc):
    """Objekte, die in KEINER Group eines anderen Objekts als Kind
    auftauchen."""
    grouped_names = set()
    for obj in doc.Objects:
        group = getattr(obj, "Group", None)
        if group:
            for child in group:
                grouped_names.add(child.Name)
    return [obj for obj in doc.Objects if obj.Name not in grouped_names]


def material_tuple(vo):
    """Liest ALLE Kanäle aus ShapeMaterial (nicht nur DiffuseColor) als
    hashbares Tupel - für color_map, das später 1:1 auf die Farbkopie
    zurückgeschrieben wird (siehe make_colored_copy).

    Liest jedes Feld EINZELN mit eigenem Try/Except statt in einem
    Rutsch, und protokolliert per Konsolen-Warnung, welches Feld genau
    fehlschlägt - statt bei EINEM kaputten Feld die komplette
    Instanzfarbe (und damit auch das Debug-Label) stillschweigend zu
    verwerfen. Bei Fehlschlag wird ein neutraler Standardwert
    verwendet, damit wenigstens Diffuse (das eigentlich Wichtige)
    durchkommt, auch wenn z.B. Shininess nicht lesbar ist."""
    obj_name = getattr(getattr(vo, "Object", None), "Name", "?")

    try:
        m = vo.ShapeMaterial
    except Exception as e:
        App.Console.PrintWarning(
            "export_visible: ShapeMaterial nicht lesbar für %s (%s) - "
            "Instanzfarbe wird übersprungen.\n" % (obj_name, e)
        )
        raise

    def field(name, default):
        try:
            return getattr(m, name)
        except Exception as e:
            App.Console.PrintWarning(
                "export_visible: ShapeMaterial.%s nicht lesbar für %s (%s) - "
                "verwende Standardwert %r.\n" % (name, obj_name, e, default)
            )
            return default

    ambient = field("AmbientColor", (0.3, 0.3, 0.3, 1.0))
    diffuse = field("DiffuseColor", (0.8, 0.8, 0.8, 1.0))
    specular = field("SpecularColor", (0.6, 0.6, 0.6, 1.0))
    emissive = field("EmissiveColor", (0.0, 0.0, 0.0, 1.0))
    shininess = field("Shininess", 0.25)
    transparency = field("Transparency", 0.0)

    return (
        tuple(ambient),
        tuple(diffuse),
        tuple(specular),
        tuple(emissive),
        float(shininess),
        float(transparency),
    )


def collect_source_colors(obj, color_map, path):
    """Sammelt Instanzfarben. color_map wird mit (doc.Name, obj.Name)
    -> vollständigem Material-Tupel (siehe material_tuple()) befüllt,
    für alle Blatt-Objekte, die eine Instanzfarbe haben sollten."""
    key = (obj.Document.Name, obj.Name)
    if key in path:
        return
    path = path | {key}

    # Sichtbarkeit JETZT auch an Containern prüfen, nicht nur an Blättern
    # (siehe Modul-Doku v13-Nachtrag): FreeCAD blendet in der eigenen
    # 3D-Ansicht Kinder eines ausgeblendeten Containers hierarchisch mit
    # aus, unabhängig von deren eigenem Visibility-Flag. Bug gefunden an
    # Gleiter.FCStd: Assembly003 (die Rigid-"Vorlage" hinter Gkeiter02,
    # selbst Visibility=False) hat Kinder mit Visibility=True, die dadurch
    # bisher trotzdem als zusätzliche, unbemalte Duplikate exakt an
    # derselben Weltposition wie die bemalten Rigid-Kopien exportiert
    # wurden. Betrifft NUR die unabhängige Top-Level-Traversierung hier -
    # das Farb-Matching gegen linked.Group weiter unten liest Assembly003
    # als reine Datenquelle, nicht über einen rekursiven Aufruf, und ist
    # von dieser Prüfung nicht betroffen.
    if not bool(getattr(obj, "Visibility", True)):
        return

    group, force_container = get_effective_group(obj)
    own_shape = getattr(obj, "Shape", None)
    has_own_shape = own_shape is not None and not own_shape.isNull()
    is_assembly_container = obj.TypeId in ASSEMBLY_CONTAINER_TYPES

    if group and (is_assembly_container or not has_own_shape or force_container or is_part_wrapper_link(obj)):
        linked = getattr(obj, "LinkedObject", None)
        source_group = getattr(linked, "Group", None) if linked is not None else None
        if source_group:
            # NICHT nach Listenposition matchen (nachweislich
            # unzuverlässig: die lokale Group ist teils eine
            # unvollständige Kopie der Quelle, wodurch sich die
            # Reihenfolge ab einer bestimmten Stelle verschiebt -
            # z.B. lokal 4 statt 8 Elastikstellringe, ab dort liegt
            # jede Position daneben). Stattdessen jedes lokale Kind
            # mit dem geometrisch nächstgelegenen Quell-Kind matchen
            # (Placement.Base) - jedes physische Teil hat eine
            # eindeutige 3D-Position, die der Rigid-Import exakt
            # erhalten soll.
            used = set()
            for child in group:
                try:
                    child_pos = child.Placement.Base
                except Exception:
                    continue
                best_i, best_dist = None, None
                for i, src in enumerate(source_group):
                    if i in used:
                        continue
                    try:
                        d = (child_pos - src.Placement.Base).Length
                    except Exception:
                        continue
                    if best_dist is None or d < best_dist:
                        best_dist, best_i = d, i
                if best_i is None or best_dist > 0.01:
                    continue  # kein hinreichend naher Treffer (0.01mm Toleranz)
                used.add(best_i)
                src_vo = getattr(source_group[best_i], "ViewObject", None)
                if src_vo is not None and getattr(src_vo, "OverrideMaterial", False):
                    try:
                        color_map[(child.Document.Name, child.Name)] = material_tuple(src_vo)
                    except Exception:
                        pass
        for child in group:
            collect_source_colors(child, color_map, path)
        return

    own_vo = getattr(obj, "ViewObject", None)
    if own_vo is not None and getattr(own_vo, "OverrideMaterial", False):
        try:
            color_map[(obj.Document.Name, obj.Name)] = material_tuple(own_vo)
        except Exception:
            pass


def build_tree(obj, ext_placement, path):
    """Rekursiver Baum-Walk. Baut - anders als eine flache Blattliste -
    eine verschachtelte Struktur nach, damit die Assembly-Gruppierung
    im Export erhalten bleibt:
      ('container', obj, [Kind-Knoten...])  - für Container mit >=1
                                               sichtbarem Inhalt
      ('leaf', obj, ext_placement)          - für ein sichtbares Blatt,
                                               ext_placement ist seine
                                               volle Weltplatzierung
                                               (wie bisher berechnet -
                                               die Container-Knoten
                                               bekommen selbst KEIN
                                               Placement, sie sind rein
                                               organisatorisch, die
                                               Blätter tragen bereits
                                               ihre volle Weltposition)
    Gibt None zurück, wenn dieser Zweig nichts Sichtbares enthält."""
    key = (obj.Document.Name, obj.Name)
    if key in path:
        return None
    path = path | {key}

    # Sichtbarkeit jetzt an JEDEM Knoten geprüft (Container wie Blatt),
    # nicht mehr nur am Blatt wie in v12 - siehe ausführliche Begründung
    # in collect_source_colors(). Ersetzt den alten, blattspezifischen
    # Visibility-Check weiter unten (der war zu spät: ein ausgeblendeter
    # CONTAINER wurde vorher trotzdem voll durchlaufen).
    if not bool(getattr(obj, "Visibility", True)):
        return None

    group, force_container = get_effective_group(obj)
    own_shape = getattr(obj, "Shape", None)
    has_own_shape = own_shape is not None and not own_shape.isNull()
    is_assembly_container = obj.TypeId in ASSEMBLY_CONTAINER_TYPES

    if group and (is_assembly_container or not has_own_shape or force_container or is_part_wrapper_link(obj)):
        own_pl = getattr(obj, "Placement", App.Placement())
        new_ext = ext_placement.multiply(own_pl)
        children = []
        for child in group:
            node = build_tree(child, new_ext, path)
            if node is not None:
                children.append(node)
        if not children:
            return None
        return ("container", obj, children)

    if not has_own_shape:
        return None
    return ("leaf", obj, ext_placement)


def make_colored_copy(scratch_doc, base, color, cache):
    """Unabhängige Farbkopie von base anlegen (frisches Part::Feature
    mit nur der reinen Shape - NICHT copyObject(), siehe Modul-Doku).
    Dedupliziert über cache, damit mehrere Instanzen mit derselben
    (Basisteil, Farbe)-Kombination sich eine Kopie teilen.

    color ist das vollständige Material-Tupel aus material_tuple()
    (Ambient, Diffuse, Specular, Emissive, Shininess, Transparency) -
    NICHT nur DiffuseColor wie in v12. Das ist hier unproblematisch:
    die von paint.py dokumentierte FreeCAD-Einschränkung (App::Link-
    Instanzen rendern bei OverrideMaterial=True live nur Diffuse pro
    Instanz, FreeCAD/FreeCAD#19135) betrifft nur Link-Override auf
    geteilter Geometrie - diese Kopie hier ist ein eigenständiges
    Part::Feature ohne Override-Mechanik, das komplette Material wird
    also tatsächlich 1:1 wirksam."""
    cache_key = (base.Document.Name, base.Name, color)
    if cache_key in cache:
        return cache[cache_key]

    colored = scratch_doc.addObject(
        "Part::Feature", "ColorFix%03d" % len(cache)
    )
    colored.Shape = base.Shape.copy()
    colored.Label = (base.Label or base.Name) + "_farbe"
    try:
        ambient, diffuse, specular, emissive, shininess, transparency = color
        mat = App.Material()
        mat.AmbientColor = ambient
        mat.DiffuseColor = diffuse
        mat.SpecularColor = specular
        mat.EmissiveColor = emissive
        mat.Shininess = shininess
        mat.Transparency = transparency
        colored.ViewObject.ShapeAppearance = (mat,)
    except Exception as e:
        App.Console.PrintWarning(
            "export_visible: Farbkopie fehlgeschlagen für %s: %s\n"
            % (base.Name, e)
        )
    cache[cache_key] = colored
    return colored


def make_export_link(scratch_doc, obj, ext_placement, index, color_map, colored_cache):
    """Leichtgewichtigen App::Link im Scratch-Dokument anlegen, der
    auf die Original-Geometrie verweist (kein Kopieren der Shape) -
    oder, falls eine Instanzfarbe vorliegt, auf eine eigens angelegte
    Farbkopie. Hat obj eine erkannte Instanzfarbe, wird zusätzlich der
    nächstgelegene Eitech-Farbname an das Label angehängt (z.B.
    "Zylindersegment" -> "Zylindersegment Rot") - reine Lesehilfe im
    Viewer, damit man sieht, welche Farbe ein Teil laut Datenmodell
    haben sollte."""
    key = (obj.Document.Name, obj.Name)
    color = color_map.get(key)

    if color is not None:
        target = make_colored_copy(scratch_doc, obj, color, colored_cache)
    else:
        target = obj

    link = scratch_doc.addObject("App::Link", "Export%03d" % index)
    link.LinkedObject = target
    link.Placement = ext_placement.multiply(obj.Placement)

    label = obj.Label
    if color is not None:
        diffuse = color[1]
        label = "%s %s" % (label, nearest_color_name(diffuse))
    link.Label = label

    if color is None:
        try:
            src_vo = obj.ViewObject
            if src_vo is not None:
                link.ViewObject.ShapeColor = src_vo.ShapeColor
                link.ViewObject.Transparency = src_vo.Transparency
        except Exception:
            pass

    return link


def materialize_tree(scratch_doc, node, color_map, colored_cache, counter):
    """Baut einen build_tree()-Knoten im Scratch-Dokument nach.
    Container werden als App::Part (rein organisatorisch, kein
    eigenes Placement) angelegt, Blätter als App::Link mit ihrer
    vollen, bereits berechneten Weltplatzierung. Gibt das erzeugte
    Scratch-Objekt zurück."""
    kind = node[0]

    if kind == "leaf":
        _, obj, ext_placement = node
        counter[0] += 1
        link = make_export_link(
            scratch_doc, obj, ext_placement, counter[0], color_map, colored_cache
        )
        return link

    _, obj, children = node
    counter[0] += 1
    part = scratch_doc.addObject("App::Part", "Group%03d" % counter[0])
    part.Label = obj.Label
    for child_node in children:
        child_obj = materialize_tree(
            scratch_doc, child_node, color_map, colored_cache, counter
        )
        part.addObject(child_obj)
    return part


def ask_filename(doc):
    if doc.FileName:
        default = os.path.splitext(doc.FileName)[0] + ".glb"
    else:
        default = doc.Name + ".glb"
    filename, _ = QtWidgets.QFileDialog.getSaveFileName(
        None, "GLB exportieren als", default, "glTF Binary (*.glb)"
    )
    return filename


def export_visible_glb(doc=None):
    doc = doc or App.ActiveDocument
    if doc is None:
        App.Console.PrintError("export_visible: Kein aktives Dokument.\n")
        return

    filename = ask_filename(doc)
    if not filename:
        App.Console.PrintMessage(
            "export_visible: Abgebrochen (kein Dateiname gewählt).\n"
        )
        return
    if not filename.lower().endswith(".glb"):
        filename += ".glb"

    # Farbzuordnung und sichtbare Blätter direkt am (unveränderten)
    # Original-Dokument ermitteln - nur Lesezugriffe.
    color_map = {}
    for root in get_top_level_objects(doc):
        collect_source_colors(root, color_map, frozenset())

    tree_nodes = []
    for root in get_top_level_objects(doc):
        node = build_tree(root, App.Placement(), frozenset())
        if node is not None:
            tree_nodes.append(node)

    if not tree_nodes:
        App.Console.PrintWarning(
            "export_visible: Keine sichtbaren Objekte mit Shape gefunden.\n"
        )
        return

    # Scratch-Dokument anlegen und sofort speichern - App::Link
    # zwischen zwei Dokumenten setzt voraus, dass beide einen
    # Speicherort auf der Platte haben.
    scratch_name = "ExportVisibleScratch"
    if scratch_name in App.listDocuments():
        App.closeDocument(scratch_name)
    scratch_doc = App.newDocument(scratch_name)
    scratch_path = os.path.join(tempfile.gettempdir(), scratch_name + ".FCStd")
    scratch_doc.saveAs(scratch_path)

    colored_cache = {}
    counter = [0]
    top_children = []
    for node in tree_nodes:
        top_obj = materialize_tree(scratch_doc, node, color_map, colored_cache, counter)
        top_children.append(top_obj)

    # Alles unter einer einzigen, nach der Exportdatei benannten
    # Top-Level-Gruppe zusammenfassen, statt mehrere einzelne
    # Wurzelobjekte zu exportieren - sonst zeigt der Viewer-Baum den
    # technischen Scratch-Dokumentnamen statt eines sinnvollen Namens.
    export_label = os.path.splitext(os.path.basename(filename))[0]
    top_part = scratch_doc.addObject("App::Part", "ExportRoot")
    top_part.Label = export_label
    for child in top_children:
        top_part.addObject(child)
    export_objs = [top_part]
    scratch_doc.recompute()

    ImportGui.export(export_objs, filename)

    def count_leaves(node):
        if node[0] == "leaf":
            return 1
        return sum(count_leaves(c) for c in node[2])

    total_leaves = sum(count_leaves(n) for n in tree_nodes)

    msg = (
        "%d sichtbare Objekte exportiert (%d Instanzfarben angewandt) "
        "nach:\n%s" % (total_leaves, len(colored_cache), filename)
    )
    App.Console.PrintMessage("export_visible: " + msg.replace("\n", " ") + "\n")
    App.Console.PrintMessage(
        "export_visible: Scratch-Dokument '%s' bleibt zum Debuggen offen "
        "(Datei: %s) - danach manuell schließen.\n" % (scratch_doc.Name, scratch_path)
    )

    QtWidgets.QMessageBox.information(None, "Export erfolgreich", msg)


if __name__ == "__main__":
    export_visible_glb()
