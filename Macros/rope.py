"""
Eitech Seilvisualisierung – Stufe 2.2
=======================================
Zeichnet das Hakenseil mit korrekten Tangenten und Bögen.

Vorzeichen-Konvention:
  +1 wenn das ziehende Seil ein positives Drehmoment bzgl. der Rollenachse erzeugt
  -1 umgekehrt

Das Vorzeichen gehört zur Rolle und steuert sowohl:
  - den Tangentenpunkt (Einlauf und Auslauf)
  - die Bogendrehrichtung

Ausführen als Makro.
Zum Stoppen:  App._eitech_observer.stop()  oder  stop_observer()
"""

import FreeCAD as App
import Part
import math


# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------
SEIL_NAME             = "Hakenseil"
SEIL_FARBE            = (1.0, 0.0, 0.0)
SEIL_DICKE            = 4.0
ROPE_DIAMETER_DEFAULT = 0.5   # mm
verbose_bogen         = True  # Bogen-Winkel im Ausgabefenster anzeigen

# Seilpfad: (Objekt-Label, LCS-Label, Vorzeichen)
# Vorzeichen = 0 für Endpunkte (kein Bogen)
SEILPFAD = [
    ("Winde M1 Z20 P003", "LCS_winch",       -1),
    ("Felge 25",          "LCS_rope_groove",  +1),
    ("Felge 005",         "LCS_rope_groove",  -1),
    ("Seilknoten",        "LCS_anchor",        0),
]

SEIL_NAME_2           = "Auslegerseil"
SEIL_FARBE_2          = (0.0, 0.0, 1.0)   # blau

SEILPFAD_2 = [
    ("Winde M1 Z20 P001", "LCS_winch",        -1),
    ("Rolle 14",          "LCS_rope_groove",  -1),
    ("Felge 004",         "LCS_rope_groove",  -1),
    ("Felge 002",         "LCS_rope_groove",  -1),
    ("Felge 003",         "LCS_rope_groove",  +1),
    ("Felge 001",         "LCS_rope_groove",  -1),
    ("Seilknoten001",     "LCS_anchor",        0),
]


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------
def _to_mm(val):
    try:
        return float(val.getValueAs("mm"))
    except AttributeError:
        return float(val)

def _v(obj):     return (float(obj.x), float(obj.y), float(obj.z))
def _norm(v):
    l = (v[0]**2+v[1]**2+v[2]**2)**0.5
    if l < 1e-10: raise ValueError(f"Zero vector: {v}")
    return (v[0]/l, v[1]/l, v[2]/l)
def _cross(a,b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
def _dot(a,b):   return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]
def _add(a,b):   return (a[0]+b[0], a[1]+b[1], a[2]+b[2])
def _sub(a,b):   return (a[0]-b[0], a[1]-b[1], a[2]-b[2])
def _scale(v,s): return (v[0]*s, v[1]*s, v[2]*s)
def _len(v):     return (v[0]**2+v[1]**2+v[2]**2)**0.5
def _fvec(t):    return App.Vector(t[0], t[1], t[2])


# ---------------------------------------------------------------------------
# Tangentenberechnung
# Vorzeichen w1 und w2 gehören zu den jeweiligen Rollen
# ---------------------------------------------------------------------------
def berechne_tangente(M1, A1, r1, w1, M2, A2, r2, w2,
                      max_iter=50, toleranz=1e-6):
    """
    Berechnet die gemeinsame Tangente zweier Rollen.

    T1 liegt auf Rolle 1, bestimmt durch w1 (Vorzeichen von Rolle 1)
    T2 liegt auf Rolle 2, bestimmt durch w2 (Vorzeichen von Rolle 2)

    Returns T1, T2 als tuples.
    """
    A1 = _norm(A1)
    A2 = _norm(A2)
    S  = _sub(M2, M1)

    T1 = T2 = None

    for _ in range(max_iter):
        c1 = _cross(A1, S)
        c2 = _cross(A2, S)

        R1 = _scale(_norm(c1), r1 * w1) if _len(c1) > 1e-8 and r1 > 0 \
             else (0.0, 0.0, 0.0)
        R2 = _scale(_norm(c2), r2 * w2) if _len(c2) > 1e-8 and r2 > 0 \
             else (0.0, 0.0, 0.0)

        T1 = _add(M1, R1)
        T2 = _add(M2, R2)

        S_neu = _sub(T2, T1)
        delta = _len(_sub(S_neu, S))
        S = S_neu

        if delta < toleranz:
            return T1, T2

    App.Console.PrintWarning("Tangente: keine Konvergenz.\n")
    return T1, T2


