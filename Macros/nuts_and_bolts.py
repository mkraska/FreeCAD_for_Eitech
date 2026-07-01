# nuts_and_bolts.py  v1.1
# Eitech Workbench – Schrauben und Muttern in Assembly einfügen
#
# Aufruf: Als Makro in FreeCAD 1.1 ausführen

import FreeCAD as App
import FreeCADGui as Gui
import Part
import math
import random

try:
    import UtilsAssembly
    import JointObject
except ImportError:
    App.Console.PrintError("schrauben_platzierung: Assembly-Module nicht gefunden.\n")

try:
    from PySide6 import QtWidgets, QtCore
except ImportError:
    from PySide2 import QtWidgets, QtCore


# ---------------------------------------------------------------------------
# Icons (Base64)
# ---------------------------------------------------------------------------
ICONS = {}
ICONS["Gewindestift"] = "iVBORw0KGgoAAAANSUhEUgAAADgAAAA4CAYAAACohjseAAAEN0lEQVR4nO2YXW8VRRiAn5md3e12S9vDZ3va0AJ+kxouCkKMxkjQGyKQABqv/A3qL1AvNF4ZEo3cGk30Qi5MDAkIBosmRlBJDASxYkukSAunPYezZz9mxotjiyZemLibsMk+V7vZzew8eWff950RCwsLlhyx1uK6Lr7vY+1/H7rT6WCMyXMqAMjcR7zHqATLTiX4f9Fadz8k735q+Xr5WZEUJmitxVpLGIY4jkOr1cIYgzGGVquFlJIwDFfeLQpVxKDWWqSUSCk5duxTTnxxms2bNvHqKy8D8P7Ro/wy/Ss7t09y8NAhlKuIoqiIqSDyroPGGIIgQAh48623uXb9Bk88tZsL579l68MPAfDTxUts276TM6dOooTljddfIwxD2u32P5ZyHuS+RIWQWGN4972jTP92jb37DhCGvVgkRvVgVA8Wie95HDh4mGbU4Z0jR4jjOHc5yFnQGENvb8CPFy4wN3+bsfExtNZ0Oh08z6NWq1Gr1fA8jySJSbOMkfoIU2e/5uKlSwRBkHs3k6ugtRbHcZiZnWV88304jmJpcZG+vj6stWit0VpjrCEIeum02zQatxkZHcUUlFFzFRRCYIxhw7r1NJcWmdyxi5mrV7ly+fJKZKy1CCG4+ccNvjk7RX10lNVr1pKVRTBNU4brI8zOXEU6Doeff4EHNm8kat9BCIFSilvz8/xw7juG6nWCoJeb8/MMDtYwWiOEyHNK+ScZaw3KVQwN1zl14jhJ1GT/vucYGh4mzTKstfStWsXWR7cRtdt8f/4cq9dtIAhDtMk/irnXQSEEWZYRhn14ns8HH37Ex5+4LDWbPPjIBEIIlhYXmTrzJZm1DNRq9IZ9ZGmae/SgkE7G4roeWms8z6M+shGhfKIoQohum5akKUH/ABvqI7jKReusEDnIOYLWWpRymZ2doRNFrOrvJ05i+gf6WZj3Of75Zxht6MQJ69esJU1SoNv1iAJqIBQg6DiKubnrRFHEwOAgQgh0phkdG6e51KTVauL4PRht6AZNdGtlFCHEPV7opZTEccyOyUm0ThBCIITAWkuWpkgpUcrFGoux3bKhXI+bc9fRaXLv/4NCCDqdDmPjYzz95ONMX/kZISS+76OU6i5FAY7j4CoXpMPv12bZ+8xuJiYm/vpP85XMPYtKKblzp82ze/agHIeTp78iihOU55NpTbvdZqnZJEliAs/lpRcPc2D/fhqNRiG9aO67ieVTNdfzCHp6uHVrgamps1yZ/pVGY5EsyxgcHOD+LVvYtfMxhoaHiaKIOI4LOVUrTND3fbTWXVnX7T4zBgQrySTLMpIkQUpZ2LFhIRveZaSUKxIrCQewxrJcHopYln+nUEHoJh7Hce7eAzjFFPV/ozpVKzuVYNmpBMtOJVh2KsGyUwmWnUqw7FSCZacSLDuVYNmpBMtOJVh2KsGyUwmWnUqw7PwJZEHKaWSo0XQAAAAASUVORK5CYII="
ICONS["Mutter"] = "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"
ICONS["Schraube_6_Schlitz"] = "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"
ICONS["Schraube_8_Schlitz"] = "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"
ICONS["Schraube_12_Schlitz"] = "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"
ICONS["Schraube_16_Schlitz"] = "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"


def _icon(name):
    """Lädt ein Icon, Hintergrund weiß."""
    import base64
    data = ICONS.get(name)
    if data is None:
        return QtGui.QIcon()
    from PySide6 import QtGui as _QtGui
    pix = _QtGui.QPixmap()
    pix.loadFromData(base64.b64decode(data), "PNG")
    img = pix.toImage().convertToFormat(_QtGui.QImage.Format_ARGB32)
    bg = _QtGui.QColor(237, 237, 237)
    white = _QtGui.QColor(255, 255, 255)
    for x in range(img.width()):
        for y in range(img.height()):
            c = _QtGui.QColor(img.pixel(x, y))
            if abs(c.red()-bg.red()) < 25 and abs(c.green()-bg.green()) < 25 and abs(c.blue()-bg.blue()) < 25:
                img.setPixelColor(x, y, white)
    pix = _QtGui.QPixmap.fromImage(img)
    return _QtGui.QIcon(pix)


# ---------------------------------------------------------------------------
# Observer-Verwaltung: beim Neustart alle alten Observer entfernen
# ---------------------------------------------------------------------------

_OBSERVER_REGISTRY_ATTR = "_schrauben_observer_instance"

def _cleanup_old_observer():
    """Entfernt einen evtl. noch laufenden Observer aus einer früheren Instanz."""
    import builtins
    old = getattr(builtins, _OBSERVER_REGISTRY_ATTR, None)
    if old is not None:
        try:
            Gui.Selection.removeObserver(old)
            App.Console.PrintMessage("schrauben_platzierung: alter Observer entfernt.\n")
        except Exception:
            pass
        setattr(builtins, _OBSERVER_REGISTRY_ATTR, None)

def _register_observer(observer):
    import builtins
    setattr(builtins, _OBSERVER_REGISTRY_ATTR, observer)

def _unregister_observer(observer):
    import builtins
    setattr(builtins, _OBSERVER_REGISTRY_ATTR, None)

_cleanup_old_observer()

# ---------------------------------------------------------------------------
# Konfiguration – später in Workbench-Einstellungen auslagern
# ---------------------------------------------------------------------------

# Pfad zur FCStd-Datei mit den Schrauben-Bodies
SCHRAUBEN_DATEI = r"C:\Users\kraska\Documents\Eitech\CAD\Teile\Schrauben.FCStd"

# Body-Namen in der Schrauben-Datei → werden zur Laufzeit geladen
# Format: { "Anzeigename": "Body-Name-in-FCStd" }
SCHRAUBEN_BODIES = {
    "Schraube 6 Schlitz":  "Body",
    "Schraube 8 Schlitz":  "Body001",
    "Schraube 12 Schlitz": "Body002",
    "Schraube 16 Schlitz": "Body003",
    "Gewindestift":        "Body005",
}

LCS_BOLT_NAME = "LCS_bolt"
LCS_NUT_NAME  = "LCS_nut"
MUTTER_LABEL     = "Mutter"
MUTTER_DICKE     = 3.2

# Format für Dialog: (Anzeigename, Body-Name, Icon-Name, ist_gewindestift)
SCHRAUBEN = [
    ("Schraube 6 Schlitz",  "Body",    "Schraube_6_Schlitz",  False),
    ("Schraube 8 Schlitz",  "Body001", "Schraube_8_Schlitz",  False),
    ("Schraube 12 Schlitz", "Body002", "Schraube_12_Schlitz", False),
    ("Schraube 16 Schlitz", "Body003", "Schraube_16_Schlitz", False),
    ("Gewindestift",        "Body005", "Gewindestift",        True),
]

# ---------------------------------------------------------------------------
# Geometrie-Hilfsfunktionen
# ---------------------------------------------------------------------------

def get_global_placement(link_obj):
    """Globales Placement eines Link-Objekts (inkl. Assembly-Hierarchie)."""
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


