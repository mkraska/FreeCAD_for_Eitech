# nuts_and_bolts.py  v0.4
# Eitech Workbench – Schrauben und Muttern in Assembly einfügen
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
    # Eindeutiger interner Name aus Label ableiten (Leerzeichen ersetzen)
    internal_name = label.replace(' ', '_').replace('ü','ue').replace('ä','ae').replace('ö','oe')
    item = assembly.newObject("App::Link", internal_name)
    item.LinkedObject = body
    item.Label = label
    App.ActiveDocument.recompute()
    return item


def fixed_joint_erstellen(assembly, ref1_link, ref1_edge_name,
                           ref2_link, ref2_edge_name,
                           label="StarrerVerbund"):
    """
    Legt einen Fixed Joint an. Detach=False, FreeCAD berechnet alles selbst.
    """
    doc = App.ActiveDocument

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

    # Erst recompute damit die Schraube im Dokument registriert ist
    doc.recompute()

    try:
        joint.Reference1 = (ref1_link, [ref1_edge_name, ref1_edge_name])
    except Exception as e:
        App.Console.PrintMessage(f"  Reference1 Fehler: {e}\n")
    try:
        joint.Reference2 = (ref2_link, [ref2_edge_name, ref2_edge_name])
    except Exception as e:
        App.Console.PrintMessage(f"  Reference2 Fehler: {e}\n")

    joint.Visibility = False
    doc.recompute()
    p1_after = joint.Placement1
    p2_after = joint.Placement2
    App.Console.PrintMessage(f"  Nach recompute: P1={p1_after.Base} Q1={p1_after.Rotation.Q}\n")
    App.Console.PrintMessage(f"                  P2={p2_after.Base} Q2={p2_after.Rotation.Q}\n")

    # Wenn FreeCAD eine ~180°-Rotation gewählt hat (|Q2.w| < 0.1 und |Q1.w| > 0.9)
    # dann hat FreeCAD die falsche Orientierung gewählt → invertieren
    q2w = p2_after.Rotation.Q[3]
    q1w = p1_after.Rotation.Q[3]
    if abs(q2w) < 0.1 and abs(q1w) > 0.9:
        App.Console.PrintMessage(f"  Q2 zeigt ~180°-Rotation (w={q2w:.3f}) → Joint invertieren\n")
        flip = App.Rotation(App.Vector(0, 1, 0), 180)
        joint.Detach1 = True
        p1c = joint.Placement1
        joint.Placement1 = App.Placement(p1c.Base, p1c.Rotation.multiply(flip))
        doc.recompute()
        App.Console.PrintMessage(f"  Nach Inversion: P1={joint.Placement1.Base} Q1={joint.Placement1.Rotation.Q}\n")
        App.Console.PrintMessage(f"                  P2={joint.Placement2.Base} Q2={joint.Placement2.Rotation.Q}\n")

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
        App.ActiveDocument.recompute()
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

        App.Console.PrintMessage(f"  Keine passende Fläche in ancestors\n")
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
    click_pos: 3D-Klickpunkt zur Bestimmung der Kopfseite.
    """
    # 1. LCS_bolt im Schrauben-Body auslesen
    try:
        p1 = lcs_placement_im_body(body, LCS_BOLT_NAME)
        App.Console.PrintMessage(f"  LCS_bolt Placement: P={p1.Base} Q={p1.Rotation.Q}\n")
    except ValueError as e:
        App.Console.PrintError(f"schrauben_platzierung: {e}\n")
        return None

    basis_rotation = p1.Rotation

    # 2. Kreisachse und Mittelpunkt in Weltkoordinaten
    # real_center kommt aus getSelectionEx('',0) → bereits in Weltkoordinaten
    if real_center is not None:
        center_global = App.Vector(real_center.x, real_center.y, real_center.z)
    else:
        # Fallback: lokalen Center mit Link-Placement transformieren
        link_pl = get_global_placement(target_link)
        center_global = link_pl.multVec(edge.Curve.Center)
    axis_global   = edge.Curve.Axis
    axis_global.normalize()
    App.Console.PrintMessage(f"  Edge.Curve.Axis (roh): {axis_global}\n")

    # Flächennormale der anliegenden ebenen Fläche bestimmen
    # (zeigt vom Material weg = Kopfseite)
    # 3. Schraubenachse = Kreisachse in Weltkoordinaten (aus resolve=0)
    if real_axis is not None:
        axis_global = App.Vector(real_axis.x, real_axis.y, real_axis.z)
        axis_global.normalize()
        App.Console.PrintMessage(f"  Edge.Curve.Axis (roh): {edge.Curve.Axis}\n")
        App.Console.PrintMessage(f"  real_axis (resolve=0): {axis_global}\n")
    else:
        axis_global = edge.Curve.Axis
        axis_global.normalize()
        App.Console.PrintMessage(f"  Edge.Curve.Axis (roh): {axis_global}\n")

    # Vorzeichen: Zylinder-CoG zeigt ins Material → axis_global soll entgegengesetzt zeigen
    import Part as P
    faces = raw_obj.Shape.ancestorsOfType(edge, P.Face)
    cog_vec = None
    # edge.Curve.Center und face.CenterOfGravity liegen beide im gleichen KS
    # (lokales KS von raw_obj) – kein Transformieren nötig
    center_local = edge.Curve.Center
    axis_local = edge.Curve.Axis
    axis_local.normalize()
    for face in faces:
        if isinstance(face.Surface, (P.Cylinder, P.Cone)):
            cog = face.CenterOfGravity
            cog_vec = cog - center_local
            App.Console.PrintMessage(f"  {type(face.Surface).__name__} R={getattr(face.Surface,'Radius',0):.2f} CoG={cog}  vec_to_cog={cog_vec}\n")
            break

    if cog_vec is not None and cog_vec.Length > 1e-6:
        dot_cog = cog_vec.dot(axis_local)
        App.Console.PrintMessage(f"  dot(cog, axis_local)={dot_cog:.4f}\n")
        if dot_cog > 0:
            axis_global = App.Vector(-axis_global.x, -axis_global.y, -axis_global.z)
            App.Console.PrintMessage(f"  axis_global umgedreht (CoG zeigt ins Material)\n")
    else:
        App.Console.PrintError(f"schrauben_platzierung: Kein Zylinder/Kegel an dieser Kante – kein Loch?\n")
        raise ValueError("Keine Lochleibung (Zylinder/Kegel) an dieser Kante gefunden.")

    App.Console.PrintMessage(f"  axis_global final: {axis_global}\n")

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
        App.Console.PrintMessage(f"  P2 lokal: {center_local}  axis_lokal (snap): {axis_local}\n")
        p2 = App.Placement(center_local, App.Rotation())
    except Exception as e:
        App.Console.PrintError(f"schrauben_platzierung: Placement2 Fehler: {e}\n")
        return None

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
    App.Console.PrintMessage(f"  axis_global={axis_global}  schrauben_laenge={schrauben_laenge}\n")
    App.Console.PrintMessage(f"  Schraube Weltpos: {schraube_welt_pos}  Rot.Q: {welt_rot.Q}\n")

    schraube_link = link_zu_assembly(assembly, body, body_label)
    schraube_link.Placement = App.Placement(schraube_welt_pos, welt_rot)

    # 6. Joint anlegen
    lcs_edge = lcs_attachment_edge_name(body, LCS_BOLT_NAME)
    App.Console.PrintMessage(f"  LCS_bolt Edge: {lcs_edge}\n")
    r1_name = target_link.Label.replace(' ', '')
    r2_name = schraube_link.Label.replace(' ', '')
    joint = fixed_joint_erstellen(
        assembly,
        ref1_link=target_link,   ref1_edge_name=edge_name,
        ref2_link=schraube_link, ref2_edge_name=lcs_edge,
        label=f"Fixed_{r1_name}_{r2_name}"
    )

    # Tatsächliche Achse nach recompute aus Schraube-Placement
    actual_pl = schraube_link.Placement
    actual_axis = actual_pl.Rotation.multVec(App.Vector(0, 0, 1))
    p1_local = lcs_placement_im_body(body, LCS_BOLT_NAME)
    lcs_welt = actual_pl.multVec(p1_local.Base) if p1_local else center_global
    App.Console.PrintMessage(f"  Tatsächliche Achse: {actual_axis}  LCS_bolt Welt: {lcs_welt}\n")

    # Prüfen ob LCS X-Achse ins Material zeigt (= gleiche Richtung wie cog_vec_welt)
    # cog_vec_welt wurde oben berechnet
    if cog_vec is not None:
        link_pl = get_global_placement(target_link)
        cog_vec_welt = link_pl.Rotation.multVec(cog_vec)
        lcs_x_welt = actual_pl.Rotation.multiply(p1_local.Rotation).multVec(App.Vector(1, 0, 0))
        dot_check = lcs_x_welt.dot(cog_vec_welt)
        App.Console.PrintMessage(f"  LCS X-Welt: {lcs_x_welt}  dot mit CoG: {dot_check:.4f}\n")
        if dot_check < 0:
            flip_achse = actual_axis.cross(App.Vector(0, 1, 0))
            if flip_achse.Length < 1e-6:
                flip_achse = actual_axis.cross(App.Vector(1, 0, 0))
            flip = App.Rotation(flip_achse, 180)
            schraube_link.Placement = App.Placement(
                schraube_link.Placement.Base,
                flip.multiply(schraube_link.Placement.Rotation))
            assembly.Document.recompute()
            actual_pl = schraube_link.Placement
            actual_axis = actual_pl.Rotation.multVec(App.Vector(0, 0, 1))
            lcs_welt = actual_pl.multVec(p1_local.Base)
            App.Console.PrintMessage(f"  Nach Flip: Achse={actual_axis}  LCS_bolt Welt={lcs_welt}\n")

    # Zufallsdrehung um Schraubenachse über Offset2 des Joints (Schraube=Reference2)
    if zufaellig_drehen and joint is not None:
        import random as _random
        winkel = _random.choice(list(range(-90, 91, 10)))
        joint.Offset2 = App.Placement(
            App.Vector(0, 0, 0),
            App.Rotation(*[float(winkel), 0.0, 0.0]))
        assembly.Document.recompute()
        App.Console.PrintMessage(f"  Zufallsdrehung: {winkel}°\n")

    return joint, lcs_welt, actual_axis, schraube_link, lcs_edge


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
    App.Console.PrintMessage(f"  Mutter Weltpos: {mutter_welt_pos}  Rot.Q: {welt_rot.Q}\n")

    # 6. Vorschau-Link wiederverwenden oder neuen anlegen
    if vorschau_link and hasattr(vorschau_link, 'Document'):
        mutter_link = vorschau_link
        App.Console.PrintMessage(f"  Vorschau-Link wiederverwendet: {mutter_link.Name}\n")
    else:
        mutter_link = link_zu_assembly(assembly, body, body_label)
    mutter_link.Placement = App.Placement(mutter_welt_pos, welt_rot)

    # 7. LCS_nut-Edge für Reference1
    lcs_nut_edge = lcs_attachment_edge_name(linked, LCS_NUT_NAME)
    App.Console.PrintMessage(f"  LCS_nut Edge: {lcs_nut_edge}\n")

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
        assembly.Document.recompute()
        App.Console.PrintMessage(f"  Offset2.Z={offset_dist:.3f} mm\n")

    return joint


# ---------------------------------------------------------------------------
class SchraubenDialog(QtWidgets.QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Schrauben platzieren")
        self.setWindowFlags(
            QtCore.Qt.Window |
            QtCore.Qt.WindowStaysOnTopHint |
            QtCore.Qt.WindowCloseButtonHint
        )
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, False)
        self.resize(280, 400)

        self._letzter_joint         = None
        self._letzter_mutter_joint  = None
        self._letzter_schraube_link = None
        self._letzter_lcs_bolt_edge = None
        self._letzte_achse_ursprung = None
        self._letzte_achse_richtung = None
        self._modus = 'schraube'  # 'schraube' | 'warte_schraube_fuer_mutter' | 'warte_flaeche'
        self._warte_auf_flaeche = False  # Kompatibilität
        self._warte_auf_kante   = False
        self._gewaehlter_body   = None
        self._gewaehlter_label  = None
        self._observer          = None
        self._einfuegen_aktiv   = False
        self._einfuegen_aktiv  = False  # Re-Entrant-Schutz

        self._build_ui()
        self._start_observer()
        self._schrauben_doc_laden()

    def _schrauben_doc_laden(self):
        """Stellt sicher dass die Schrauben-Datei vollständig geladen ist."""
        import os
        schrauben_doc = None
        datei_name = os.path.basename(SCHRAUBEN_DATEI)
        for d in App.listDocuments().values():
            if d.FileName and os.path.basename(d.FileName) == datei_name:
                schrauben_doc = d
                break
        if schrauben_doc is None:
            try:
                App.Console.PrintMessage(f"schrauben_platzierung: Lade {SCHRAUBEN_DATEI}\n")
                schrauben_doc = App.openDocument(SCHRAUBEN_DATEI, hidden=False)
            except Exception as e:
                self._set_status(f"Fehler: Schrauben-Datei nicht gefunden.\n{e}", error=True)
                return
        schrauben_doc.recompute()
        # Ersten Button auslösen damit Body gesetzt wird
        if self._schrauben_btns:
            self._schrauben_btns[0].clicked.emit()

    # --- UI aufbauen --------------------------------------------------------

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        # Schrauben-Knöpfe
        layout.addWidget(QtWidgets.QLabel("Schraube wählen:"))
        self._btn_gruppe = QtWidgets.QButtonGroup(self)
        self._btn_gruppe.setExclusive(True)

        self._schrauben_btns = []
        first_btn = None
        for label, body_name in SCHRAUBEN_BODIES.items():
            btn = QtWidgets.QPushButton(label)
            btn.setCheckable(True)
            btn.setProperty("body_name",  body_name)
            btn.setProperty("body_label", label)
            self._btn_gruppe.addButton(btn)
            self._schrauben_btns.append(btn)
            layout.addWidget(btn)
            btn.clicked.connect(self._on_schraube_gewaehlt)
            if first_btn is None:
                first_btn = btn

        # Ersten Button direkt auswählen (emit nach doc-laden in _schrauben_doc_laden)
        if first_btn is not None:
            first_btn.setChecked(True)

        layout.addSpacing(8)

        # Mutter zu bestehender Schraube
        self._btn_mutter_zu_schraube = QtWidgets.QPushButton("Mutter zu Schraube …")
        self._btn_mutter_zu_schraube.setToolTip("Schraube anklicken → Vorschau → Fläche anklicken")
        self._btn_mutter_zu_schraube.setCheckable(True)
        self._btn_mutter_zu_schraube.clicked.connect(self._on_mutter_zu_schraube)
        layout.addWidget(self._btn_mutter_zu_schraube)

        layout.addSpacing(8)

        # Optionen
        self._cb_zufall = QtWidgets.QCheckBox("Zufällig drehen")
        self._cb_zufall.setChecked(True)
        layout.addWidget(self._cb_zufall)

        self._cb_mutter = QtWidgets.QCheckBox("Mutter automatisch einfügen")
        self._cb_mutter.stateChanged.connect(self._on_mutter_checkbox)
        layout.addWidget(self._cb_mutter)

        layout.addSpacing(8)

        # Nachjustieren
        btn_nachj_schraube = QtWidgets.QPushButton("Nachjustieren Schraube …")
        btn_nachj_schraube.clicked.connect(self._on_nachjustieren_schraube)
        layout.addWidget(btn_nachj_schraube)

        btn_nachj_mutter = QtWidgets.QPushButton("Nachjustieren Mutter …")
        btn_nachj_mutter.clicked.connect(self._on_nachjustieren_mutter)
        layout.addWidget(btn_nachj_mutter)

        layout.addStretch()

        # Statuszeile
        self._status = QtWidgets.QLabel("Schraube wählen, dann Lochrand anklicken.")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color: #555; font-style: italic;")
        layout.addWidget(self._status)

    # --- SelectionObserver --------------------------------------------------

    def _start_observer(self):
        dialog = self
        assembly_doc_name = None
        asm = get_active_assembly()
        if asm:
            assembly_doc_name = asm.Document.Name

        class Observer:
            def addSelection(self, doc, obj, sub, pnt):
                # Bei verschachtelten Assemblies kommen mehrere Events –
                # wir verzögern und nehmen beim Callback den besten
                QtCore.QTimer.singleShot(
                    200,
                    lambda: dialog._on_selection_delayed(doc, obj, sub, pnt)
                )

        self._observer = Observer()
        Gui.Selection.addObserver(self._observer)
        _register_observer(self._observer)

    def _stop_observer(self):
        if self._observer:
            Gui.Selection.removeObserver(self._observer)
            _unregister_observer(self._observer)
            self._observer = None

    def closeEvent(self, event):
        self._stop_observer()
        super().closeEvent(event)

    # --- Selektion verarbeiten ----------------------------------------------

    def _on_selection_delayed(self, doc, obj_name, sub, pnt):
        """Verzögert aufgerufen – holt sub mit vollem Pfad über resolve=0."""
        real_sub = sub
        real_axis = None
        real_center = None
        try:
            sel = Gui.Selection.getSelectionEx('', 0)
            for s in sel:
                if not s.SubElementNames:
                    continue
                full = s.SubElementNames[0]
                clean = full.split(';')[0]  # z.B. 'Fahrgestell.Platte_3_x_5.Pad002.Edge42'
                if '.' in clean:
                    real_sub = clean + sub if not clean.endswith(sub) else clean.rstrip('.')
                    # Edge-Name aus original sub anhängen wenn nicht schon drin
                    if sub and not real_sub.endswith(sub):
                        real_sub = clean + sub
                    if s.SubObjects:
                        e = s.SubObjects[0]
                        if hasattr(e, 'Curve') and hasattr(e.Curve, 'Axis'):
                            real_axis   = e.Curve.Axis
                            real_center = e.Curve.Center
                    App.Console.PrintMessage(f"  sub resolved: '{sub}' → '{real_sub}'\n")
                    if real_axis:
                        App.Console.PrintMessage(f"  Kreisachse (resolve=0): {real_axis}\n")
                    break
        except Exception as e:
            App.Console.PrintMessage(f"  resolve Fehler: {e}\n")
        self._on_selection(doc, obj_name, real_sub, pnt, real_axis, real_center)

    def _on_selection(self, doc, obj_name, sub, pnt, real_axis=None, real_center=None):
        """Wird bei jeder Selektion aufgerufen."""
        if self._gewaehlter_body is None:
            return
        if self._einfuegen_aktiv:
            return

        # Modus: auf Schraube warten für Mutter
        if self._modus == 'warte_schraube_fuer_mutter':
            # Wenn ein Lochrand angeklickt wird → Schraube einfügen (Mutter folgt automatisch)
            result = get_selected_circular_edge()
            if result is not None:
                self._modus = 'schraube'  # zurücksetzen damit normale Verarbeitung greift
            else:
                self._on_schraube_fuer_mutter_angeklickt(obj_name, sub, pnt)
                return

        # Modus: auf Fläche warten für Mutter-Positionierung
        if self._modus == 'warte_flaeche':
            # Nur Flächen akzeptieren (Face), keine Kanten (Edge)
            sub_element = sub.split('.')[-1] if sub and '.' in sub else sub
            if sub_element and sub_element.startswith('Face'):
                self._on_flaeche_fuer_mutter_angeklickt(obj_name, sub, pnt)
            else:
                self._set_status("Bitte eine Fläche anklicken (kein Lochrand).", error=True)
            return

        # Modus: Schraube einfügen – auf Kreiskante warten
        result = get_selected_circular_edge()
        if result is None:
            if self._gewaehlter_body is not None:
                self._set_status(
                    f"{self._gewaehlter_label} gewählt.\n"
                    "Bitte einen Lochrand (Kreiskante) anklicken.")
            return

        raw_obj, edge, edge_name = result
        App.Console.PrintMessage(f"Selection: doc={doc} obj={obj_name} sub={sub} TypeId={getattr(raw_obj,'TypeId','?')}\n")
        App.Console.PrintMessage(f"  Klickpunkt: {pnt}\n")
        try:
            App.Console.PrintMessage(f"  Edge.Curve.Center={edge.Curve.Center}  Edge.Curve.Axis={edge.Curve.Axis}\n")
        except Exception:
            pass

        assembly = get_active_assembly()
        if assembly is None:
            self._set_status("Kein aktives Assembly gefunden.", error=True)
            return

        # Link-Name = erster Teil des sub-Strings
        link_obj = None
        joint_edge_name = edge_name
        if sub and '.' in sub:
            parts = sub.split('.')
            link_name = parts[0]
            candidate = assembly.Document.getObject(link_name)
            if candidate and candidate.TypeId in ("App::Link", "Assembly::AssemblyLink"):
                link_obj = candidate
                joint_edge_name = '.'.join(parts[1:]) if len(parts) > 1 else edge_name
                App.Console.PrintMessage(f"  → Link: {link_obj.Name} / {link_obj.Label}  joint_edge='{joint_edge_name}'\n")
            else:
                self._set_status(
                    f"'{link_name}' ist kein direktes Bauteil der aktiven Assembly.\n"
                    "Bitte zuerst die Assembly aktivieren, die dieses Teil enthält.",
                    error=True)
                return

        if link_obj is None:
            App.Console.PrintMessage(f"  → sub='{sub}' ohne Präfix, suche per Klickpunkt\n")
            click_pos = App.Vector(pnt[0], pnt[1], pnt[2]) if pnt else None
            link_obj = find_link_in_assembly(assembly, raw_obj, click_pos)
            if link_obj:
                App.Console.PrintMessage(f"  → Link per Fallback: {link_obj.Name} / {link_obj.Label}\n")

        if link_obj is None:
            self._set_status(
                "Bauteil nicht erkannt.\nBitte Lochrand nochmal anklicken.",
                error=True)
            return

        click_pos = App.Vector(pnt[0], pnt[1], pnt[2]) if pnt else None
        self._schraube_einfuegen_jetzt(link_obj, edge, joint_edge_name, raw_obj, click_pos, real_axis, real_center)

    def _on_schraube_fuer_mutter_angeklickt(self, obj_name, sub, pnt):
        """Im Modus 'warte_schraube_fuer_mutter': prüft ob eine Schraube angeklickt wurde."""
        assembly = get_active_assembly()
        if assembly is None:
            return
        # Link-Name aus sub
        if not (sub and '.' in sub):
            return
        link_name = sub.split('.')[0]
        link_obj = assembly.Document.getObject(link_name)
        if link_obj is None:
            return
        # Prüfen ob der Link auf einen Schrauben-Body zeigt (hat LCS_bolt)
        linked = link_obj.LinkedObject if hasattr(link_obj, 'LinkedObject') else None
        while linked and hasattr(linked, 'LinkedObject') and linked.LinkedObject:
            linked = linked.LinkedObject
        if linked is None:
            return
        # Schraube erkennen: hat LCS_bolt UND ist in Schrauben-Dokument
        hat_lcs_bolt = any(
            obj.Label == LCS_BOLT_NAME or obj.Name == LCS_BOLT_NAME
            for obj in (linked.OutList if hasattr(linked, 'OutList') else [])
        )
        if not hat_lcs_bolt:
            self._set_status("Bitte eine Schraube anklicken.", error=True)
            return

        App.Console.PrintMessage(f"Schraube für Mutter: {link_obj.Name}\n")

        # Achse aus Schraube rekonstruieren
        lcs_edge = lcs_attachment_edge_name(linked, LCS_BOLT_NAME)
        p1 = lcs_placement_im_body(linked, LCS_BOLT_NAME)
        if p1 is None:
            self._set_status("LCS_bolt nicht gefunden.", error=True)
            return

        # Weltposition und Achse wie beim normalen Workflow:
        # actual_axis = Body-Z in Weltkoordinaten (zeigt aus dem Material)
        link_pl = link_obj.Placement
        actual_axis = link_pl.Rotation.multVec(App.Vector(0, 0, 1))
        lcs_ursprung = link_pl.multVec(p1.Base)

        self._letzter_schraube_link = link_obj
        self._letzter_lcs_bolt_edge = lcs_edge
        self._letzte_achse_ursprung = lcs_ursprung
        self._letzte_achse_richtung = actual_axis

        App.Console.PrintMessage(
            f"Mutter zu Schraube: {link_obj.Label}\n"
            f"  LCS Ursprung Welt: {lcs_ursprung}\n"
            f"  Achse Welt (actual_axis): {actual_axis}\n")

        self._mutter_vorschau()

    def _on_flaeche_fuer_mutter_angeklickt(self, obj_name, sub, pnt):
        """Im Modus 'warte_flaeche': Fläche auswerten und Mutter endgültig platzieren."""
        assembly = get_active_assembly()
        if assembly is None:
            return

        # Fläche direkt aus getSelectionEx holen (noch aktiv im delayed callback)
        face = None
        face_name = None
        target_link = None

        sel = Gui.Selection.getSelectionEx('', 0)
        for s in sel:
            for sn, so in zip(s.SubElementNames, s.SubObjects):
                clean = sn.split(';')[0]
                if isinstance(so, Part.Face):
                    face = so
                    # face_name = letzter Teil des sub-Pfads
                    clean_sub = sub.split(';')[0] if sub else sn
                    face_name = clean_sub.split('.')[-1] if '.' in clean_sub else sn
                    # Link aus sub bestimmen
                    if '.' in clean_sub:
                        link_name = clean_sub.split('.')[0]
                        target_link = assembly.Document.getObject(link_name)
                    break
            if face:
                break

        # Fallback: aus sub-Parameter
        if face is None and sub and '.' in sub:
            link_name = sub.split('.')[0]
            target_link = assembly.Document.getObject(link_name)
            face_name = sub.split('.')[-1]
            App.Console.PrintMessage(f"  Fläche-Fallback: link={link_name} face={face_name}\n")

        if target_link is None:
            self._set_status("Bitte eine Fläche anklicken.", error=True)
            return

        # Joints und Assembly-Objekte nicht als Fläche akzeptieren
        if target_link.TypeId in ('Assembly::JointGroup', 'App::DocumentObjectGroup'):
            self._set_status("Bitte eine Bauteilfläche anklicken, nicht einen Joint.", error=True)
            return

        App.Console.PrintMessage(f"  Fläche erkannt: {face_name} auf {target_link.Name}\n")

        # Vorschau-Link sichern bevor er auf None gesetzt wird
        self._mutter_vorschau_link_gesichert = getattr(self, '_mutter_vorschau_link', None)
        self._mutter_vorschau_link = None  # nicht entfernen, wird wiederverwendet
        # Modus zurücksetzen: bei "Mutter zu Schraube" wieder auf warte_schraube
        naechster_modus = 'warte_schraube_fuer_mutter' if getattr(self, '_mutter_zu_schraube_aktiv', False) else 'schraube'
        self._modus = naechster_modus
        self._mutter_einfuegen_jetzt(target_link, face, face_name)

    MUTTER_VORSCHAU_ABSTAND = 2.0  # mm Abstand vom Schraubenende

    def _mutter_vorschau(self):
        """Platziert die Mutter als Vorschau am Schraubenende + 2mm Abstand."""
        if self._letzte_achse_ursprung is None:
            return

        mutter_body = get_mutter_body()
        if mutter_body is None:
            self._set_status(f"Mutter-Body '{MUTTER_LABEL}' nicht gefunden.", error=True)
            self._modus = 'schraube'
            return

        assembly = get_active_assembly()
        if assembly is None:
            return

        # Schraubenlänge aus LCS_bolt
        p1 = lcs_placement_im_body(
            self._letzter_schraube_link.LinkedObject if hasattr(self._letzter_schraube_link, 'LinkedObject')
            else self._letzter_schraube_link,
            LCS_BOLT_NAME)
        schrauben_laenge = p1.Base.z if p1 else 6.0

        # Vorschau-Position: am Schraubenende (Spitzenseite) + Abstand
        # axis_global zeigt vom Loch weg (Kopfseite) → Spitze ist -axis_global
        achse = self._letzte_achse_richtung
        vorschau_pos = (self._letzte_achse_ursprung
                        - App.Vector(achse.x, achse.y, achse.z) * (schrauben_laenge + self.MUTTER_VORSCHAU_ABSTAND))

        # Rotation wie Schraube
        body_z = App.Vector(0, 0, 1)
        if abs(body_z.dot(achse) - 1.0) < 1e-6:
            welt_rot = App.Rotation()
        elif abs(body_z.dot(achse) + 1.0) < 1e-6:
            welt_rot = App.Rotation(App.Vector(1, 0, 0), 180)
        else:
            welt_rot = App.Rotation(body_z, achse)

        # LCS_nut Offset
        linked = mutter_body
        while hasattr(linked, 'LinkedObject') and linked.LinkedObject:
            linked = linked.LinkedObject
        p_nut = None
        for obj in (linked.OutList if hasattr(linked, 'OutList') else []):
            if obj.Label == LCS_NUT_NAME or obj.Name == LCS_NUT_NAME:
                p_nut = obj.Placement
                break
        if p_nut:
            lcs_ursprung_welt = welt_rot.multVec(p_nut.Base)
            vorschau_pos = vorschau_pos - lcs_ursprung_welt

        App.Console.PrintMessage(
            f"  Vorschau: pos={vorschau_pos}  achse={achse}  laenge={schrauben_laenge}\n")

        # Vorschau-Link anlegen (kein Joint)
        mutter_link = link_zu_assembly(assembly, mutter_body, MUTTER_LABEL)
        mutter_link.Placement = App.Placement(vorschau_pos, welt_rot)
        self._mutter_vorschau_link = mutter_link

        self._modus = 'warte_flaeche'
        self._set_status("Mutter-Vorschau gesetzt.\nBitte Fläche für Mutter anklicken …")

    def _mutter_vorschau_entfernen(self):
        """Entfernt die Vorschau-Mutter ohne Joint."""
        if hasattr(self, '_mutter_vorschau_link') and self._mutter_vorschau_link:
            try:
                obj = self._mutter_vorschau_link
                # Nur entfernen wenn kein Joint darauf zeigt
                if not obj.InList:
                    doc = obj.Document
                    doc.removeObject(obj.Name)
                    doc.recompute()
                else:
                    App.Console.PrintMessage(f"  Vorschau-Mutter hat InList – nicht entfernt\n")
            except Exception as e:
                App.Console.PrintMessage(f"  Vorschau entfernen Fehler: {e}\n")
            self._mutter_vorschau_link = None

    def _on_mutter_zu_schraube(self):
        """Startet den Mutter-Workflow für eine bereits eingefügte Schraube."""
        # Schraube-Buttons deselektieren
        for btn in self._schrauben_btns:
            btn.setChecked(False)
        self._modus = 'warte_schraube_fuer_mutter'
        self._mutter_zu_schraube_aktiv = True
        self._btn_mutter_zu_schraube.setChecked(True)
        self._btn_mutter_zu_schraube.setStyleSheet(
            "QPushButton { background-color: #0066cc; color: white; "
            "font-weight: bold; border: 2px solid #004499; padding: 4px; }")
        self._set_status("Schraube anklicken …")

    def _on_mutter_checkbox(self, state):
        if state == 2:  # Checked
            if self._letzter_schraube_link is None:
                self._modus = 'warte_schraube_fuer_mutter'
                self._set_status("Bitte eine bereits gesetzte Schraube anklicken …")
            elif self._letzte_achse_ursprung is not None:
                self._mutter_vorschau()
        else:
            self._mutter_vorschau_entfernen()
            self._modus = 'schraube'
            if self._gewaehlter_label:
                self._set_status(f"{self._gewaehlter_label} gewählt.\nLochrand anklicken …")

    def _on_schraube_gewaehlt(self):
        btn = self._btn_gruppe.checkedButton()
        if btn is None:
            return
        body_name  = btn.property("body_name")
        body_label = btn.property("body_label")

        self._highlight_active_btn(btn)
        self._mutter_zu_schraube_aktiv = False
        if hasattr(self, '_btn_mutter_zu_schraube'):
            self._btn_mutter_zu_schraube.setChecked(False)
            self._btn_mutter_zu_schraube.setStyleSheet("")

        # Mutter-Checkbox für Gewindestift deaktivieren
        ist_gewindestift = (body_label == "Gewindestift")
        self._cb_mutter.setEnabled(not ist_gewindestift)
        if ist_gewindestift:
            self._cb_mutter.setChecked(False)

        # Body aus Schrauben-Dokument holen (muss geöffnet sein)
        schrauben_doc = None
        for d in App.listDocuments().values():
            if SCHRAUBEN_DATEI.endswith(d.FileName.replace("/", "\\")):
                schrauben_doc = d
                break
            if d.FileName and d.FileName.split("\\")[-1] == SCHRAUBEN_DATEI.split("\\")[-1]:
                schrauben_doc = d
                break

        if schrauben_doc is None:
            # Versuchen zu öffnen (hidden=False = vollständig laden)
            try:
                schrauben_doc = App.openDocument(SCHRAUBEN_DATEI, hidden=False)
            except Exception as e:
                self._set_status(f"Fehler: Schrauben-Datei nicht gefunden.\n{e}", error=True)
                return

        body = schrauben_doc.getObject(body_name)
        if body is None:
            # Fallback: per Label suchen
            for obj in schrauben_doc.Objects:
                if obj.Label == body_label:
                    body = obj
                    break
        if body is None:
            self._set_status(f"Body '{body_name}' (Label: '{body_label}') nicht in Schrauben-Datei.", error=True)
            App.Console.PrintError(f"Verfügbare Objekte: {[o.Name+'/'+o.Label for o in schrauben_doc.Objects]}\n")
            return

        App.Console.PrintMessage(f"Schraube gewählt: Name={body.Name} Label={body.Label}\n")

        self._gewaehlter_body  = body
        self._gewaehlter_label = body_label

        # Assembly jetzt prüfen
        assembly = get_active_assembly()
        if assembly is None:
            QtWidgets.QMessageBox.critical(
                self,
                "Kein Assembly aktiv",
                "Bitte zuerst das Assembly-Dokument aktivieren\n"
                "(Fenster anklicken oder in der Dokumentenliste auswählen)."
            )
            self._gewaehlter_body = None
            # Knopf-Auswahl zurücksetzen
            self._highlight_active_btn(None)
            checked = self._btn_gruppe.checkedButton()
            if checked:
                checked.setChecked(False)
            self._set_status("Schraube wählen, dann Lochrand anklicken.")
            return

        self._set_status(
            f"{body_label} gewählt.\n"
            f"Assembly: {assembly.Document.Label}\n"
            "Bitte Lochrand anklicken …")

    # --- Einfügen -----------------------------------------------------------

    def _schraube_einfuegen_jetzt(self, target_link, edge, edge_name, raw_obj, click_pos=None, real_axis=None, real_center=None):
        self._mutter_zu_schraube_aktiv = False
        if hasattr(self, '_btn_mutter_zu_schraube'):
            self._btn_mutter_zu_schraube.setChecked(False)
            self._btn_mutter_zu_schraube.setStyleSheet("")
        App.Console.PrintMessage(
            f"Optionen: Zufällig={self._cb_zufall.isChecked()} "
            f"Mutter={self._cb_mutter.isChecked()}\n")
        assembly = get_active_assembly()
        if assembly is None:
            self._set_status("Kein aktives Assembly gefunden.", error=True)
            return

        self._einfuegen_aktiv = True
        self._set_status(f"Füge {self._gewaehlter_label} ein …")

        try:
            result = schraube_einfuegen(
                assembly,
                self._gewaehlter_body,
                self._gewaehlter_label,
                target_link, edge, edge_name, raw_obj,
                click_pos=click_pos,
                real_axis=real_axis,
                real_center=real_center,
                zufaellig_drehen=self._cb_zufall.isChecked()
            )
            joint, center_global, axis_global, schraube_link, lcs_bolt_edge = result
        except ValueError as e:
            self._set_status(str(e), error=True)
            joint = schraube_link = lcs_bolt_edge = None
            center_global = axis_global = None
        finally:
            self._einfuegen_aktiv = False

        if joint is None:
            self._set_status("Fehler beim Einfügen.", error=True)
            return

        self._letzter_joint         = joint
        self._letzter_schraube_link = schraube_link
        self._letzter_lcs_bolt_edge = lcs_bolt_edge
        self._letzte_achse_ursprung = center_global
        self._letzte_achse_richtung = axis_global

        if self._cb_mutter.isChecked():
            self._mutter_vorschau()
        else:
            self._set_status(f"{self._gewaehlter_label} eingefügt.\nNächsten Lochrand anklicken …")

    def _mutter_einfuegen_jetzt(self, target_link, face, face_name):
        """Mutter auf der angeklickten Fläche einfügen."""
        self._warte_auf_flaeche = False

        if self._letzte_achse_ursprung is None or self._letzter_schraube_link is None:
            self._set_status("Keine Schraube bekannt.\nBitte zuerst eine Schraube einfügen.", error=True)
            return

        assembly = get_active_assembly()
        if assembly is None:
            self._set_status("Kein aktives Assembly gefunden.", error=True)
            return

        mutter_body = get_mutter_body()
        if mutter_body is None:
            self._set_status(f"Mutter-Body '{MUTTER_LABEL}' nicht gefunden.", error=True)
            return

        try:
            vorschau = getattr(self, '_mutter_vorschau_link_gesichert', None)
            self._mutter_vorschau_link_gesichert = None
            joint = mutter_einfuegen(
                assembly, mutter_body, MUTTER_LABEL,
                target_link, face, face_name,
                self._letzte_achse_ursprung,
                self._letzte_achse_richtung,
                self._letzter_schraube_link,
                self._letzter_lcs_bolt_edge,
                vorschau_link=vorschau
            )
            if joint:
                self._letzter_mutter_joint = joint
                # Zufallsdrehung ±30° in 10°-Schritten
                if self._cb_zufall.isChecked():
                    import random as _random
                    winkel = _random.choice(list(range(-30, 31, 10)))
                    joint.Offset2 = App.Placement(
                        App.Vector(0, 0, joint.Offset2.Base.z),
                        App.Rotation(*[float(winkel), 0.0, 0.0]))
                    assembly.Document.recompute()
                    App.Console.PrintMessage(f"  Mutter Zufallsdrehung: {winkel}°\n")
                self._set_status("Mutter eingefügt.\nNächste Schraube anklicken …")
            else:
                self._set_status("Fehler beim Einfügen der Mutter.", error=True)
        except Exception as e:
            self._set_status(f"Mutter-Fehler: {e}", error=True)
            App.Console.PrintError(f"mutter_einfuegen: {e}\n")

    # --- Nachjustieren ------------------------------------------------------

    def _on_nachjustieren_schraube(self):
        if self._letzter_joint is None:
            self._set_status("Noch keine Schraube eingefügt.", error=True)
            return
        # Standard-FreeCAD-Dialog öffnen (Doppelklick-Äquivalent)
        try:
            Gui.ActiveDocument.setEdit(self._letzter_joint.Name)
        except Exception as e:
            self._set_status(f"Fehler beim Öffnen des Dialogs: {e}", error=True)

    def _on_nachjustieren_mutter(self):
        # TODO: Eigener 1D-Offset-Dialog in v0.2
        self._set_status("Nachjustieren Mutter noch nicht implementiert (kommt in v0.2).")

    # --- Hilfsmethoden ------------------------------------------------------

    def _highlight_active_btn(self, active_btn):
        """Hebt den gewählten Schrauben-Knopf farblich hervor."""
        for btn in self._schrauben_btns:
            if btn is active_btn:
                btn.setStyleSheet(
                    "QPushButton { background-color: #0066cc; color: white; "
                    "font-weight: bold; border: 2px solid #004499; padding: 4px; }"
                )
            else:
                btn.setStyleSheet("")

    def _set_status(self, text, error=False):
        self._status.setText(text)
        color = "#aa0000" if error else "#555"
        self._status.setStyleSheet(f"color: {color}; font-style: italic;")


# ---------------------------------------------------------------------------
# Einstiegspunkt
# ---------------------------------------------------------------------------

# Dialog als Modulvariable halten (verhindert garbage collection)
_dialog = None

def main():
    global _dialog
    if _dialog is not None and _dialog.isVisible():
        _dialog.raise_()
        _dialog.activateWindow()
        return

    _dialog = SchraubenDialog(Gui.getMainWindow())
    _dialog.show()

main()