# ---------------------------------------------------------------------------
# Bogenberechnung
# Vorzeichen w bestimmt Bogendrehrichtung
# ---------------------------------------------------------------------------
def berechne_bogen(M, A, r, w, T_ein, T_aus, S_ein):
    """
    Berechnet den Kreisbogen auf einer Rolle mit expliziten Winkeln.

    M     : Rollenmittelpunkt
    A     : Rollenachse (normiert)
    r     : effektiver Radius
    w     : Vorzeichen (+1 = gegen Uhrzeigersinn bzgl. A, -1 = mit Uhrzeigersinn)
    T_ein : Einlaufpunkt (liegt auf dem Kreis)
    T_aus : Auslaufpunkt (liegt auf dem Kreis)

    Baut ein lokales 2D-Koordinatensystem in der Rollenebene (e1, e2),
    berechnet Winkel von T_ein und T_aus, läuft in Richtung w.
    """
    import math

    A = _norm(A)

    # Lokales KS in der Rollenebene senkrecht zu A:
    # e1 = Richtung von M nach T_ein
    # e2 = cross(A, e1) → senkrecht zu e1 und A, in der Rollenebene
    R_ein = _norm(_sub(T_ein, M))
    e1 = R_ein
    e2 = _norm(_cross(A, e1))
    if _len(_cross(A, e1)) < 1e-8:
        App.Console.PrintWarning("  Arc: R_ein parallel to A – skipped.\n")
        return None

    # Winkel von T_ein und T_aus im lokalen KS
    R_aus = _norm(_sub(T_aus, M))
    theta_ein = 0.0   # T_ein liegt per Definition bei 0
    x_aus = _dot(R_aus, e1)
    y_aus = _dot(R_aus, e2)
    theta_aus = math.atan2(y_aus, x_aus)

    # Bogenlauf in Richtung w:
    # w=+1 → gegen Uhrzeigersinn → theta steigt → theta_aus > theta_ein
    # w=-1 → mit Uhrzeigersinn  → theta sinkt  → theta_aus < theta_ein
    if w > 0 and theta_aus <= 0:
        theta_aus += 2 * math.pi
    elif w < 0 and theta_aus >= 0:
        theta_aus -= 2 * math.pi

    # Kontinuitätsprüfung am Einlaufpunkt:
    # Bogentangente bei T_ein = e2 * w (senkrecht zu R_ein in Drehrichtung w)
    # Einlaufender Seilvektor S_ein muss dieselbe Richtung haben
    # dot(S_ein, bogen_tangente) > 0 → korrekt, sonst w umkehren
    bogen_tangente = _scale(e2, float(w))
    if _dot(_norm(S_ein), bogen_tangente) < 0:
        w = -w
        # theta_aus neu berechnen mit umgekehrtem w
        if w > 0 and theta_aus <= 0:
            theta_aus += 2 * math.pi
        elif w < 0 and theta_aus >= 0:
            theta_aus -= 2 * math.pi

    # T_mid bei halbem Winkel
    theta_mid = (theta_ein + theta_aus) / 2
    R_mid = _add(_scale(e1, math.cos(theta_mid)),
                 _scale(e2, math.sin(theta_mid)))
    T_mid = _add(M, _scale(R_mid, r))

    if verbose_bogen:
        App.Console.PrintMessage(
            f"  Arc angles: ein=0°, mid={math.degrees(theta_mid):.1f}°, "
            f"aus={math.degrees(theta_aus):.1f}°  w={w}\n"
        )

    try:
        arc = Part.Arc(_fvec(T_ein), _fvec(T_mid), _fvec(T_aus))
        return arc.toShape()
    except Exception as e:
        App.Console.PrintWarning(f"  Arc failed: {e}\n")
        return None


# ---------------------------------------------------------------------------
# Objekt- und LCS-Zugriff
# ---------------------------------------------------------------------------
def find_by_label(doc, label):
    for obj in doc.Objects:
        if obj.Label == label:
            return obj
    return None


def get_global_placement(link_obj):
    """
    Berechnet das globale Placement eines App::Link durch Traversierung
    der InList-Kette bis zur Hauptassembly.
    """
    placement = link_obj.Placement
    current = link_obj

    for _ in range(10):   # max 10 Ebenen
        in_list = current.InList
        if not in_list:
            break
        parent = in_list[0]
        if not hasattr(parent, "Placement"):
            break
        # Assembly::AssemblyObject ist der interne Container der Subassembly
        # – dessen Placement ist immer (0,0,0), überspringen
        if parent.TypeId == "Assembly::AssemblyObject":
            current = parent
            continue
        placement = parent.Placement.multiply(placement)
        current = parent

    return App.Placement(placement)