def kreiskante_placement(edge, link_obj, lcs_rotation):
    """
    Berechnet Placement2 für einen Fixed Constraint am Lochrand.
    lcs_rotation: Rotation des LCS_bolt – wird direkt übernommen damit
                  alle Achsen mit Placement1 übereinstimmen.
    """
    if not hasattr(edge, 'Curve') or not isinstance(edge.Curve, Part.Circle):
        raise ValueError("Gewählte Kante ist kein Kreis.")

    circle = edge.Curve
    center_global = circle.Center
    axis_global   = circle.Axis
    axis_global.normalize()

    App.Console.PrintMessage(f"  Kreismittelpunkt global: {center_global}\n")
    App.Console.PrintMessage(f"  Kreisachse global:       {axis_global}\n")

    # In lokales KS des Links transformieren
    global_pl = get_global_placement(link_obj)
    inv = global_pl.inverse()
    center_local = inv.multVec(center_global)
    axis_local   = inv.Rotation.multVec(axis_global)
    axis_local.normalize()

    App.Console.PrintMessage(f"  Kreismittelpunkt lokal:  {center_local}\n")
    App.Console.PrintMessage(f"  Kreisachse lokal:        {axis_local}\n")

    # Rotation = LCS_bolt Rotation: FreeCAD bringt P1 auf P2 zur Deckung,
    # alle Achsen müssen übereinstimmen.
    # Vorzeichen der X-Achse prüfen: LCS_bolt X soll antiparallel zu axis_local sein
    lcs_x = lcs_rotation.multVec(App.Vector(1, 0, 0))
    dot = lcs_x.dot(axis_local)
    if dot > 0:
        # LCS_bolt X zeigt in gleiche Richtung wie Achse → umdrehen
        flip = App.Rotation(App.Vector(0, 1, 0), 180)
        rot = lcs_rotation.multiply(flip)
        App.Console.PrintMessage(f"  Rotation umgedreht (dot={dot:.2f})\n")
    else:
        rot = lcs_rotation
        App.Console.PrintMessage(f"  Rotation direkt (dot={dot:.2f})\n")

    return App.Placement(center_local, rot)


def lcs_placement_im_body(body, lcs_name):
    """
    Gibt das Placement des benannten LCS im lokalen KS des Bodies zurück.
    Sucht in body.OutList nach dem LCS-Objekt.
    """
    for obj in body.OutList:
        if obj.Label == lcs_name or obj.Name == lcs_name:
            return obj.Placement
    # Auch in verschachtelten Objekten suchen
    for obj in body.Document.Objects:
        if (obj.Label == lcs_name or obj.Name == lcs_name):
            if body in obj.InList or any(body.Name == p.Name for p in obj.InList):
                return obj.Placement
    raise ValueError(f"LCS '{lcs_name}' nicht in Body '{body.Label}' gefunden.")


def zufaellige_x_rotation():
    """Zufällige Rotation um X-Achse (0–360°)."""
    angle = random.uniform(0, 2 * math.pi)
    return App.Rotation(App.Vector(1, 0, 0), math.degrees(angle))


def schnittpunkt_achse_flaeche(achse_ursprung, achse_richtung, face):
    """
    Berechnet den Schnittpunkt einer Linie (Schraubenachse) mit einer Fläche.
    Gibt App.Vector zurück oder None wenn kein Schnittpunkt.
    """
    try:
        line = Part.Line(achse_ursprung, achse_ursprung + achse_richtung)
        shape = line.toShape(-1000, 1000)
        intersection = face.Surface.intersect(line)
        if intersection and len(intersection[0]) > 0:
            pt = intersection[0][0]
            return App.Vector(pt.X, pt.Y, pt.Z)
    except Exception as e:
        App.Console.PrintWarning(f"Schnittpunkt-Berechnung fehlgeschlagen: {e}\n")
    return None


# ---------------------------------------------------------------------------
# Assembly-Hilfsfunktionen
# ---------------------------------------------------------------------------

def get_active_assembly():
    """Gibt das aktive Assembly-Objekt zurück."""
    try:
        return UtilsAssembly.activeAssembly()
    except Exception:
        # Fallback: erstes Assembly in aktivem Dokument suchen
        doc = App.ActiveDocument
        if doc is None:
            return None
        for obj in doc.Objects:
            if obj.TypeId == "Assembly::AssemblyObject":
                return obj
        return None


def link_zu_assembly(assembly, body, label):
    """Fügt einen App::Link für body zur Assembly hinzu."""
    internal_name = label.replace(' ', '_').replace('ü','ue').replace('ä','ae').replace('ö','oe')
    item = assembly.newObject("App::Link", internal_name)
    item.LinkedObject = body
    item.Label = label
    return item


def _strip_link_prefix(link_obj, subelement_name):
    """
    SubElementNames aus Gui.Selection.getSelectionEx('', 0) sind relativ zum
    ganz oben selektierten Objekt (z.B. der Root-Assembly) und enthalten
    dadurch bei verschachtelten Sub-Assemblies den Namen von link_obj selbst
    als redundantes erstes Pfad-Segment (z.B. 'Assembly001.Assembly002.Body.Edge6'
    obwohl link_obj bereits 'Assembly001' ist).
    Joint.ReferenceX erwartet aber einen SubElementName RELATIV zu link_obj
    -> redundantes Präfix entfernen, sonst schlägt getSubObject() fehl und
    der Joint bekommt eine falsche/zufällige Placement.
    """
    if link_obj is None or not subelement_name:
        return subelement_name
    prefix = link_obj.Name + "."
    if subelement_name.startswith(prefix):
        return subelement_name[len(prefix):]
    return subelement_name


def fixed_joint_erstellen(assembly, ref1_link, ref1_edge_name,
                           ref2_link, ref2_edge_name,
                           label="StarrerVerbund"):
    """
    Legt einen Fixed Joint an ohne globales recompute().
    """
    if ref1_link is None or ref1_edge_name is None:
        App.Console.PrintError(f"fixed_joint_erstellen: ref1_link={ref1_link} ref1_edge_name={ref1_edge_name}\n")
        return None
    if ref2_link is None or ref2_edge_name is None:
        App.Console.PrintError(f"fixed_joint_erstellen: ref2_link={ref2_link} ref2_edge_name={ref2_edge_name}\n")
        return None
    doc = App.ActiveDocument

    # Redundantes Namens-Präfix entfernen (siehe _strip_link_prefix)
    ref1_edge_name = _strip_link_prefix(ref1_link, ref1_edge_name)
    ref2_edge_name = _strip_link_prefix(ref2_link, ref2_edge_name)

    joints_group = None
    for obj in assembly.OutList:
        if obj.TypeId == "Assembly::JointGroup":
            joints_group = obj
            break
    if joints_group is None:
        joints_group = assembly.newObject("Assembly::JointGroup", "Joints")

    joint = joints_group.newObject("App::FeaturePython", "Joint")
    JointObject.Joint(joint, 0)
    JointObject.ViewProviderJoint(joint.ViewObject)

    joint.Label     = label
    joint.JointType = "Fixed"
    joint.Detach1   = False
    joint.Detach2   = False

    try:
        joint.Reference1 = (ref1_link, [ref1_edge_name, ref1_edge_name])
    except Exception as e:
        App.Console.PrintMessage(f"  Reference1 Fehler: {e}\n")
    try:
        joint.Reference2 = (ref2_link, [ref2_edge_name, ref2_edge_name])
    except Exception as e:
        App.Console.PrintMessage(f"  Reference2 Fehler: {e}\n")

    joint.Visibility = False
    joint.recompute()

    p1_after = joint.Placement1
    p2_after = joint.Placement2

    # ~180°-Rotation korrigieren
    q2w = p2_after.Rotation.Q[3]
    q1w = p1_after.Rotation.Q[3]
    if abs(q2w) < 0.1 and abs(q1w) > 0.9:
        flip = App.Rotation(App.Vector(0, 1, 0), 180)
        joint.Detach1 = True
        p1c = joint.Placement1
        joint.Placement1 = App.Placement(p1c.Base, p1c.Rotation.multiply(flip))
        joint.recompute()

    return joint


def joint_orientierung_pruefen_und_korrigieren(joint, schraube_link, lcs_placement, axis_global, click_pos, center_global):
    """
    Prüft ob der Schraubenkopf auf der richtigen Seite sitzt.
    Kriterium: LCS_bolt Ursprung (= Kopfauflagefläche) soll auf der Seite von
    axis_global liegen (vom Material weg = Kopfseite).
    """
    # LCS_bolt Ursprung in Weltkoordinaten nach dem Solver
    schraube_welt = schraube_link.Placement
    lcs_ursprung_welt = schraube_welt.multVec(lcs_placement.Base)

    # Vektor vom Lochrand zum LCS_bolt Ursprung
    vec = lcs_ursprung_welt - center_global
    dot = vec.dot(axis_global)
    App.Console.PrintMessage(f"  Orientierungscheck: lcs_ursprung={lcs_ursprung_welt} dot={dot:.3f}\n")

    if dot < 0:
        # Kopf auf der falschen Seite → invertieren
        App.Console.PrintMessage(f"  → Invertiere Joint\n")
        flip = App.Rotation(App.Vector(0, 1, 0), 180)
        p1 = joint.Placement1
        joint.Detach1 = True
        joint.Placement1 = App.Placement(p1.Base, p1.Rotation.multiply(flip))
        pass  # kein globales recompute
    else:
        App.Console.PrintMessage(f"  → Orientierung korrekt\n")


# ---------------------------------------------------------------------------
# Selektions-Hilfsfunktionen
# ---------------------------------------------------------------------------

def get_selected_circular_edge():
    """
    Gibt (link_obj, edge, edge_name) der aktuell selektierten
    kreisförmigen Kante zurück, oder None.
    link_obj ist das direkte Selektions-Objekt (kann Part-Feature oder Link sein).
    """
    sel = Gui.Selection.getSelectionEx()
    for s in sel:
        for sub_name, sub_obj in zip(s.SubElementNames, s.SubObjects):
            if isinstance(sub_obj, Part.Edge):
                if hasattr(sub_obj, 'Curve') and isinstance(sub_obj.Curve, Part.Circle):
                    return s.Object, sub_obj, sub_name
    return None


def find_link_in_assembly(assembly, raw_obj, click_pos=None):
    """
    Sucht den App::Link in der Assembly der das angeklickte Objekt enthält.
    Bei mehreren Kandidaten (gleicher Body mehrfach) wird der dem Klickpunkt
    nächste Link gewählt.
    """
    group = assembly.Group if hasattr(assembly, 'Group') else []

    # Alle Links sammeln die raw_obj enthalten
    kandidaten = []
    for link in group:
        if link.TypeId != "App::Link":
            continue
        linked = link.LinkedObject
        while hasattr(linked, 'LinkedObject') and linked.LinkedObject:
            linked = linked.LinkedObject
        if linked.Name == raw_obj.Name:
            kandidaten.append(link)
            continue
        if hasattr(linked, 'OutList'):
            for child in linked.OutList:
                if child.Name == raw_obj.Name:
                    kandidaten.append(link)
                    break

    if not kandidaten:
        return None
    if len(kandidaten) == 1:
        return kandidaten[0]

    # Mehrere Kandidaten → dem Klickpunkt nächsten wählen
    if click_pos is not None:
        best = None
        best_dist = 1e10
        for link in kandidaten:
            link_pos = link.Placement.Base
            dist = (link_pos - click_pos).Length
            App.Console.PrintMessage(f"  Kandidat: {link.Name} Pos={link_pos} dist={dist:.1f}\n")
            if dist < best_dist:
                best_dist = dist
                best = link
        return best

    return kandidaten[0]


def lcs_attachment_edge_name(body, lcs_name):
    """
    Gibt den Edge-Namen zurück an dem LCS im Body attached ist.
    Falls das Attachment eine Fläche ist (z.B. beim Gewindestift),
    wird die nächste Kreiskante auf dieser Fläche gesucht.
    """
    import Part as P
    lcs_obj = None
    for obj in body.OutList:
        if obj.Label == lcs_name or obj.Name == lcs_name:
            lcs_obj = obj
            if hasattr(obj, 'AttachmentSupport') and obj.AttachmentSupport:
                support = obj.AttachmentSupport
                if support and len(support) > 0:
                    feature, subs = support[0]
                    if subs:
                        sub = subs[0]
                        # Wenn es schon eine Edge ist → direkt zurückgeben
                        if sub.startswith('Edge'):
                            return sub
                        # Wenn es eine Fläche ist → nächste Kreiskante suchen
                        if sub.startswith('Face') and hasattr(feature, 'Shape'):
                            try:
                                face_idx = int(sub[4:]) - 1
                                face = feature.Shape.Faces[face_idx]
                                # Kreiskante mit größtem Radius auf dieser Fläche
                                lcs_pos = lcs_obj.Placement.Base if lcs_obj else None
                                best = None
                                best_dist = 1e10
                                for i, e in enumerate(feature.Shape.Edges):
                                    if not hasattr(e.Curve, 'Center'):
                                        continue
                                    if lcs_pos:
                                        d = (e.Curve.Center - lcs_pos).Length
                                        if d < best_dist:
                                            best_dist = d
                                            best = f"Edge{i+1}"
                                    else:
                                        best = f"Edge{i+1}"
                                        break
                                if best:
                                    App.Console.PrintMessage(
                                        f"  lcs_attachment: {sub} → Kreiskante {best}\n")
                                    return best
                            except Exception as e:
                                App.Console.PrintMessage(
                                    f"  lcs_attachment Fallback Fehler: {e}\n")
                        return sub
    return None


def get_face_normal_at_edge(edge, raw_obj):
    """
    Bestimmt die Flächennormale 'vom Material weg' an einer Kreiskante.
    Nutzt ancestorsOfType um angrenzende Flächen zu finden.
    raw_obj = das direkt selektierte Objekt (aus getSelectionEx).
    Gibt die Normale der anliegenden ebenen Fläche in Weltkoordinaten zurück.
    """
    try:
        import Part as P
        faces = raw_obj.Shape.ancestorsOfType(edge, P.Face)
        App.Console.PrintMessage(f"  ancestorsOfType: {len(faces)} Flächen\n")

        for face in faces:
            if isinstance(face.Surface, P.Plane):
                normal = face.normalAt(0, 0)
                App.Console.PrintMessage(f"  Plane normal (Welt): {normal}\n")
                return normal
            if isinstance(face.Surface, P.Cylinder):
                # Zylinder-CoG zeigt ins Material → Normale umgekehrt
                cog = face.CenterOfGravity
                center = edge.Curve.Center
                axis = edge.Curve.Axis
                axis.normalize()
                vec = cog - center
                along = vec.dot(axis)
                perp = vec - axis * along
                if perp.Length > 1e-6:
                    normal = perp * (-1.0 / perp.Length)
                    App.Console.PrintMessage(f"  Zylinder CoG-Methode normal (Welt): {normal}\n")
                    return normal

        return None
    except Exception as e:
        App.Console.PrintMessage(f"  Flächennormale Fehler: {e}\n")
        return None


def get_selected_face():
    """
    Gibt (link_obj, face, face_name) der aktuell selektierten Fläche zurück,
    oder None.
    """
    sel = Gui.Selection.getSelectionEx()
    for s in sel:
        for sub_name, sub_obj in zip(s.SubElementNames, s.SubObjects):
            if isinstance(sub_obj, Part.Face):
                return s.Object, sub_obj, sub_name
    return None


# ---------------------------------------------------------------------------
# Hauptlogik: Schraube einfügen
# ---------------------------------------------------------------------------