def get_lcs_data(link_obj, lcs_label, rope_diameter_mm):
    linked = link_obj.LinkedObject
    if linked is None:
        App.Console.PrintError(f"  No LinkedObject for '{link_obj.Label}'.\n")
        return None

    # LCS suchen – direkt oder in verschachteltem Body
    lcs = None
    for child in linked.OutList:
        if child.Label == lcs_label:
            lcs = child
            break
        if hasattr(child, "OutList"):
            for subchild in child.OutList:
                if subchild.Label == lcs_label:
                    lcs = subchild
                    break
        if lcs:
            break

    if lcs is None:
        App.Console.PrintError(
            f"  LCS '{lcs_label}' not found in '{link_obj.Label}'.\n"
        )
        return None

    # Globale Transformation: Parents-Kette × Link × LCS
    global_pl = get_global_placement(link_obj).multiply(lcs.Placement)
    pos_vec   = global_pl.Base
    achse_vec = global_pl.Rotation.multVec(App.Vector(1, 0, 0))

    pos   = (float(pos_vec.x),   float(pos_vec.y),   float(pos_vec.z))
    achse = (float(achse_vec.x), float(achse_vec.y), float(achse_vec.z))

    if hasattr(lcs, "radius"):
        r_mm = _to_mm(lcs.radius)
        r_eff = r_mm + rope_diameter_mm / 2 if r_mm > 0 else 0.0
    else:
        r_eff = 0.0

    return pos, achse, r_eff


# ---------------------------------------------------------------------------
# Seil zeichnen
# ---------------------------------------------------------------------------
def draw_seil(doc=None, verbose=False, do_recompute=True,
              seil_name=None, seilpfad=None, seil_farbe=None):
    if doc is None:
        doc = App.ActiveDocument
    if doc is None:
        return
    if seil_name  is None: seil_name  = SEIL_NAME
    if seilpfad   is None: seilpfad   = SEILPFAD
    if seil_farbe is None: seil_farbe = SEIL_FARBE

    seil_obj = find_by_label(doc, seil_name)
    rope_diameter_mm = _to_mm(seil_obj.rope_diameter) \
        if seil_obj and hasattr(seil_obj, "rope_diameter") \
        else ROPE_DIAMETER_DEFAULT

    # --- LCS-Daten sammeln ---
    punkte_data = []   # (pos, achse, r_eff, label, vorzeichen)
    for obj_label, lcs_label, vorzeichen in seilpfad:
        obj = find_by_label(doc, obj_label)
        if obj is None:
            App.Console.PrintError(f"  Object not found: '{obj_label}'.\n")
            return
        data = get_lcs_data(obj, lcs_label, rope_diameter_mm)
        if data is None:
            return
        pos, achse, r_eff = data
        punkte_data.append((pos, achse, r_eff, obj_label, vorzeichen))
        if verbose:
            App.Console.PrintMessage(
                f"  '{obj_label}': pos=({pos[0]:.1f},{pos[1]:.1f},{pos[2]:.1f})"
                f"  r_eff={r_eff:.2f}  w={vorzeichen}\n"
            )

    n = len(punkte_data)

    # --- Tangenten berechnen ---
    # Segment i→i+1: T1 bestimmt durch w_i, T2 durch w_{i+1}
    tangenten = []
    for i in range(n - 1):
        M1, A1, r1, label1, w1 = punkte_data[i]
        M2, A2, r2, label2, w2 = punkte_data[i + 1]
        try:
            T1, T2 = berechne_tangente(M1, A1, r1, w1, M2, A2, r2, w2)
        except ValueError as e:
            App.Console.PrintError(f"  Tangent error: {e}\n")
            return
        tangenten.append((T1, T2))
        if verbose:
            App.Console.PrintMessage(
                f"  Seg {i+1}: ({T1[0]:.1f},{T1[1]:.1f},{T1[2]:.1f})"
                f" → ({T2[0]:.1f},{T2[1]:.1f},{T2[2]:.1f})\n"
            )

    # --- Kanten bauen: gerade + Bogen + gerade + ... ---
    kanten = []
    for i in range(n - 1):
        T1, T2 = tangenten[i]

        # Gerades Segment
        if _len(_sub(T2, T1)) > 1e-6:
            kanten.append(Part.LineSegment(_fvec(T1), _fvec(T2)).toShape())
        else:
            App.Console.PrintWarning(f"  Segment {i+1} zero length – skipped.\n")

        # Bogen auf Rolle i+1 (außer beim letzten Segment)
        if i < n - 2:
            M, A, r, label, w = punkte_data[i + 1]
            T_ein = T2                    # Einlaufpunkt
            T_aus = tangenten[i + 1][0]  # Auslaufpunkt

            if r > 1e-6 and w != 0:
                S_ein = _sub(T2, T1)   # einlaufender Seilvektor
                bogen = berechne_bogen(M, A, r, w, T_ein, T_aus, S_ein)
                if bogen is not None:
                    kanten.append(bogen)
                    if verbose:
                        App.Console.PrintMessage(
                            f"  Arc Rolle {i+1} ('{label}') w={w}\n"
                        )

    if not kanten:
        App.Console.PrintError("  No valid segments.\n")
        return

    try:
        wire = Part.Wire(kanten)
    except Exception as e:
        App.Console.PrintError(f"  Wire failed: {e}\n")
        try:
            wire = Part.Wire(Part.sortEdges(kanten)[0])
        except Exception as e2:
            App.Console.PrintError(f"  Fallback failed: {e2}\n")
            return

    if seil_obj is None:
        seil_obj = doc.addObject("Part::Feature", seil_name)
        seil_obj.addProperty("App::PropertyLength", "rope_diameter",
                             "Eitech", "Rope diameter in mm")
        seil_obj.rope_diameter = ROPE_DIAMETER_DEFAULT

    seil_obj.Shape = wire

    if seil_obj.ViewObject:
        try:
            seil_obj.ViewObject.LineColor  = seil_farbe
            seil_obj.ViewObject.LineWidth  = SEIL_DICKE
            seil_obj.ViewObject.PointColor = seil_farbe
            seil_obj.ViewObject.PointSize  = SEIL_DICKE
        except Exception:
            pass

    if do_recompute:
        doc.recompute()

    if verbose:
        App.Console.PrintMessage(
            f"✓ '{seil_name}': {len(kanten)} segments, "
            f"length={wire.Length:.2f} mm\n"
        )