def schraube_einfuegen(assembly, body, body_label,
                        target_link, edge, edge_name, raw_obj,
                        click_pos=None, real_axis=None, real_center=None,
                        zufaellig_drehen=False):
    """
    Fügt eine Schraube (body) als Link in assembly ein und verbindet sie
    mit einem Fixed Constraint an der gewählten Kreiskante.
    """
    App.Console.PrintMessage(f"Schritt 1: LCS_bolt aus Schrauben-Body lesen\n")
    try:
        p1 = lcs_placement_im_body(body, LCS_BOLT_NAME)
    except ValueError as e:
        App.Console.PrintError(f"LCS_bolt nicht gefunden: {e}\n")
        return None

    basis_rotation = p1.Rotation

    App.Console.PrintMessage(f"Schritt 2: Kreisachse und Mittelpunkt in Weltkoordinaten\n")
    if real_center is not None:
        center_global = App.Vector(real_center.x, real_center.y, real_center.z)
    else:
        # Fallback: lokalen Center mit Link-Placement transformieren
        link_pl = get_global_placement(target_link)
        center_global = link_pl.multVec(edge.Curve.Center)
    axis_global   = edge.Curve.Axis
    axis_global.normalize()

    # Flächennormale der anliegenden ebenen Fläche bestimmen
    # (zeigt vom Material weg = Kopfseite)
    # 3. Schraubenachse = Kreisachse in Weltkoordinaten (aus resolve=0)
    if real_axis is not None:
        axis_global = App.Vector(real_axis.x, real_axis.y, real_axis.z)
        axis_global.normalize()
    else:
        axis_global = edge.Curve.Axis
        axis_global.normalize()

    App.Console.PrintMessage(f"Schritt 2: Achse={axis_global}  Mittelpunkt={center_global}\n")
    App.Console.PrintMessage(f"Schritt 3: Vorzeichen der Achse bestimmen (CoG-Methode)\n")
    import Part as P

    def _find_adjacent_faces_geometric(target_edge, shape, tol=1e-4):
        """
        Fallback für ancestorsOfType: sucht Flächen, deren Kreiskante
        geometrisch (Center/Achse/Radius) zur target_edge passt, statt
        exakte Shape-Identität vorauszusetzen.
        Nötig bei tief verschachtelten / gespiegelten Sub-Assemblies, wo
        die selektierte Edge eine transformierte Kopie ist und
        ancestorsOfType mit 'NCollection_IndexedDataMap::FindFromKey'
        fehlschlägt.
        Gibt (faces, matched_local_edge) zurück – matched_local_edge stammt
        garantiert aus `shape` selbst und ist damit im gleichen lokalen KS
        wie face.CenterOfGravity (im Gegensatz zu target_edge, die evtl.
        eine transformierte Kopie aus einem anderen KS ist).
        """
        try:
            t_center = target_edge.Curve.Center
            t_axis   = target_edge.Curve.Axis
            t_axis.normalize()
            t_radius = target_edge.Curve.Radius
        except Exception:
            return [], None

        matches = []
        matched_local_edge = None
        for face in shape.Faces:
            for e in face.Edges:
                try:
                    if not isinstance(e.Curve, P.Circle):
                        continue
                    if abs(e.Curve.Radius - t_radius) > tol:
                        continue
                    if (e.Curve.Center - t_center).Length > tol:
                        continue
                    ax = e.Curve.Axis
                    ax.normalize()
                    if abs(abs(ax.dot(t_axis)) - 1.0) > 1e-3:
                        continue
                    matches.append(face)
                    if matched_local_edge is None:
                        matched_local_edge = e
                    break
                except Exception:
                    continue
        return matches, matched_local_edge

    # raw_obj ist bereits das per getSelectionEx('', 0) (resolve=0) korrekt
    # aufgelöste Feature-Objekt. Für die reine Vorzeichen-Bestimmung
    # (welche Seite der Kante zeigt zum Material) brauchen wir KEINE
    # Weltkoordinaten – nur ein für Kante und Fläche konsistentes KS, der
    # Dot-Product-Vergleich ist unter jeder starren Transformation invariant.
    #
    # Schnellster & robustester Weg: das tatsächliche Bauteil (z.B.
    # Kühlergrill_LKW) über raw_obj.getSubObjectList(edge_name) auflösen
    # (liefert die Objekt-Kette, kein Shape-Transform nötig) und den
    # Edge-Index aus dem letzten SubElementName-Segment ('Edge150' -> 149)
    # direkt im LOKALEN Shape dieses Bauteils verwenden. Kein Weltkoordinaten-
    # Transform, keine großen Compound-Shapes -> kein 'hasher mismatch',
    # deutlich schneller (nur die Edges des Bauteils selbst statt des
    # gesamten Assemblies).
    faces = []
    local_edge_for_cog = edge  # Fallback: Original-Edge-Objekt
    lokal_erfolgreich = False

    # Für den Fixed Joint (Schritt 6) brauchen wir ein Referenz-Objekt +
    # einen dazu RELATIVEN SubElementName. Standard (Fallback, falls die
    # lokale Methode unten scheitert): target_link + voller edge_name
    # (mit redundantem Präfix, das _strip_link_prefix() später entfernt).
    # Bei Erfolg der lokalen Methode wird das direkt durch das echte
    # Blatt-Objekt + den simplen lokalen Edge-Namen ersetzt (verifiziert an
    # der Konsole: liefert exakt dasselbe Placement2, aber ganz ohne
    # Präfix-Stringoperationen und ohne die kryptischen Hash-Segmente).
    joint_ref2_link = target_link
    joint_ref2_edge_name = edge_name

    try:
        kette = raw_obj.getSubObjectList(edge_name)
        leaf_obj = kette[-1]
        letztes_segment = edge_name.split('.')[-1]
        if letztes_segment.startswith('Edge') and hasattr(leaf_obj, 'Shape'):
            edge_idx = int(letztes_segment[4:]) - 1
            local_shape = leaf_obj.Shape
            if 0 <= edge_idx < len(local_shape.Edges):
                kandidat_edge = local_shape.Edges[edge_idx]
                if (isinstance(kandidat_edge.Curve, P.Circle)
                        and abs(kandidat_edge.Curve.Radius - edge.Curve.Radius) < 1e-4):
                    try:
                        faces = local_shape.ancestorsOfType(kandidat_edge, P.Face)
                    except Exception:
                        faces = []
                    if not faces:
                        faces, matched = _find_adjacent_faces_geometric(kandidat_edge, local_shape)
                        if matched is not None:
                            kandidat_edge = matched
                    if faces:
                        local_edge_for_cog = kandidat_edge
                        lokal_erfolgreich = True
                        # Joint-Referenz auf das echte Blatt-Objekt umstellen
                        # (an der Konsole verifiziert: identisches Placement2
                        # wie über target_link + Präfix-gestripptem Pfad).
                        joint_ref2_link = leaf_obj
                        joint_ref2_edge_name = letztes_segment
                        App.Console.PrintMessage(
                            f"Schritt 3: {len(faces)} Flächen rein lokal auf "
                            f"{leaf_obj.Name} (Edge-Index {edge_idx}, "
                            f"{len(local_shape.Edges)} Edges im Bauteil) gefunden\n")
                else:
                    App.Console.PrintWarning(
                        f"Schritt 3: lokaler Edge-Index {edge_idx} auf {leaf_obj.Name} "
                        f"passt nicht zur Kreiskante (Radius-Mismatch)\n")
            else:
                App.Console.PrintWarning(
                    f"Schritt 3: Edge-Index {edge_idx} außerhalb "
                    f"({len(local_shape.Edges)} Edges auf {leaf_obj.Name})\n")
    except Exception as ex:
        App.Console.PrintWarning(f"Schritt 3: lokale Edge-Index-Methode fehlgeschlagen: {ex}\n")

    if not lokal_erfolgreich:
        App.Console.PrintWarning(
            "Schritt 3: lokale Methode nicht erfolgreich – "
            "versuche welt-transformierte Kandidaten als Fallback\n")
        search_kandidaten = []
        try:
            objekt_pfad = edge_name.rsplit('.', 1)[0] + '.'
            bauteil_shape = raw_obj.getSubObject(objekt_pfad)
            if bauteil_shape is not None and hasattr(bauteil_shape, 'Faces') and bauteil_shape.Faces:
                search_kandidaten.append((f"Bauteil (Pfad='{objekt_pfad}')", bauteil_shape))
        except Exception:
            pass
        if target_link is not None and hasattr(target_link, 'Shape') and target_link.Name != raw_obj.Name:
            search_kandidaten.append((f"target_link={target_link.Name}", target_link.Shape))
        search_kandidaten.append((f"raw_obj={raw_obj.Name}", raw_obj.Shape))

        for such_label, such_shape in search_kandidaten:
            try:
                faces = such_shape.ancestorsOfType(edge, P.Face)
                if not faces:
                    raise ValueError("ancestorsOfType lieferte 0 Flächen")
                App.Console.PrintMessage(
                    f"Schritt 3: {len(faces)} angrenzende Flächen gefunden ({such_label})\n")
                break
            except Exception as ex:
                App.Console.PrintWarning(
                    f"Schritt 3: ancestorsOfType auf {such_label} fehlgeschlagen ({ex}) – "
                    f"versuche geometrischen Fallback\n")
                try:
                    faces, matched_local_edge = _find_adjacent_faces_geometric(edge, such_shape)
                    if faces:
                        if matched_local_edge is not None:
                            local_edge_for_cog = matched_local_edge
                        App.Console.PrintMessage(
                            f"Schritt 3: {len(faces)} Flächen via geometrischem Fallback "
                            f"auf {such_label} gefunden\n")
                        break
                except Exception as ex2:
                    App.Console.PrintWarning(
                        f"Schritt 3: geometrischer Fallback auf {such_label} fehlgeschlagen: {ex2}\n")

    # center_local/axis_local stammen aus local_edge_for_cog, die garantiert

    # im gleichen lokalen KS liegt wie face.CenterOfGravity -> kein
    # Transformieren nötig.
    center_local = local_edge_for_cog.Curve.Center
    axis_local   = local_edge_for_cog.Curve.Axis
    axis_local.normalize()

    cog_vec = None
    for face in faces:
        if isinstance(face.Surface, (P.Cylinder, P.Cone)):
            cog_lokal = face.CenterOfGravity
            cog_vec   = cog_lokal - center_local
            App.Console.PrintMessage(
                f"Schritt 3: Zylinder R={face.Surface.Radius:.2f}  CoG_lokal={cog_lokal}\n")
            break

    if cog_vec is None:
        # Fallback: ebene Fläche, Normale nach außen
        for face in faces:
            if isinstance(face.Surface, P.Plane):
                normal_lokal = face.Surface.Axis
                cog_vec      = normal_lokal * -1  # nach innen drehen
                break

    cog_unbekannt = False
    if cog_vec is not None and cog_vec.Length > 1e-6:
        dot_cog = cog_vec.dot(axis_local)
        App.Console.PrintMessage(f"Schritt 3: dot(cog_vec, axis_local)={dot_cog:.4f}\n")
        if dot_cog > 0:
            # CoG und Achse gleichsinnig → Achse zeigt ins Material → umdrehen
            axis_global = App.Vector(-axis_global.x, -axis_global.y, -axis_global.z)
            App.Console.PrintMessage(f"Schritt 3: Achse umgedreht (CoG zeigt ins Material)\n")
        else:
            App.Console.PrintMessage(f"Schritt 3: Achse korrekt (zeigt aus Material)\n")
    else:
        App.Console.PrintWarning(f"Schritt 3: Orientierung unbekannt – Flip-Button verfügbar\n")
        cog_unbekannt = True


    # Numerisches Rauschen entfernen: Komponenten nahe 0 oder ±1 snappen
    def snap_axis(v, tol=0.001):
        comps = [v.x, v.y, v.z]
        for i, c in enumerate(comps):
            if abs(c) < tol:
                comps[i] = 0.0
            elif abs(abs(c) - 1.0) < tol:
                comps[i] = 1.0 if c > 0 else -1.0
        r = App.Vector(*comps)
        r.normalize()
        return r
    axis_global = snap_axis(axis_global)

    App.Console.PrintMessage(f"Schritt 4: Placement im lokalen KS des Zielteils berechnen\n")
    # 4. Placement2 im lokalen KS des Ziel-Links
    try:
        target_global_pl = get_global_placement(target_link)
        target_inv = target_global_pl.inverse()
        center_local = target_inv.multVec(center_global)
        axis_local   = target_inv.Rotation.multVec(axis_global)
        axis_local.normalize()

        def snap(v, tol=0.01):
            comps = [v.x, v.y, v.z]
            for i, c in enumerate(comps):
                if abs(abs(c) - 1.0) < tol:
                    comps[i] = 1.0 if c > 0 else -1.0
                elif abs(c) < tol:
                    comps[i] = 0.0
            return App.Vector(*comps)
        axis_local = snap(axis_local)
        p2 = App.Placement(center_local, App.Rotation())
    except Exception as e:
        App.Console.PrintError(f"schrauben_platzierung: Placement2 Fehler: {e}\n")
        return None

    App.Console.PrintMessage(f"Schritt 5: Schraube vorpositionieren\n")
    # 5. Weltposition und Rotation der Schraube
    # Body steht entlang +Z, Kopf bei Z=schrauben_laenge
    # Body-Ursprung liegt schrauben_laenge hinter dem Kopf (Kopfseite = axis_global)
    schrauben_laenge = p1.Base.z
    schraube_welt_pos = center_global - App.Vector(
        axis_global.x * schrauben_laenge,
        axis_global.y * schrauben_laenge,
        axis_global.z * schrauben_laenge)

    # Weltrotation: Body-Z zeigt in Richtung axis_global (Kopf→Spitze)
    body_z = App.Vector(0, 0, 1)
    if abs(body_z.dot(axis_global) - 1.0) < 1e-6:
        welt_rot = App.Rotation()
    elif abs(body_z.dot(axis_global) + 1.0) < 1e-6:
        welt_rot = App.Rotation(App.Vector(1, 0, 0), 180)
    else:
        welt_rot = App.Rotation(body_z, axis_global)

    # Zufällige Rotation um Schraubenachse (Schlitz-Orientierung)

    schraube_link = link_zu_assembly(assembly, body, body_label)
    schraube_link.Placement = App.Placement(schraube_welt_pos, welt_rot)

    App.Console.PrintMessage(f"Schritt 6: Fixed Joint anlegen\n")
    lcs_edge = lcs_attachment_edge_name(body, LCS_BOLT_NAME)
    r1_name = schraube_link.Label.replace(' ', '')
    r2_name = joint_ref2_link.Label.replace(' ', '')
    joint = fixed_joint_erstellen(
        assembly,
        ref1_link=schraube_link,   ref1_edge_name=lcs_edge,
        ref2_link=joint_ref2_link, ref2_edge_name=joint_ref2_edge_name,
        label=f"Fixed_{r1_name}_{r2_name}"
    )

    # Tatsächliche Achse nach recompute aus Schraube-Placement
    actual_pl = schraube_link.Placement
    actual_axis = actual_pl.Rotation.multVec(App.Vector(0, 0, 1))
    p1_local = lcs_placement_im_body(body, LCS_BOLT_NAME)
    lcs_welt = actual_pl.multVec(p1_local.Base) if p1_local else center_global

    # Schritt 6: Zufallsdrehung (optional)
    if zufaellig_drehen and joint is not None:
        import random as _random
        winkel = _random.choice(list(range(-90, 91, 10)))
        joint.Offset2 = App.Placement(
            App.Vector(0, 0, 0),
            App.Rotation(*[float(winkel), 0.0, 0.0]))
        joint.recompute()

    return joint, lcs_welt, actual_axis, schraube_link, lcs_edge, cog_unbekannt


def get_schrauben_doc():
    """Gibt das Schrauben-Dokument zurück, öffnet es falls nötig."""
    import os
    datei_name = os.path.basename(SCHRAUBEN_DATEI)
    for doc in App.listDocuments().values():
        if doc.FileName and os.path.basename(doc.FileName) == datei_name:
            return doc
    App.Console.PrintMessage(f"Öffne Schrauben-Datei: {SCHRAUBEN_DATEI}\n")
    try:
        return App.openDocument(SCHRAUBEN_DATEI, hidden=False)
    except Exception as e:
        raise RuntimeError(f"Schrauben-Datei konnte nicht geöffnet werden: {e}")


def get_mutter_body():
    """Gibt den Mutter-Body aus der Schrauben-Datei zurück."""
    import os
    datei_name = os.path.basename(SCHRAUBEN_DATEI)
    for doc in App.listDocuments().values():
        if doc.FileName and os.path.basename(doc.FileName) == datei_name:
            # Nach Body mit Label 'Mutter' suchen
            for obj in doc.Objects:
                if obj.Label == MUTTER_LABEL and obj.TypeId == 'PartDesign::Body':
                    return obj
            App.Console.PrintMessage(f"Mutter-Body '{MUTTER_LABEL}' nicht in {datei_name} gefunden.\n")
            return None
    App.Console.PrintMessage(f"Schrauben-Datei nicht geöffnet.\n")
    return None


def mutter_einfuegen_frei(assembly, body, body_label,
                          auflagen_link, auflagen_face, auflagen_face_name,
                          achse_ursprung, achse_richtung,
                          kreis_link=None, kreis_edge_name=None,
                          vorschau_link=None, zufaellig_drehen=False):
    """
    Fügt eine Mutter ein nach folgendem Algorithmus:
    E = achse_ursprung (Gewindeende = Kreismittelpunkt)
    M = Schnittpunkt Gewindeachse × Auflagefläche
    LCS_nut X-Achse zeigt von M in Richtung E (ins Gewinde).
    Offset im Joint = |E-M| entlang Achse.

    WICHTIG: Die Verdrehung um die Gewindeachse (Roll) wird über
    joint.Offset2 gesetzt, NICHT über mutter_link.Placement direkt!
    Der Fixed-Joint-Solver berechnet Placement1 aus Reference1/Reference2
    bei jedem recompute() neu und überschreibt dabei eine nur in Placement
    gesetzte Rotation kommentarlos (an der Konsole verifiziert). Offset2
    wird dagegen vom Solver respektiert und bleibt über recompute() hinweg
    erhalten - das ist der einzige Weg, zwei Muttern auf derselben
    Kreiskante (z.B. Kontermutter-Paar) unterschiedlich zu verdrehen.
    Gleiches Prinzip wie die 'Zufall'-Drehung bei der Schraube
    (siehe schraube_einfuegen, Schritt 6).
    """
    # Schritt 1: LCS_nut aus Mutter-Body
    linked = body
    while hasattr(linked, 'LinkedObject') and linked.LinkedObject:
        linked = linked.LinkedObject
    lcs_nut = None
    for obj in (linked.OutList if hasattr(linked, 'OutList') else []):
        if obj.Label == LCS_NUT_NAME or obj.Name == LCS_NUT_NAME:
            lcs_nut = obj
            break
    if lcs_nut is None:
        raise ValueError(f"'{LCS_NUT_NAME}' nicht im Mutter-Body gefunden.")
    lcs_nut_edge = lcs_attachment_edge_name(linked, LCS_NUT_NAME)
    if lcs_nut_edge is None:
        raise ValueError("LCS_nut Edge nicht gefunden.")

    # Schritt 2: Schnittpunkt M der Gewindeachse mit Auflagefläche
    M = schnittpunkt_achse_flaeche(achse_ursprung, achse_richtung, auflagen_face)
    if M is None:
        raise ValueError("Kein Schnittpunkt der Gewindeachse mit der Auflagefläche.\nAndere Fläche wählen.")
    App.Console.PrintMessage(f"Mutter: E={achse_ursprung}  M={M}\n")
    App.Console.PrintMessage(f"Mutter: Auflagefläche={auflagen_face_name} bei {auflagen_link.Label}\n")

    # Schritt 3: Richtungsvektor E→M und Offset
    vec_EM = M - achse_ursprung
    dist_EM = vec_EM.dot(achse_richtung)  # vorzeichenbehaftet entlang Achse
    App.Console.PrintMessage(f"Mutter: |E→M| entlang Achse = {dist_EM:.3f} mm\n")

    # Richtung M→E (LCS_nut X-Achse soll ins Gewinde zeigen)
    richtung_ME = achse_richtung * -1 if dist_EM > 0 else achse_richtung

    # Schritt 4: Vorpositionierung der Mutter
    # LCS_nut X-Achse auf richtung_ME ausrichten
    lcs_x_lokal = lcs_nut.Placement.Rotation.multVec(App.Vector(1, 0, 0))
    welt_rot = App.Rotation(lcs_x_lokal, richtung_ME)

    # Mutter so platzieren dass LCS_nut-Ursprung auf E liegt
    lcs_ursprung_welt = welt_rot.multVec(lcs_nut.Placement.Base)
    mutter_welt_pos   = achse_ursprung - lcs_ursprung_welt

    # Link anlegen oder Vorschau wiederverwenden
    if vorschau_link and hasattr(vorschau_link, 'Document'):
        mutter_link = vorschau_link
    else:
        mutter_link = link_zu_assembly(assembly, body, body_label)
    mutter_link.Placement = App.Placement(mutter_welt_pos, welt_rot)

    # Schritt 5: Fixed Joint anlegen
    # Reference1 = LCS_nut der Mutter
    # Reference2 = Kreiskante am Gewindeende
    # Offset2.Z  = dist_EM (verschiebt Mutter von E nach M)
    if kreis_link is None or kreis_edge_name is None:
        raise ValueError(f"Kreiskante fehlt: link={kreis_link} edge={kreis_edge_name}")
    r1_name = mutter_link.Label.replace(' ', '')
    r2_name = (kreis_link.Label if kreis_link else 'Ref').replace(' ', '')
    joint = fixed_joint_erstellen(
        assembly,
        ref1_link=mutter_link, ref1_edge_name=lcs_nut_edge,
        ref2_link=kreis_link,  ref2_edge_name=kreis_edge_name,
        label=f"Fixed_{r1_name}_{r2_name}"
    )

    if joint:
        winkel = 0.0
        if zufaellig_drehen:
            import random as _random
            # Wert innerhalb EINER 60°-Periode (6-zählige Symmetrie der
            # Sechskantmutter) -- Vielfache von 60° sehen alle identisch aus,
            # nur Werte DAZWISCHEN erzeugen eine sichtbar andere Orientierung.
            winkel = _random.uniform(1e-6, 60.0)
        joint.Offset2 = App.Placement(
            App.Vector(0, 0, dist_EM),
            App.Rotation(winkel, 0.0, 0.0))
        App.Console.PrintMessage(
            f"Mutter: Offset2.Z={dist_EM:.3f} mm  Offset2-Winkel={winkel:.1f}°\n")
        joint.recompute()

    App.Console.PrintMessage(f"Mutter: finale Position={mutter_link.Placement.Base}\n")
    App.Console.PrintMessage(f"Mutter: finale Rotation.Q={mutter_link.Placement.Rotation.Q}\n")

    return joint, mutter_link