# ---------------------------------------------------------------------------
# DocumentObserver
# ---------------------------------------------------------------------------
class SeilObserver:
    def __init__(self, doc_name):
        self.doc_name = doc_name
        self._aktiv   = True
        App.Console.PrintMessage(
            f"✓ SeilObserver started for '{doc_name}'.\n"
            f"  To stop: stop_observer()\n"
        )

    def slotRecomputedDocument(self, doc):
        if not self._aktiv or doc.Name != self.doc_name:
            return
        draw_seil(doc, verbose=False, do_recompute=False)
        draw_seil(doc, verbose=False, do_recompute=False,
                  seil_name=SEIL_NAME_2, seilpfad=SEILPFAD_2, seil_farbe=SEIL_FARBE_2)

    def stop(self):
        self._aktiv = False
        App.Console.PrintMessage("✓ SeilObserver stopped.\n")


_observer = None

def start_observer():
    global _observer
    if hasattr(App, "_eitech_observer") and App._eitech_observer is not None:
        try:
            App.removeDocumentObserver(App._eitech_observer)
            App._eitech_observer.stop()
        except Exception:
            pass
    doc = App.ActiveDocument
    if doc is None:
        App.Console.PrintError("No active document.\n")
        return
    if _observer is not None:
        App.removeDocumentObserver(_observer)
        _observer.stop()
    _observer = SeilObserver(doc.Name)
    App._eitech_observer = _observer
    App.addDocumentObserver(_observer)
    draw_seil(doc, verbose=True, do_recompute=False)
    draw_seil(doc, verbose=True, do_recompute=True,
              seil_name=SEIL_NAME_2, seilpfad=SEILPFAD_2, seil_farbe=SEIL_FARBE_2)

def stop_observer():
    global _observer
    obs = getattr(App, "_eitech_observer", None)
    if obs is None:
        App.Console.PrintMessage("No active observer.\n")
        return
    App.removeDocumentObserver(obs)
    obs.stop()
    App._eitech_observer = None
    _observer = None


# ---------------------------------------------------------------------------
# Direkt ausführen
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    App.Console.PrintMessage("=== Eitech Seilvisualisierung – Stufe 2.2 ===\n")
    start_observer()