def mutter_einfuegen(assembly, body, body_label,
                     target_link, face, face_name,
                     achse_ursprung, achse_richtung,
                     schraube_link, lcs_bolt_edge_name,
                     vorschau_link=None):
    """
    Fügt eine Mutter in die Assembly ein.
    Reference1 = LCS_nut der Mutter, Reference2 = LCS_bolt der Schraube.
    Offset = Abstand von LCS_bolt-Ursprung (Kopfauflagefläche) zur Mutter-Position.
    """
    # 1. Schnittpunkt Schraubenachse × Fläche = Mutter-Position
    mutter_pos = schnittpunkt_achse_flaeche(achse_ursprung, achse_richtung, face)
    if mutter_pos is None:
        try:
            dist, pts, _ = face.distToShape(
                Part.Line(achse_ursprung, achse_ursprung + achse_richtung).toShape(-1000, 1000))
            mutter_pos = pts[0][1]
        except Exception:
            raise ValueError("Kein Schnittpunkt der Schraubenachse mit der gewählten Fläche.")
    App.Console.PrintMessage(f"mutter_einfuegen: Mutter-Pos={mutter_pos}\n")

    # 2. Offset: Abstand von achse_ursprung (LCS_bolt-Welt) zu mutter_pos entlang der Achse
    vec = mutter_pos - achse_ursprung
    offset_dist = vec.dot(achse_richtung)
    App.Console.PrintMessage(f"  Offset entlang Achse: {offset_dist:.3f} mm\n")

    # 3. LCS_nut Placement aus dem Mutter-Body holen
    lcs_nut = None
    linked = body
    while hasattr(linked, 'LinkedObject') and linked.LinkedObject:
        linked = linked.LinkedObject
    for obj in (linked.OutList if hasattr(linked, 'OutList') else []):
        if obj.Label == LCS_NUT_NAME or obj.Name == LCS_NUT_NAME:
            lcs_nut = obj
            break
    if lcs_nut is None:
        raise ValueError(f"'{LCS_NUT_NAME}' nicht im Mutter-Body gefunden.")
    p_nut = lcs_nut.Placement

    # 4. Weltrotation: Body-Z zeigt in achse_richtung (gleichsinnig zur Schraube)
    body_z = App.Vector(0, 0, 1)
    if abs(body_z.dot(achse_richtung) - 1.0) < 1e-6:
        welt_rot = App.Rotation()
    elif abs(body_z.dot(achse_richtung) + 1.0) < 1e-6:
        welt_rot = App.Rotation(App.Vector(1, 0, 0), 180)
    else:
        welt_rot = App.Rotation(body_z, achse_richtung)

    # 5. Mutter-Ursprung positionieren
    lcs_ursprung_welt = welt_rot.multVec(p_nut.Base)
    mutter_welt_pos   = mutter_pos - lcs_ursprung_welt

    # 6. Vorschau-Link wiederverwenden oder neuen anlegen
    if vorschau_link and hasattr(vorschau_link, 'Document'):
        mutter_link = vorschau_link
        App.Console.PrintMessage(f"  Vorschau-Link wiederverwendet: {mutter_link.Name}\n")
    else:
        mutter_link = link_zu_assembly(assembly, body, body_label)
    mutter_link.Placement = App.Placement(mutter_welt_pos, welt_rot)

    # 7. LCS_nut-Edge für Reference1
    lcs_nut_edge = lcs_attachment_edge_name(linked, LCS_NUT_NAME)

    # 8. Fixed Joint: Mutter ↔ Schraube
    r1_name = mutter_link.Label.replace(' ', '')
    r2_name = schraube_link.Label.replace(' ', '')
    joint = fixed_joint_erstellen(
        assembly,
        ref1_link=mutter_link,   ref1_edge_name=lcs_nut_edge,
        ref2_link=schraube_link, ref2_edge_name=lcs_bolt_edge_name,
        label=f"Fixed_{r1_name}_{r2_name}"
    )

    # 9. Offset entlang Schraubenachse über Offset2.Z
    # Detach2 muss False bleiben – sonst ignoriert der Solver den Offset
    if joint and abs(offset_dist) > 1e-6:
        joint.Offset2 = App.Placement(
            App.Vector(0, 0, offset_dist),
            App.Rotation())
        joint.recompute()
        App.Console.PrintMessage(f"  Offset2.Z={offset_dist:.3f} mm\n")

    return joint



# ---------------------------------------------------------------------------
# Observer für Mutterauflagefläche
# ---------------------------------------------------------------------------

class _FlächeObserver:
    """Temporärer Observer – wartet auf eine Fläche, ruft dann Callback auf und stoppt."""
    def __init__(self, callback):
        self._callback = callback
        self._active   = False

    def start(self):
        if not self._active:
            Gui.Selection.addObserver(self)
            self._active = True

    def stop(self):
        if self._active:
            try:
                Gui.Selection.removeObserver(self)
            except Exception:
                pass
            self._active = False

    def addSelection(self, doc, obj, sub, pnt):
        active_doc = App.ActiveDocument
        if active_doc is None:
            return
        sel = Gui.Selection.getSelectionEx('', 0)
        for s in sel:
            for i, subname in enumerate(s.SubElementNames):
                if i >= len(s.SubObjects):
                    continue
                subobj = s.SubObjects[i]
                if subobj.ShapeType != 'Face':
                    continue
                parts    = subname.split('.')
                link_obj = active_doc.getObject(parts[0].strip()) or s.Object
                face_name = next(
                    (p for p in reversed(parts) if p.startswith('Face')), subname
                )
                self.stop()
                self._callback(link_obj, subobj, face_name)
                return

    def clearSelection(self, doc):
        pass


# ---------------------------------------------------------------------------
# Hauptdialog
# ---------------------------------------------------------------------------

class NutsAndBoltsDialog(QtWidgets.QDialog):

    def __init__(self, parent=None):
        super().__init__(parent, QtCore.Qt.Tool)
        self.setWindowTitle("Eitech – Schrauben & Muttern")
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)

        # Zustand Schraube
        self._aktiver_body     = None
        self._aktiver_label    = None
        self._ist_gewindestift = False
        self._letzter_lcs_bolt_edge  = None
        self._letzte_achse_ursprung  = None
        self._letzte_achse_richtung  = None

        # Zustand Mutter
        self._mutter_achse_orig    = None
        self._mutter_achse_richt   = None
        self._mutter_link_vorschau = None
        self._mutter_assembly      = None
        self._mutter_kreis_link    = None
        self._mutter_kreis_edge    = None
        self._obs_flaeche          = None

        # History für Undo
        self._history = []

        # Letzter Joint für Flip/Edit
        self._letzter_joint         = None
        self._letzter_schraube_link = None

        self._build_ui()

    # -----------------------------------------------------------------------
    # UI
    # -----------------------------------------------------------------------

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(6, 6, 6, 6)

        # --- Alle Buttons in einer Reihe ---
        row_btns = QtWidgets.QHBoxLayout()
        row_btns.setSpacing(2)
        self._schraube_btns = []

        for label, body_name, icon_name, ist_gewindestift in SCHRAUBEN:
            btn = QtWidgets.QPushButton()
            btn.setIcon(_icon(icon_name))
            btn.setIconSize(QtCore.QSize(44, 44))
            btn.setFixedSize(30, 54)
            btn.setToolTip(label)
            btn.setCheckable(True)
            btn.setStyleSheet(
                "QPushButton { padding: 0px; border: 1px solid #aaa; background: white; }"
                "QPushButton:checked { border: 2px solid #0066cc; background: #ddeeff; }"
            )
            btn.clicked.connect(lambda checked, l=label, b=body_name, g=ist_gewindestift:
                                self._on_schraube_btn(l, b, g))
            self._schraube_btns.append(btn)
            row_btns.addWidget(btn)

        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.VLine)
        sep.setFrameShadow(QtWidgets.QFrame.Sunken)
        row_btns.addWidget(sep)

        self._btn_mutter = QtWidgets.QPushButton()
        self._btn_mutter.setIcon(_icon("Mutter"))
        self._btn_mutter.setIconSize(QtCore.QSize(44, 44))
        self._btn_mutter.setFixedSize(30, 54)
        self._btn_mutter.setToolTip(
            "Mutter einfügen\n"
            "Schritt 1: Kreisfläche markieren, dann klicken\n"
            "Schritt 2: Auflagefläche markieren, dann klicken"
        )
        self._btn_mutter.setCheckable(True)
        self._btn_mutter.setStyleSheet(
            "QPushButton { padding: 0px; border: 1px solid #aaa; background: white; }"
            "QPushButton:checked { border: 2px solid #0066cc; background: #ddeeff; }"
        )
        self._btn_mutter.clicked.connect(self._on_mutter_btn)
        row_btns.addWidget(self._btn_mutter)
        row_btns.addStretch()
        layout.addLayout(row_btns)

        # --- Zweite Reihe: Optionen + Aktions-Buttons ---
        row2 = QtWidgets.QHBoxLayout()
        row2.setSpacing(3)

        self._cb_zufall = QtWidgets.QCheckBox("Zufall")
        self._cb_zufall.setToolTip("Zufällig drehen")
        self._cb_zufall.setChecked(True)
        row2.addWidget(self._cb_zufall)

        row2.addStretch()

        self._btn_flip = QtWidgets.QPushButton("↕")
        self._btn_flip.setToolTip("Letzte Schraube um 180° flippen")
        self._btn_flip.setFixedSize(28, 28)
        self._btn_flip.setEnabled(False)
        self._btn_flip.clicked.connect(self._on_flip)
        row2.addWidget(self._btn_flip)

        self._btn_edit = QtWidgets.QPushButton("✎")
        self._btn_edit.setToolTip("Letzten Joint editieren")
        self._btn_edit.setFixedSize(28, 28)
        self._btn_edit.setEnabled(False)
        self._btn_edit.clicked.connect(self._on_edit)
        row2.addWidget(self._btn_edit)

        self._btn_undo = QtWidgets.QPushButton("↩")
        self._btn_undo.setToolTip("Letzte Einfügung rückgängig")
        self._btn_undo.setFixedSize(28, 28)
        self._btn_undo.setEnabled(False)
        self._btn_undo.clicked.connect(self._on_undo)
        row2.addWidget(self._btn_undo)

        layout.addLayout(row2)

        # --- Statuszeile ---
        self._status = QtWidgets.QLabel(
            "Kreiskante markieren,\ndann Schraube oder Mutter\nButton drücken."
        )
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color: #555; font-style: italic; font-size: 10px;")
        self._status.setFixedWidth(200)
        self._status.setMinimumHeight(28)
        layout.addWidget(self._status)

        self.adjustSize()

    # -----------------------------------------------------------------------
    # Hilfsmethoden Selektion
    # -----------------------------------------------------------------------

    def _get_selektierte_kreiskante(self):
        """Gibt (link, edge, edge_name) zurück wenn Kreiskante selektiert."""
        try:
            sel = Gui.Selection.getSelectionEx('', 0)
            for s in sel:
                for i, subname in enumerate(s.SubElementNames):
                    if i >= len(s.SubObjects):
                        continue
                    subobj = s.SubObjects[i]
                    if hasattr(subobj, 'Curve') and isinstance(subobj.Curve, Part.Circle):
                        link_name = subname.split('.')[0].strip()
                        link = App.ActiveDocument.getObject(link_name) or s.Object
                        return link, subobj, subname
        except Exception as e:
            App.Console.PrintWarning(f"Selektion Kreiskante: {e}\n")
        return None

    def _get_selektierte_kreisflaeche(self):
        """Gibt (link, face, full_subname) zurück wenn planare Kreisfläche selektiert."""
        try:
            sel = Gui.Selection.getSelectionEx('', 0)
            for s in sel:
                for i, subname in enumerate(s.SubElementNames):
                    if i >= len(s.SubObjects):
                        continue
                    subobj = s.SubObjects[i]
                    if subobj.ShapeType != 'Face':
                        continue
                    edges = subobj.Edges
                    if len(edges) != 1:
                        continue
                    if not isinstance(edges[0].Curve, Part.Circle):
                        continue
                    if not isinstance(subobj.Surface, Part.Plane):
                        continue
                    link_name = subname.split('.')[0].strip()
                    link = App.ActiveDocument.getObject(link_name) or s.Object
                    return link, subobj, subname  # vollständiger SubElementName
        except Exception as e:
            App.Console.PrintWarning(f"Selektion Kreisfläche: {e}\n")
        return None

    def _get_selektierte_flaeche(self):
        """Gibt (link, face, face_name) zurück wenn irgendeine Fläche selektiert."""
        try:
            sel = Gui.Selection.getSelectionEx('', 0)
            for s in sel:
                for i, subname in enumerate(s.SubElementNames):
                    if i >= len(s.SubObjects):
                        continue
                    subobj = s.SubObjects[i]
                    if subobj.ShapeType == 'Face':
                        link_name = subname.split('.')[0].strip()
                        link = App.ActiveDocument.getObject(link_name) or s.Object
                        face_name = subname.split('.')[-1]
                        return link, subobj, face_name
        except Exception as e:
            App.Console.PrintWarning(f"Selektion Fläche: {e}\n")
        return None

    # -----------------------------------------------------------------------
    # Button-Handler: Schraube
    # -----------------------------------------------------------------------

    def _on_schraube_btn(self, label, body_name, ist_gewindestift):
        # Alle anderen Buttons deaktivieren
        for btn in self._schraube_btns:
            if btn.toolTip() != label:
                btn.setChecked(False)
        self._btn_mutter.setChecked(False)
        self._mutter_schritt = 0

        # Body laden
        self._set_status(f"Lade {label} …")
        try:
            doc = get_schrauben_doc()
        except Exception as e:
            self._set_status(f"Schrauben-Datei nicht gefunden: {e}", error=True)
            return

        body = doc.getObject(body_name)
        if body is None:
            self._set_status(f"Body '{body_name}' nicht gefunden.", error=True)
            return

        self._aktiver_body     = body
        self._aktiver_label    = label
        self._ist_gewindestift = ist_gewindestift

        # Assembly prüfen
        assembly = get_active_assembly()
        if assembly is None:
            self._set_status("Kein aktives Assembly.", error=True)
            for btn in self._schraube_btns:
                if btn.toolTip() == label:
                    btn.setChecked(False)
            return

        # Aktuelle Selektion prüfen
        kreiskante = self._get_selektierte_kreiskante()
        if kreiskante is None:
            self._set_status(f"{label}: keine Kreiskante selektiert.", error=True)
            # Button wieder deaktivieren
            for btn in self._schraube_btns:
                if btn.toolTip() == label:
                    btn.setChecked(False)
            return

        link, edge, edge_name = kreiskante
        self._set_status(f"Füge {label} ein …")
        self._schraube_einfuegen(assembly, link, edge, edge_name)

        # Button deaktivieren nach Einfügen
        for btn in self._schraube_btns:
            if btn.toolTip() == label:
                btn.setChecked(False)

    # -----------------------------------------------------------------------
    # Button-Handler: Mutter (zweistufig)
    # -----------------------------------------------------------------------

    def _on_mutter_btn(self):
        # Schrauben-Buttons deaktivieren
        for btn in self._schraube_btns:
            btn.setChecked(False)

        # Kreiskante oder Kreisfläche aus aktueller Selektion lesen
        kreiskante = self._get_selektierte_kreiskante()
        if kreiskante is None:
            kreisflaeche = self._get_selektierte_kreisflaeche()
            if kreisflaeche is not None:
                link, face, subname = kreisflaeche
                kante = face.Edges[0]
                # Vollständigen SubElementName behalten – FreeCAD löst Fläche→Kante auf
                kreiskante = (link, kante, subname)

        if kreiskante is None:
            self._set_status("Kreiskante oder Kreisfläche markieren, dann Mutter-Button drücken.", error=True)
            self._btn_mutter.setChecked(False)
            return

        assembly = get_active_assembly()
        if assembly is None:
            self._set_status("Kein aktives Assembly.", error=True)
            self._btn_mutter.setChecked(False)
            return

        mutter_body = get_mutter_body()
        if mutter_body is None:
            self._set_status("Mutter-Body nicht gefunden.", error=True)
            self._btn_mutter.setChecked(False)
            return

        link, edge, edge_name = kreiskante

        # Achse direkt aus Kreiskante
        self._mutter_achse_orig  = edge.Curve.Center
        self._mutter_achse_richt = edge.Curve.Axis
        self._mutter_achse_richt.normalize()
        self._mutter_assembly    = assembly
        App.Console.PrintMessage(
            f"Mutter: Gewindeende E={self._mutter_achse_orig}  "
            f"Achse={self._mutter_achse_richt}\n"
        )

        # kreis_link und kreis_edge_name aus der Selektion
        sel = Gui.Selection.getSelectionEx('', 0)
        self._mutter_kreis_link  = link  # kommt aus _get_selektierte_kreiskante/-flaeche
        self._mutter_kreis_edge  = edge_name
        for s in sel:
            for i, subname in enumerate(s.SubElementNames):
                if i >= len(s.SubObjects):
                    continue
                subobj = s.SubObjects[i]
                # Kreiskante direkt selektiert
                if hasattr(subobj, 'Curve') and isinstance(subobj.Curve, Part.Circle):
                    link_name = subname.split('.')[0].strip()
                    self._mutter_kreis_link = App.ActiveDocument.getObject(link_name) or s.Object
                    self._mutter_kreis_edge = subname
                    break
                # Kreisfläche selektiert
                if (subobj.ShapeType == 'Face' and len(subobj.Edges) == 1
                        and isinstance(subobj.Edges[0].Curve, Part.Circle)):
                    link_name = subname.split('.')[0].strip()
                    self._mutter_kreis_link = App.ActiveDocument.getObject(link_name) or s.Object
                    self._mutter_kreis_edge = subname
                    break
            if self._mutter_kreis_link is not link:
                break
        App.Console.PrintMessage(
            f"  Kreiskante: {self._mutter_kreis_edge}  "
            f"Link: {self._mutter_kreis_link.Label}\n"
        )

        # Mutter vorpositionieren (ohne Joint): LCS_nut-Ursprung auf E
        try:
            rot = App.Rotation(App.Vector(0, 0, 1), self._mutter_achse_richt)
        except Exception:
            rot = App.Rotation()
        self._mutter_link_vorschau = link_zu_assembly(assembly, mutter_body, MUTTER_LABEL)
        self._mutter_link_vorschau.Placement = App.Placement(self._mutter_achse_orig, rot)
        App.Console.PrintMessage(
            f"Mutter: Vorposition={self._mutter_link_vorschau.Placement.Base}\n"
        )

        # Observer für Auflagefläche starten
        self._obs_flaeche = _FlächeObserver(self._on_auflagenflaeche)
        self._obs_flaeche.start()
        self._btn_mutter.setChecked(True)
        self._set_status("Auflagefläche anklicken …")

    def _on_auflagenflaeche(self, auflagen_link, auflagen_face, auflagen_face_name):
        """Callback: Auflagefläche selektiert → Mutter endgültig einfügen."""
        self._btn_mutter.setChecked(False)
        self._set_status("Füge Mutter ein …")
        try:
            mutter_body = get_mutter_body()
            if mutter_body is None:
                self._set_status("Mutter-Body nicht gefunden.", error=True)
                self._mutter_aufraeuemen()
                return

            joint, mutter_link = mutter_einfuegen_frei(
                self._mutter_assembly,
                mutter_body,
                MUTTER_LABEL,
                auflagen_link, auflagen_face, auflagen_face_name,
                self._mutter_achse_orig,
                self._mutter_achse_richt,
                self._mutter_kreis_link,
                self._mutter_kreis_edge,
                vorschau_link=self._mutter_link_vorschau,
                zufaellig_drehen=self._cb_zufall.isChecked(),
            )
            if joint:
                self._letzter_joint = joint
                self._btn_edit.setEnabled(True)
                self._history.append(('mutter', mutter_link, joint))
                self._btn_undo.setEnabled(True)
                self._set_status("Mutter eingefügt.")
                Gui.Selection.clearSelection()
            else:
                self._set_status("Fehler beim Einfügen der Mutter.", error=True)
                self._mutter_aufraeuemen()
                return
        except Exception as e:
            msg = str(e)
            self._set_status(f"Mutter-Fehler: {msg}", error=True)
            App.Console.PrintError(f"mutter_einfuegen_frei: {msg}\n")
            if "Kein Schnittpunkt" in msg:
                # Selektion leeren damit Observer nicht sofort wieder feuert
                Gui.Selection.clearSelection()
                self._obs_flaeche = _FlächeObserver(self._on_auflagenflaeche)
                self._obs_flaeche.start()
                self._btn_mutter.setChecked(True)
                return
            self._mutter_aufraeuemen()
            return

        self._mutter_link_vorschau = None
        self._mutter_achse_orig    = None
        self._mutter_achse_richt   = None
        self._mutter_assembly      = None
        self._mutter_kreis_link    = None
        self._mutter_kreis_edge    = None

    def _mutter_aufraeuemen(self):
        """Vorschau-Mutter entfernen und Zustand zurücksetzen."""
        if self._mutter_link_vorschau is not None:
            try:
                App.ActiveDocument.removeObject(self._mutter_link_vorschau.Name)
                pass  # kein globales recompute
            except Exception:
                pass
        self._mutter_link_vorschau = None
        self._mutter_achse_orig    = None
        self._mutter_achse_richt   = None
        self._mutter_assembly      = None

    # -----------------------------------------------------------------------
    # Einfüge-Logik: Schraube
    # -----------------------------------------------------------------------

    def _schraube_einfuegen(self, assembly, link, edge, edge_name):
        # real_axis und real_center aus resolve=0 Selektion holen
        real_axis = None
        real_center = None
        raw_obj = link
        try:
            sel = Gui.Selection.getSelectionEx('', 0)
            for s in sel:
                for i, subname in enumerate(s.SubElementNames):
                    if i >= len(s.SubObjects):
                        continue
                    subobj = s.SubObjects[i]
                    if hasattr(subobj, 'Curve') and isinstance(subobj.Curve, Part.Circle):
                        real_axis   = subobj.Curve.Axis
                        real_center = subobj.Curve.Center
                        raw_obj     = s.Object
                        break
                if real_axis:
                    break
        except Exception:
            pass

        try:
            result = schraube_einfuegen(
                assembly,
                self._aktiver_body,
                self._aktiver_label,
                link, edge, edge_name, raw_obj,
                real_axis=real_axis,
                real_center=real_center,
                zufaellig_drehen=self._cb_zufall.isChecked(),
            )
            if result is None:
                self._set_status("Fehler beim Einfügen.", error=True)
                return
            joint, lcs_welt, achse_richt, schraube_link, lcs_edge, cog_unbekannt = result
        except Exception as e:
            self._set_status(f"Fehler: {e}", error=True)
            App.Console.PrintError(f"schraube_einfuegen: {e}\n")
            return

        self._letzter_joint         = joint
        self._letzter_schraube_link = schraube_link
        self._letzter_lcs_bolt_edge = lcs_edge
        self._letzte_achse_ursprung = lcs_welt
        self._letzte_achse_richtung = achse_richt
        self._btn_flip.setEnabled(True)
        self._btn_edit.setEnabled(True)
        self._history.append(('schraube', schraube_link, joint))
        self._btn_undo.setEnabled(True)
        self._set_status(f"{self._aktiver_label} eingefügt.")
        Gui.Selection.clearSelection()

    # -----------------------------------------------------------------------
    # Aktions-Buttons
    # -----------------------------------------------------------------------

    def _on_flip(self):
        if self._letzter_joint is None:
            return
        try:
            j = self._letzter_joint
            j.Proxy.flipOnePart(j)
            self._set_status("Schraube geflippt.")
        except Exception as e:
            self._set_status(f"Flip-Fehler: {e}", error=True)

    def _on_edit(self):
        if self._letzter_joint is None:
            return
        try:
            self._letzter_joint.ViewObject.doubleClicked()
        except Exception as e:
            self._set_status(f"Edit-Fehler: {e}", error=True)

    def _on_undo(self):
        if not self._history:
            return
        entry = self._history.pop()
        try:
            doc = App.ActiveDocument
            _, link, joint = entry
            doc.removeObject(joint.Name)
            doc.removeObject(link.Name)
            pass  # kein globales recompute
            self._letzter_joint = self._history[-1][2] if self._history else None
            self._btn_flip.setEnabled(self._letzter_joint is not None)
            self._btn_edit.setEnabled(self._letzter_joint is not None)
            self._btn_undo.setEnabled(bool(self._history))
            self._set_status("Rückgängig gemacht.")
        except Exception as e:
            self._set_status(f"Undo-Fehler: {e}", error=True)
            App.Console.PrintError(f"Undo: {e}\n")

    # -----------------------------------------------------------------------

    def _set_status(self, text, error=False):
        self._status.setText(text)
        color = "#aa0000" if error else "#555"
        self._status.setStyleSheet(f"color: {color}; font-style: italic; font-size: 10px;")
        if error:
            App.Console.PrintError(f"[nuts_and_bolts] {text}\n")
        else:
            App.Console.PrintMessage(f"[nuts_and_bolts] {text}\n")

    def closeEvent(self, event):
        if self._obs_flaeche is not None:
            self._obs_flaeche.stop()
        if self._mutter_link_vorschau is not None:
            try:
                App.ActiveDocument.removeObject(self._mutter_link_vorschau.Name)
                pass  # kein globales recompute
            except Exception:
                pass
        event.accept()



# ---------------------------------------------------------------------------
# Einstiegspunkt
# ---------------------------------------------------------------------------

_dialog = None

def main():
    global _dialog
    if _dialog is not None and _dialog.isVisible():
        _dialog.raise_()
        _dialog.activateWindow()
        return
    _dialog = NutsAndBoltsDialog(Gui.getMainWindow())
    _dialog.show()

main()
