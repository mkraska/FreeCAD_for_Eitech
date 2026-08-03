"""
FlexHosePath - FreeCAD scripted object (Stab/Drehfeder-Version)

Pfad aus drei Segmenten zwischen zwei Local-Coordinate-System-Objekten
(LCS1, LCS2), die jeweils im Anschlussstutzen-Bauteil sitzen (Ursprung =
Beginn des Stutzens, Z-Achse = Steckrichtung):

  1. gerade Strecke entlang LCS1-Z-Achse ueber "InsertionLength1"
  2. freier Bogen dazwischen - jetzt ein diskretes System aus starren
     Staeben gleicher Laenge, verbunden durch Drehfedern (Biegeenergie
     proportional zum Knickwinkel^2), das per Energie-Minimierung
     (scipy.optimize.minimize, SLSQP) unter der Nebenbedingung fester
     Stablaenge geloest wird - statt wie zuvor per Shooting-Verfahren
     ueber die Elastica-DGL.
  3. gerade Strecke entlang LCS2-Z-Achse ueber "InsertionLength2"

Warum Energie-Minimierung statt Schuss-Verfahren:
Die "Korkenzieher"-Artefakte der Elastica-Loesung waren gueltige
Gleichgewichtsloesungen, aber Sattelpunkte der Biegeenergie (hohe,
instabile Formen). Ein Minimierer kann dort prinzipbedingt nicht
haengen bleiben. Zusaetzlich wird das Problem grob-zu-fein geloest
(N=2 -> 4 -> 8 Staebe): mit nur 2 Staeben ist eine verschlungene Form
geometrisch gar nicht erst darstellbar, wodurch die Loesung von Anfang
an im "einfachen" Loesungsbereich bleibt.

Die vorgegebenen Endtangenten (aus LCS1/LCS2) fliessen ueber zwei feste
"Geisterknoten" ausserhalb des freien Bereichs ein (Fortsetzung der
Einsteckrichtung um eine Stablaenge) - die Biegeenergie an den beiden
Rand-Gelenken bestraft dann automatisch jede Abweichung von der
vorgegebenen Tangente, ohne separate Zwangsbedingung.

Unterbestimmtheit bei symmetrischen Randbedingungen (z.B. parallele
Anschlussstutzen -> Lage des "Dreiecks" bei N=2 frei drehbar um die
Verbindungsachse): wird durch eine deterministische Dreieckslast
aufgebrochen - Richtung an LCS1 ueber "PullAngle1" (Drehwinkel
um die lokale LCS1-Z-Achse, gemessen von dessen lokaler X-Achse), an LCS2
analog ueber "PullAngle2"; die Last ist an ihrem jeweiligen Ende
maximal und faellt linear zum anderen Ende hin ab. Betrag ueber
"PullStrength1"/"PullStrength2" (getrennt pro Ende). Haengt nur vom
AKTUELLEN Assembly-Zustand ab (LCS-Orientierungen), nicht von der
Historie - anders als ein frueherer Ansatz mit raumfestem Vektor, der bei
gleicher Assembly-Stellung je nach vorheriger Position zu unterschiedlichen
Ergebnissen fuehren konnte.

Torsion/Verwoelbung ist in dieser Version bewusst NICHT modelliert
(nur die Mittellinie) - kann bei Bedarf spaeter ergaenzt werden.

Benoetigt scipy (scipy.optimize.minimize) in der FreeCAD-Python-Umgebung.
"""

import FreeCAD as App
import FreeCADGui as Gui
import Part
import numpy as np
import time
from scipy.optimize import minimize

# Auf True setzen, um Zeitmessungen der einzelnen Berechnungsphasen in die
# Konsole zu schreiben (Diagnose bei Performance-Fragen in grossen/komplexen
# Assemblies - unterscheidet FreeCAD-eigene Platzierungsaufloesung von
# unserer eigenen Rechenzeit, siehe Skill-Abschnitt "Profiling").
PROFILE = False

# Vorbelegungen fuer den Wire/Hose-Umschalter im Task-Panel.
HOSE_DEFAULT_DIAMETER = 4.0
HOSE_DEFAULT_COLOR = (0.8549, 0.898, 0.9373)  # #dae5ef
HOSE_DEFAULT_TRANSPARENCY = 50
WIRE_DEFAULT_DIAMETER = 1.5
WIRE_DEFAULT_COLOR = (0.05, 0.05, 0.05)  # dunkle Isolierung als Default
WIRE_DEFAULT_TRANSPARENCY = 0


def set_profiling(enabled):
    """Schaltet PROFILE um - als Funktion statt direkter Variablen-
    Zuweisung, damit es unabhaengig vom Namensraum zuverlaessig wirkt (bei
    Ausfuehrung ueber den Makro-Dialog liegt PROFILE sonst evtl. in einem
    anderen Namensraum als dort, wo man es aus der Konsole setzen wuerde)."""
    global PROFILE
    PROFILE = enabled
    App.Console.PrintMessage("PROFILE = %s\n" % enabled)


def _profile_start():
    return time.perf_counter() if PROFILE else None


def _profile_log(label, t_start):
    if PROFILE and t_start is not None:
        App.Console.PrintMessage(
            "PROFILE: %s: %.3f s\n" % (label, time.perf_counter() - t_start))


def _joint_angle(t_prev, t_next):
    """Winkel zwischen zwei Einheits-Tangentenvektoren, numerisch robust
    (atan2 aus Kreuz-/Skalarprodukt statt arccos - keine Ableitungs-
    Singularitaet nahe Winkel=0)."""
    cross = np.cross(t_prev, t_next)
    sin_t = np.linalg.norm(cross)
    cos_t = np.dot(t_prev, t_next)
    return np.arctan2(sin_t, cos_t)


def _placement_signature(pl, ndigits=6):
    """Rundet Position+Rotation einer Placement auf eine vergleichbare,
    hashbare Form - fuer den Signatur-Vergleich in FlexHosePath.execute()
    (Gleitkomma-Rauschen aus wiederholter Transform-Verkettung wuerde sonst
    selbst bei "unveraenderter" Lage minimale Abweichungen erzeugen und
    das Ueberspringen der teuren Neuberechnung verhindern)."""
    base = pl.Base
    q = pl.Rotation.Q
    return (round(base.x, ndigits), round(base.y, ndigits),
            round(base.z, ndigits),
            round(q[0], ndigits), round(q[1], ndigits),
            round(q[2], ndigits), round(q[3], ndigits))


def _perp_basis(axis):
    """Zwei orthonormale Vektoren senkrecht zu `axis` (fuer die
    Schwerkraft-/Regularisierungsrichtung, die per Winkel um `axis` gedreht
    wird). Branchlose Konstruktion nach Duff, Burgess, Christensen, Hery,
    Kensler, Liani, Villemin: "Building an Orthonormal Basis, Revisited"
    (JCGT 2017) - im Gegensatz zur vorherigen Version (harte Fallunter-
    scheidung bei |dot(Z,axis)| > 0.9, Referenzvektor sprang dort abrupt
    von Z- auf X-Achse -> sichtbarer Sprung im Regularisierungsvektor bei
    leichter Repositionierung nahe dieser Schwelle) ist diese Formel fuer
    JEDE Achsrichtung stetig, keine Schwelle, kein Sprung."""
    n = axis / np.linalg.norm(axis)
    sign = 1.0 if n[2] >= 0.0 else -1.0
    a = -1.0 / (sign + n[2])
    b = n[0] * n[1] * a
    e1 = np.array([1.0 + sign * n[0] * n[0] * a, sign * b, -sign * n[0]])
    e2 = np.array([b, sign + n[1] * n[1] * a, -n[1]])
    return e1, e2


def _build_chain(p0, p3, free_nodes, ghost_minus, ghost_plus):
    return np.vstack([ghost_minus, p0, free_nodes, p3, ghost_plus])


def _bending_energy(chain):
    seg = np.diff(chain, axis=0)
    tangents = seg / np.linalg.norm(seg, axis=1, keepdims=True)
    E = 0.0
    for i in range(len(tangents) - 1):
        th = _joint_angle(tangents[i], tangents[i + 1])
        E += 0.5 * th * th
    return E


def _total_energy(x, N, p0, p3, ghost_minus, ghost_plus, load1, load2,
                   target_length):
    free_nodes = x.reshape(N - 1, 3)
    chain = _build_chain(p0, p3, free_nodes, ghost_minus, ghost_plus)
    E_bend = _bending_energy(chain)
    # Dreieckslast statt raumfestem globalem Vektor: pro freiem Knoten i
    # (1..N-1, Bogenlaengen-Anteil s_i=i/N) linear zwischen load1 (bei p0,
    # s=0, maximal) und load2 (bei p3, s=1, maximal) interpoliert - beide
    # deterministisch aus den LCS-Orientierungen + Winkeln abgeleitet.
    # Ersetzt den fruaheren global-uniformen grav_dir-Ansatz, dessen
    # Hilfsbasis (_perp_basis auf der Verbindungsachse) unvermeidbar eine
    # Singularitaet hatte und dessen Kontinuitaets-Korrektur die Loesung
    # von der vorherigen Assembly-Stellung abhaengig (nicht reproduzierbar)
    # gemacht haette - dieser Ansatz ist rein aus dem AKTUELLEN Zustand
    # bestimmt, keine Historie noetig.
    s = np.arange(1, N) / N  # (N-1,) Bogenlaengen-Anteil je freiem Knoten
    loads = np.outer(1.0 - s, load1) + np.outer(s, load2)  # (N-1, 3)
    E_grav = -np.sum(loads * (free_nodes - p0)) / target_length
    return E_bend + E_grav


def _length_constraints(x, N, p0, p3, L_bar):
    free_nodes = x.reshape(N - 1, 3)
    chain = np.vstack([p0, free_nodes, p3])
    seg = np.diff(chain, axis=0)
    return np.linalg.norm(seg, axis=1) - L_bar


def solve_rod_chain(p0, t0, p3, t3, target_length, load1, load2,
                     n_final=8):
    """Loest die freie Bogenform per Grob-zu-Fein-Energieminimierung.
    `load1`/`load2` sind die Dreieckslast-Vektoren (Richtung*Staerke) an
    den beiden Enden (siehe _total_energy). Rueckgabe: (N_final+1) x 3
    Array der Knotenpunkte p0..p_N (ohne Geisterknoten), sowie das letzte
    scipy-OptimizeResult (fuer Erfolgs-/Diagnosecheck)."""
    N = 2
    L_bar = target_length / N
    ghost_minus = p0 - t0 * L_bar
    ghost_plus = p3 + t3 * L_bar

    avg_load = 0.5 * (load1 + load2)
    avg_load_norm = np.linalg.norm(avg_load)
    perturb_dir = avg_load / avg_load_norm if avg_load_norm > 1e-9 \
        else np.zeros(3)
    mid = 0.5 * (p0 + p3) + perturb_dir * 0.05 * target_length
    x0 = mid.copy()

    result = None
    while True:
        cons = {'type': 'eq', 'fun': _length_constraints, 'args': (N, p0, p3, L_bar)}
        result = minimize(
            _total_energy, x0,
            args=(N, p0, p3, ghost_minus, ghost_plus, load1, load2,
                  target_length),
            constraints=[cons], method='SLSQP',
            options={'maxiter': 500, 'ftol': 1e-12})

        free_nodes = result.x.reshape(N - 1, 3)
        if N >= n_final:
            chain = _build_chain(p0, p3, free_nodes, ghost_minus, ghost_plus)
            return chain[1:-1], result

        chain = _build_chain(p0, p3, free_nodes, ghost_minus, ghost_plus)[1:-1]
        new_chain = [chain[0]]
        for i in range(len(chain) - 1):
            new_chain.append(0.5 * (chain[i] + chain[i + 1]))
            new_chain.append(chain[i + 1])
        new_chain = np.array(new_chain)

        N = 2 * N
        L_bar = target_length / N
        ghost_minus = p0 - t0 * L_bar
        ghost_plus = p3 + t3 * L_bar
        x0 = new_chain[1:-1].flatten()


# Name der Property, unter der die Einstecklaenge direkt am Anschluss-
# Bauteil (nicht am Schlauch) hinterlegt werden kann - fuer ein bestimmtes
# Bauteil ist sie ja immer gleich, unabhaengig davon, wie viele Schlaeuche
# an ihm haengen.
CONNECTOR_INSERTION_PROP = "HoseInsertionLength"


def set_connector_insertion_length(part_obj, length):
    """Einstecklaenge als Property auf dem Anschluss-Bauteil selbst ablegen.
    FlexHosePath liest diese Property automatisch (Vorrang vor dem manuellen
    InsertionLength1/2-Wert am Schlauch-Objekt), wenn sie am ueber LCS1/LCS2
    referenzierten Top-Objekt vorhanden ist. Bei App::Link-Instanzen ggf. auf
    dem verlinkten Basisobjekt setzen (part_obj.LinkedObject), damit alle
    Instanzen denselben Wert teilen."""
    if not hasattr(part_obj, CONNECTOR_INSERTION_PROP):
        part_obj.addProperty(
            "App::PropertyLength", CONNECTOR_INSERTION_PROP, "Hose",
            "Feste Einstecklaenge dieses Anschluss-Bauteils - wird von "
            "FlexHosePath automatisch verwendet, sofern vorhanden.")
    setattr(part_obj, CONNECTOR_INSERTION_PROP, length)


def _resolve_insertion_length(linksub, manual_value):
    """Bevorzugt die Einstecklaenge vom Anschluss-Bauteil selbst, falls dort
    (per set_connector_insertion_length) hinterlegt - sonst der manuelle
    InsertionLength1/2-Wert am Schlauch-Objekt.

    WICHTIG bei tief verschachtelten Assemblies (z.B. Assembly.Assembly001.
    Verdichterventil.Nippel028....): `topobj` (linksub[0]) ist dabei so gut
    wie NIE das eigentliche Anschluss-Bauteil, sondern der AEUSSERSTE Knoten
    der Selektion (z.B. die oberste Assembly) - das eigentliche Bauteil
    steckt erst im aufgeloesten Unterpfad. Deshalb wird hier die GESAMTE
    aufgeloeste Objektkette (topobj -> ... -> LCS) durchsucht, von der
    konkretesten (tiefsten, naeher am LCS) zur aeussersten Ebene - nicht nur
    topobj selbst. Fuer jedes Objekt in der Kette wird zusaetzlich dessen
    LinkedObject geprueft (falls es ein Link ist), damit eine einmal am
    gemeinsamen Basisteil hinterlegte Einstecklaenge von allen Instanzen
    geteilt wird."""
    topobj, subnames = linksub
    chain = [topobj]
    if subnames:
        try:
            _t = _profile_start()
            resolved_chain = topobj.getSubObjectList(subnames[0])
            _profile_log("getSubObjectList() fuer HoseInsertionLength", _t)
            if resolved_chain:
                chain = resolved_chain
        except Exception as exc:
            App.Console.PrintWarning(
                "FlexHosePath: getSubObjectList() fehlgeschlagen (%s), "
                "durchsuche nur topobj fuer HoseInsertionLength.\n" % exc)

    for obj in reversed(chain):  # tiefste (konkreteste) Ebene zuerst
        if hasattr(obj, CONNECTOR_INSERTION_PROP):
            App.Console.PrintMessage(
                "FlexHosePath: HoseInsertionLength gefunden an '%s'.\n"
                % obj.Name)
            return getattr(obj, CONNECTOR_INSERTION_PROP).Value
        linked = getattr(obj, "LinkedObject", None)
        if linked is not None and hasattr(linked, CONNECTOR_INSERTION_PROP):
            App.Console.PrintMessage(
                "FlexHosePath: HoseInsertionLength gefunden am "
                "LinkedObject '%s' von '%s'.\n" % (linked.Name, obj.Name))
            return getattr(linked, CONNECTOR_INSERTION_PROP).Value

    App.Console.PrintMessage(
        "FlexHosePath: keine HoseInsertionLength in der Kette [%s] "
        "gefunden, verwende manuellen Wert %.2f mm.\n"
        % (", ".join(o.Name for o in chain), manual_value))
    return manual_value


def _ensure_flexhosepath_properties(obj):
    """Legt alle FlexHosePath-Properties an, FALLS sie noch nicht existieren
    (idempotent) - bestehende Werte bleiben unangetastet. Wird sowohl von
    __init__() bei neu erzeugten Objekten genutzt als auch von
    upgrade_hose_objects(), um aeltere Bestandsobjekte (aus einer frueheren
    Skript-Version) ohne Neuerzeugung auf den aktuellen Stand zu bringen."""
    def add(ptype, name, group, doc, default=None):
        if not hasattr(obj, name):
            obj.addProperty(ptype, name, group, doc)
            if default is not None:
                setattr(obj, name, default)
            return True
        return False

    add("App::PropertyXLinkSub", "LCS1", "FlexHose",
        "Erstes Anschluss-Koordinatensystem")
    add("App::PropertyXLinkSub", "LCS2", "FlexHose",
        "Zweites Anschluss-Koordinatensystem")
    add("App::PropertyLength", "Length", "FlexHose",
        "Feste Schlauchlaenge (bleibt bei Bewegung konstant, kann durch "
        "die abschliessende Spline-Glaettung geringfuegig abweichen)",
        default=100.0)
    add("App::PropertyBool", "FlipStart", "FlexHose",
        "Tangentenrichtung an LCS1 umkehren", default=False)
    add("App::PropertyBool", "FlipEnd", "FlexHose",
        "Tangentenrichtung an LCS2 umkehren", default=False)
    add("App::PropertyLength", "InsertionLength1", "FlexHose",
        "Einstecklaenge auf dem Stutzen an LCS1 - NUR Fallback, wenn das "
        "Anschluss-Bauteil selbst keine '%s'-Property hat (siehe "
        "set_connector_insertion_length())" % CONNECTOR_INSERTION_PROP,
        default=0.0)
    add("App::PropertyLength", "InsertionLength2", "FlexHose",
        "Einstecklaenge auf dem Stutzen an LCS2 - NUR Fallback, wenn das "
        "Anschluss-Bauteil selbst keine '%s'-Property hat"
        % CONNECTOR_INSERTION_PROP, default=0.0)
    add("App::PropertyInteger", "Segments", "FlexHose",
        "Anzahl Staebe der finalen Verfeinerungsstufe (wird intern auf "
        "die naechste Zweierpotenz aufgerundet, Start immer bei 2)",
        default=8)
    add("App::PropertyAngle", "PullAngle1", "FlexHose",
        "Richtung des Pull-Vektors an LCS1: Drehwinkel um die lokale "
        "Z-Achse von LCS1, gemessen von dessen lokaler X-Achse aus "
        "(Regularisierung gegen unbestimmte Lage bei symmetrischen "
        "Randbedingungen). Deterministisch aus der aktuellen LCS1-"
        "Orientierung abgeleitet - anders als ein raumfester Vektor "
        "liefert das bei gleicher Assembly-Stellung immer dasselbe "
        "Ergebnis, unabhaengig von der vorherigen Position.",
        default=0.0)
    add("App::PropertyAngle", "PullAngle2", "FlexHose",
        "Richtung des Pull-Vektors an LCS2: Drehwinkel um die lokale "
        "Z-Achse von LCS2, gemessen von dessen lokaler X-Achse aus. Die "
        "Last ist bei LCS1 maximal in Richtung PullAngle1 und faellt "
        "linear zur LCS2-Seite hin auf die Richtung/Groesse von "
        "PullAngle2 ab (und umgekehrt) - siehe Skill fuer Details.",
        default=0.0)
    add("App::PropertyFloat", "PullStrength1", "FlexHose",
        "Staerke des Pull-Vektors an LCS1 (rein numerischer "
        "Regularisierungsparameter, keine physikalische Groesse; "
        "0 = deaktiviert - Vorsicht, bei PullStrength1=PullStrength2=0 "
        "ist das Problem bei symmetrischen Randbedingungen "
        "unterbestimmt)", default=0.05)
    add("App::PropertyFloat", "PullStrength2", "FlexHose",
        "Staerke des Pull-Vektors an LCS2 (analog PullStrength1)",
        default=0.05)
    add("App::PropertyBool", "ShowControlPolygon", "FlexHose",
        "Zusaetzlich das Stuetzpunkt-Polygon der diskreten Loesung "
        "anzeigen (vor der Spline-Interpolation) - zur Fehlersuche bei "
        "Spitzen/Kniffen in der Kurve. Vor dem Erzeugen einer Extrusion "
        "(FlexHoseSolid) wieder ausschalten, da diese sonst nicht nur den "
        "Pfad, sondern auch das Debug-Polygon als Kante vorfindet.",
        default=False)
    add("App::PropertyVector", "_StartPoint", "FlexHoseIntern",
        "intern: Anfangspunkt des Pfads (fuer Extrusion)")
    add("App::PropertyVector", "_StartTangent", "FlexHoseIntern",
        "intern: Anfangstangente des Pfads (fuer Extrusion)")
    add("App::PropertyBool", "SkipIfUnchanged", "FlexHose",
        "Performance-Option: teure Neuberechnung ueberspringen, wenn sich "
        "die relevanten Eingaben (Platzierungen, Parameter) seit der "
        "letzten Berechnung nicht geaendert haben. VORSICHT: kann bei "
        "asynchron arbeitenden Assembly-Loesern zu FAELSCHLICH "
        "uebersprungenen Aktualisierungen fuehren, wenn die ausgelesene "
        "Platzierung zum Zeitpunkt der Berechnung noch veraltet ist "
        "(Loeser noch nicht fertig) - Default False (immer neu "
        "berechnen), nur aktivieren wenn Performance kritischer ist als "
        "garantierte Aktualitaet.", default=False)
    add("App::PropertyString", "_LastSignature", "FlexHoseIntern",
        "intern: Signatur der Eingabewerte der letzten erfolgreichen "
        "Berechnung - erlaubt, eine teure Neuberechnung zu ueberspringen, "
        "wenn sich tatsaechlich nichts Relevantes geaendert hat (z.B. bei "
        "einem breiten Dokument-Recompute in einer grossen Assembly)")
    for pname in ("_StartPoint", "_StartTangent", "_LastSignature"):
        obj.setEditorMode(pname, 1)  # 1 = read-only (sichtbar, nicht editierbar)

    # Migration/Aufraeumen: alte Regularization*-Properties (fruehere
    # Namensgebung, teils schon durch RegularizationAngle1/2 abgeloest,
    # teils - RegularizationAngle ohne Ziffer - laengst unbenutzter
    # Ueberrest einer noch frueheren Version) an Bestandsobjekten in die
    # neuen Pull*-Properties uebernehmen und danach ENTFERNEN
    # (obj.removeProperty) statt nur ungenutzt liegen zu lassen.
    if hasattr(obj, "RegularizationAngle1"):
        obj.PullAngle1 = obj.RegularizationAngle1
        obj.removeProperty("RegularizationAngle1")
    if hasattr(obj, "RegularizationAngle2"):
        obj.PullAngle2 = obj.RegularizationAngle2
        obj.removeProperty("RegularizationAngle2")
    if hasattr(obj, "RegularizationStrength"):
        obj.PullStrength1 = obj.RegularizationStrength
        obj.PullStrength2 = obj.RegularizationStrength
        obj.removeProperty("RegularizationStrength")
    if hasattr(obj, "RegularizationAngle"):
        obj.removeProperty("RegularizationAngle")


def resolve_lcs_placement(linksub):
    """Loest die Placement eines (topobj, subnames)-Linksub-Tupels auf, wie
    es get_selected_linksub()/LCS1/LCS2 liefern. Modul-Funktion (nicht mehr
    in FlexHosePath.execute() verschachtelt), damit sie auch ausserhalb
    (z.B. im Taskpanel fuer die Abstandsanzeige) wiederverwendet werden
    kann."""
    topobj, subnames = linksub[0], linksub[1]
    if not subnames:
        try:
            return topobj.getGlobalPlacement()
        except AttributeError:
            return topobj.Placement
    pl = topobj.getSubObject(subnames[0], retType=3)  # 3 = Placement
    if pl is None:
        App.Console.PrintWarning(
            "resolve_lcs_placement(): getSubObject() konnte '%s' nicht "
            "aufloesen, falle auf Placement des Endobjekts zurueck.\n"
            % subnames[0])
        try:
            return topobj.getGlobalPlacement()
        except AttributeError:
            return topobj.Placement
    return pl


class FlexHosePath:
    def __init__(self, obj):
        obj.Proxy = self
        _ensure_flexhosepath_properties(obj)

    def execute(self, obj):
        if not obj.LCS1 or not obj.LCS2:
            return

        _t = _profile_start()
        pl1 = resolve_lcs_placement(obj.LCS1)
        pl2 = resolve_lcs_placement(obj.LCS2)
        _profile_log("Platzierungsaufloesung LCS1+LCS2", _t)

        p0 = pl1.Base
        p3 = pl2.Base

        # Rohe Z-Achsen-Richtung beider LCS. FlipStart/FlipEnd korrigieren
        # HIER, VOR der Aufteilung in Einsteckrichtung und Bogenlaengen-
        # Tangente, welche Richtung ueberhaupt "nach aussen" bedeutet (falls
        # bei einem LCS die Z-Achse tatsaechlich ins Bauteil hinein statt
        # heraus zeigt). Beide abgeleiteten Groessen bleiben so zwangslaeufig
        # konsistent zueinander - Flip NACH der Aufteilung anzuwenden (wie in
        # einer frueheren Version) entkoppelt Einsteckgerade und Tangente
        # voneinander und erzeugt einen 180-Grad-Knick am Uebergang.
        raw_t0 = pl1.Rotation.multVec(App.Vector(0, 0, 1))
        raw_t3 = pl2.Rotation.multVec(App.Vector(0, 0, 1))
        if obj.FlipStart:
            raw_t0 = -raw_t0
        if obj.FlipEnd:
            raw_t3 = -raw_t3

        # t0_out/t3_out: Einsteckrichtung, nach der Flip-Korrektur IMMER vom
        # Bauteil weg - bestimmt geometrisch wo p0_free/p3_free liegen und
        # wie die starren Einsteckstrecken verlaufen.
        t0_out = raw_t0
        t3_out = raw_t3

        # t0_bc/t3_bc: Tangente des Schlauchs in Bogenlaengen-Richtung (s
        # laeuft von LCS1 nach LCS2), wie sie dem Loeser/der Interpolation
        # als Randbedingung vorgegeben wird. Strukturell IMMER am Anfang
        # gleichsinnig zu t0_out (der Schlauch verlaesst den ersten Stutzen
        # in Steckrichtung), aber am Ende GEGENsinnig zu t3_out (der Schlauch
        # kommt von aussen an und steckt hinein) - unabhaengig von einer
        # etwaigen Bauteil-Symmetrie, und automatisch konsistent mit der
        # (ggf. geflippten) Einsteckrichtung.
        t0_bc = t0_out
        t3_bc = -t3_out

        obj._StartPoint = p0
        obj._StartTangent = t0_out

        ins1 = _resolve_insertion_length(obj.LCS1, obj.InsertionLength1.Value)
        ins2 = _resolve_insertion_length(obj.LCS2, obj.InsertionLength2.Value)

        # Selbst-Erkennung: teure Berechnung (Stabketten-Loeser + Spline)
        # ueberspringen, wenn sich seit der letzten erfolgreichen Berechnung
        # nichts Relevantes geaendert hat - wichtig in grossen Assemblies,
        # wo ein Dokument-weiter Recompute viele Objekte "beruehrt", auch
        # wenn deren tatsaechliche Eingaben (Platzierungen, Parameter)
        # unveraendert sind.
        signature = repr((
            _placement_signature(pl1), _placement_signature(pl2),
            round(obj.Length.Value, 6), round(ins1, 6), round(ins2, 6),
            bool(obj.FlipStart), bool(obj.FlipEnd), int(obj.Segments),
            round(float(obj.PullAngle1.getValueAs("rad")), 8),
            round(float(obj.PullAngle2.getValueAs("rad")), 8),
            round(obj.PullStrength1, 8), round(obj.PullStrength2, 8),
            bool(obj.ShowControlPolygon)))
        if obj.SkipIfUnchanged and not PROFILE and signature == obj._LastSignature and not obj.Shape.isNull():
            return  # nichts Relevantes geaendert - vorhandene Shape behalten

        p0_free = p0 + t0_out * ins1
        p3_free = p3 + t3_out * ins2

        free_target_length = obj.Length.Value - ins1 - ins2
        straight_dist = (p3_free - p0_free).Length

        if free_target_length <= 1e-6:
            App.Console.PrintWarning(
                "FlexHosePath: Length ist kleiner/gleich der Summe der "
                "Einstecklaengen - kein Platz fuer einen freien Bogen.\n")
            return
        if free_target_length < straight_dist - 1e-6:
            App.Console.PrintWarning(
                "FlexHosePath: Length ist kuerzer als der direkte Abstand "
                "der Einsteckenden - keine Loesung moeglich.\n")
            return

        p0_np = np.array([p0_free.x, p0_free.y, p0_free.z])
        p3_np = np.array([p3_free.x, p3_free.y, p3_free.z])
        t0_np = np.array([t0_bc.x, t0_bc.y, t0_bc.z])
        t3_np = np.array([t3_bc.x, t3_bc.y, t3_bc.z])
        t0_np /= np.linalg.norm(t0_np)
        t3_np /= np.linalg.norm(t3_np)

        # Dreieckslast statt raumfestem globalem Vektor: Richtung an JEDEM
        # Ende wird deterministisch aus der jeweiligen LCS-Orientierung
        # abgeleitet (lokale X-Achse, um die lokale Z-Achse um
        # PullAngle1/2 gedreht) - haengt NUR vom aktuellen
        # Assembly-Zustand ab, nie von der Historie. Ersetzt den fruaheren
        # Ansatz (ein raumfester Vektor aus der Verbindungsachse via
        # _perp_basis + Kontinuitaets-Korrektur), der bei gleicher
        # Assembly-Stellung je nach vorheriger Position zu unterschiedlichen
        # Ergebnissen fuehren konnte - nicht reproduzierbar, siehe Skill.
        local_x1 = pl1.Rotation.multVec(App.Vector(1, 0, 0))
        local_y1 = pl1.Rotation.multVec(App.Vector(0, 1, 0))
        local_x2 = pl2.Rotation.multVec(App.Vector(1, 0, 0))
        local_y2 = pl2.Rotation.multVec(App.Vector(0, 1, 0))
        angle1 = float(obj.PullAngle1.getValueAs("rad"))
        angle2 = float(obj.PullAngle2.getValueAs("rad"))
        v1 = np.cos(angle1) * np.array([local_x1.x, local_x1.y, local_x1.z]) \
            + np.sin(angle1) * np.array([local_y1.x, local_y1.y, local_y1.z])
        v2 = np.cos(angle2) * np.array([local_x2.x, local_x2.y, local_x2.z]) \
            + np.sin(angle2) * np.array([local_y2.x, local_y2.y, local_y2.z])
        load1 = obj.PullStrength1 * v1
        load2 = obj.PullStrength2 * v2

        n_final = max(2, int(obj.Segments))
        # auf naechste Zweierpotenz aufrunden (Verfeinerung verdoppelt jeweils)
        n_final = 1 << (n_final - 1).bit_length()

        try:
            _t = _profile_start()
            chain, result = solve_rod_chain(
                p0_np, t0_np, p3_np, t3_np, free_target_length,
                load1, load2, n_final=n_final)
            _profile_log("solve_rod_chain", _t)
        except Exception as exc:
            App.Console.PrintError(
                "FlexHosePath: Stabketten-Loeser fehlgeschlagen: %s\n" % exc)
            return

        if not result.success:
            App.Console.PrintWarning(
                "FlexHosePath: Energie-Minimierung nicht sauber konvergiert "
                "(%s) - Ergebnis ggf. ungenau.\n" % result.message)

        vectors = [App.Vector(p[0], p[1], p[2]) for p in chain]

        App.Console.PrintMessage(
            "FlexHosePath: Knoten der diskreten Loesung (p0..p_N):\n")
        for i, v in enumerate(vectors):
            App.Console.PrintMessage(
                "  [%2d] %.3f, %.3f, %.3f\n" % (i, v.x, v.y, v.z))

        edges = []
        if ins1 > 1e-9:
            edges.append(Part.LineSegment(p0, p0_free).toShape())

        bspline = Part.BSplineCurve()
        # Ohne Tangentenvorgabe an den Zwischenknoten hat der globale
        # Interpolations-Loeser (nur 2 von N+1 Punkten mit fester Tangente)
        # zu viel Freiheit in der Steigungswahl dazwischen und neigt bei
        # wechselnder Kruemmung des Stabpolygons zum Ueberschwingen (sichtbare
        # Schleifen/Ausbeulungen ueber das Polygon hinaus). Deshalb an jedem
        # Zwischenknoten die Richtung per zentralem Differenzenquotient (Catmull-
        # Rom-artig) vorgeben - haelt die Spline deutlich naeher am Polygon.
        tangent_vectors = [App.Vector(0, 0, 0)] * len(vectors)
        tangent_flags = [True] * len(vectors)
        tangent_vectors[0] = t0_bc
        tangent_vectors[-1] = t3_bc
        for i in range(1, len(vectors) - 1):
            d = vectors[i + 1] - vectors[i - 1]
            if d.Length > 1e-9:
                d.normalize()
            tangent_vectors[i] = d
        _t = _profile_start()
        bspline.interpolate(Points=vectors, Tangents=tangent_vectors,
                             TangentFlags=tangent_flags)
        _profile_log("BSpline-Interpolation", _t)
        edges.append(bspline.toShape())

        if ins2 > 1e-9:
            edges.append(Part.LineSegment(p3_free, p3).toShape())

        # IMMER als Part.Wire verpacken, auch bei nur einer Kante (z.B. wenn
        # beide Einstecklaengen 0 sind) - sonst waere Shape ein blankes Edge
        # ohne Wires, und FlexHoseSolid.execute() wuerde faelschlich "0
        # Wires" melden und auf ShowControlPolygon als Ursache tippen, obwohl
        # das gar nicht der Grund ist.
        hose_wire = Part.Wire(edges)

        if obj.ShowControlPolygon:
            # Stuetzpunkt-Polygon der diskreten Loesung (vor der Spline-
            # Interpolation) als Vergleichsgeometrie mit anzeigen - zeigt,
            # ob eine sichtbare Spitze schon in der diskreten Loesung steckt
            # oder erst durch die Spline-Interpolation entsteht.
            polygon = Part.makePolygon(vectors)
            obj.Shape = Part.Compound([hose_wire, polygon])

            # Zwei Pfeile fuer die Dreieckslast-Richtungen an LCS1 (v1, rot)
            # und LCS2 (v2, gruen) - als separate Hilfsobjekte, damit sie
            # unterschiedliche Farben/Linienstaerken bekommen koennen (ein
            # einzelnes Compound kann Kanten nicht zuverlaessig einzeln
            # einfaerben).
            arrow_len = 0.25 * free_target_length
            _update_debug_arrow(obj.Document, obj.Name + "_Pfeil1",
                                 p0_np, v1, arrow_len,
                                 (1.0, 0.0, 0.0), True)
            _update_debug_arrow(obj.Document, obj.Name + "_Pfeil2",
                                 p3_np, v2, arrow_len,
                                 (0.0, 0.6, 0.0), True)
        else:
            obj.Shape = hose_wire
            # Vorhandene Pfeil-Hilfsobjekte nur ausblenden (nicht loeschen -
            # loeschen aus execute() heraus ist riskant/nicht empfohlen).
            for suffix in ("_Pfeil1", "_Pfeil2"):
                arrow_obj = obj.Document.getObject(obj.Name + suffix)
                if arrow_obj is not None:
                    arrow_obj.ViewObject.Visibility = False

        obj._LastSignature = signature


class ViewProviderFlexHosePath:
    def __init__(self, vobj):
        vobj.Proxy = self

    def getIcon(self):
        return ":/icons/Part_Spiral.svg"

    def attach(self, vobj):
        self.ViewObject = vobj
        self.Object = vobj.Object

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


def _update_debug_arrow(doc, name, base_np, dir_np, length, color, visible):
    """Legt ein Part::Feature-Hilfsobjekt mit gegebenem Namen an (falls
    noch nicht vorhanden) und aktualisiert dessen Shape/Farbe/Sichtbarkeit -
    fuer einen einzeln einfaerbbaren, dickeren Debug-Pfeil (ein einzelnes
    Compound aus Kanten kann in FreeCAD nicht zuverlaessig teilweise
    eingefaerbt werden, deshalb ein eigenes Objekt pro Pfeil)."""
    arrow_obj = doc.getObject(name)
    if arrow_obj is None:
        arrow_obj = doc.addObject("Part::Feature", name)
        arrow_obj.ViewObject.LineColor = color
        arrow_obj.ViewObject.LineWidth = 4.0
        arrow_obj.ViewObject.PointSize = 6.0
    edges = _make_arrow_edges(base_np, dir_np, length)
    if edges:
        arrow_obj.Shape = Part.Compound(edges)
    arrow_obj.ViewObject.LineColor = color  # falls extern veraendert
    arrow_obj.ViewObject.Visibility = visible
    return arrow_obj


def _make_arrow_edges(base_np, dir_np, length):
    """Baut die Kanten eines einfachen Pfeils (Schaft + zwei kurze
    Spitzen-Schraegen) fuer die Debug-Visualisierung, beginnend bei
    `base_np` in Richtung `dir_np` (muss nicht normiert sein - wird hier
    normiert, nur die Richtung zaehlt fuer die Anzeige)."""
    n = np.linalg.norm(dir_np)
    if n < 1e-12:
        return []
    d = dir_np / n
    base_pt = App.Vector(base_np[0], base_np[1], base_np[2])
    tip_np = base_np + d * length
    tip_pt = App.Vector(tip_np[0], tip_np[1], tip_np[2])
    shaft = Part.LineSegment(base_pt, tip_pt).toShape()
    back = (tip_pt - base_pt)
    back.multiply(0.8)
    back = base_pt + back
    perp1, _ = _perp_basis(d)
    head_len = length * 0.15
    h1 = Part.LineSegment(tip_pt, back + App.Vector(*(perp1 * head_len))).toShape()
    h2 = Part.LineSegment(tip_pt, back + App.Vector(*(-perp1 * head_len))).toShape()
    return [shaft, h1, h2]


def _shape_signature(shape, ndigits=6):
    """Guenstiger Fingerabdruck einer Shape (Bounding Box + Laenge + Anzahl
    Vertices) fuer den Signatur-Vergleich in FlexHoseSolid.execute() -
    bewusst KEIN echter Geometrie-Hash (unsichere API-Verfuegbarkeit ueber
    FreeCAD-Versionen hinweg), aber ausreichend, um "Pfad hat sich nicht
    geaendert" zuverlaessig von echten Aenderungen zu unterscheiden."""
    bb = shape.BoundBox
    return (round(bb.XMin, ndigits), round(bb.XMax, ndigits),
            round(bb.YMin, ndigits), round(bb.YMax, ndigits),
            round(bb.ZMin, ndigits), round(bb.ZMax, ndigits),
            round(shape.Length, ndigits), len(shape.Vertexes))


def _ensure_flexhosesolid_properties(obj):
    """Analog zu _ensure_flexhosepath_properties() fuer FlexHoseSolid."""
    def add(ptype, name, group, doc, default=None):
        if not hasattr(obj, name):
            obj.addProperty(ptype, name, group, doc)
            if default is not None:
                setattr(obj, name, default)
            return True
        return False

    add("App::PropertyLink", "PathObject", "FlexHoseSolid",
        "Referenz auf das FlexHosePath-Objekt (Mittellinie)")
    add("App::PropertyLength", "OuterDiameter", "FlexHoseSolid",
        "Aussendurchmesser des Schlauchs", default=4.0)
    add("App::PropertyLength", "WallThickness", "FlexHoseSolid",
        "Wandstaerke (nur wirksam, wenn Hollow=True - Innendurchmesser "
        "= Aussen - 2x Wandstaerke)", default=0.5)
    add("App::PropertyBool", "Hollow", "FlexHoseSolid",
        "Schlauch als Hohlkoerper (mit Innenflaeche) statt massiv "
        "erzeugen. Kostet einen zusaetzlichen Booleschen Schnitt (laut "
        "Profiling 0.2-3s je Schlauch, dominanter Kostenfaktor bei vielen "
        "Schlaeuchen) - Default False (massiv) fuer Performance bei "
        "grossen Assemblies; bei Bedarf fuer ein realistischeres Bild "
        "einzelner Schlaeuche auf True setzen.", default=False)
    add("App::PropertyBool", "SkipIfUnchanged", "FlexHoseSolid",
        "Performance-Option: teuren Sweep/Schnitt ueberspringen, wenn "
        "sich der Pfad/die Parameter seit der letzten Berechnung nicht "
        "geaendert haben. VORSICHT: siehe gleichnamige Property an "
        "FlexHosePath - kann bei asynchron arbeitenden Assembly-Loesern "
        "zu faelschlich uebersprungenen Aktualisierungen fuehren. "
        "Default False.", default=False)
    add("App::PropertyString", "_LastSignature", "FlexHoseIntern",
        "intern: Signatur der letzten erfolgreichen Berechnung, um "
        "unnoetige Sweeps/Booleans zu vermeiden, wenn sich der Pfad "
        "tatsaechlich nicht geaendert hat")
    if hasattr(obj, "_LastSignature"):
        obj.setEditorMode("_LastSignature", 1)


class FlexHoseSolid:
    """Hohlkoerper-Extrusion (Rohr) entlang eines FlexHosePath-Pfads.
    Getrenntes Objekt, das per Link auf den Pfad verweist - der Pfad bleibt
    unabhaengig editierbar/verschiebbar, der Koerper aktualisiert sich beim
    naechsten recompute() automatisch mit."""

    def __init__(self, obj):
        obj.Proxy = self
        _ensure_flexhosesolid_properties(obj)

    def execute(self, obj):
        path_obj = obj.PathObject
        if path_obj is None:
            App.Console.PrintError(
                "FlexHoseSolid: PathObject ist nicht gesetzt.\n")
            return
        if not hasattr(path_obj, "Shape") or path_obj.Shape is None \
                or path_obj.Shape.isNull():
            App.Console.PrintError(
                "FlexHoseSolid: PathObject '%s' hat noch keine gueltige "
                "Shape (erst recompute() am Pfad-Objekt ausfuehren).\n"
                % path_obj.Name)
            return

        shape = path_obj.Shape
        wires = shape.Wires
        if len(wires) != 1:
            App.Console.PrintError(
                "FlexHoseSolid: PathObject.Shape enthaelt %d Wires statt "
                "genau 1. Falls '%s.ShowControlPolygon' auf True steht "
                "(Debug-Polygon zusaetzlich in der Shape), erst auf False "
                "setzen und neu berechnen. Andernfalls Report-Ansicht beim "
                "Neuberechnen von '%s' selbst auf Warnungen pruefen.\n"
                % (len(wires), path_obj.Name, path_obj.Name))
            return
        path_wire = wires[0]

        signature = repr((
            _shape_signature(path_wire), round(obj.OuterDiameter.Value, 6),
            round(obj.WallThickness.Value, 6), bool(obj.Hollow)))
        if obj.SkipIfUnchanged and not PROFILE and signature == obj._LastSignature and not obj.Shape.isNull():
            return  # Pfad/Parameter unveraendert - vorhandenen Koerper behalten

        App.Console.PrintMessage(
            "FlexHoseSolid: Pfad hat %d Kanten, Laenge %.2f mm.\n"
            % (len(path_wire.Edges), path_wire.Length))

        start_point = path_obj._StartPoint
        start_tangent = path_obj._StartTangent

        outer_r = obj.OuterDiameter.Value / 2.0
        wall = obj.WallThickness.Value
        inner_r = outer_r - wall
        if obj.Hollow and inner_r <= 1e-6:
            App.Console.PrintWarning(
                "FlexHoseSolid: Wandstaerke >= Aussenradius - kein "
                "Hohlraum moeglich.\n")
            return

        outer_circle = Part.Wire([Part.makeCircle(
            outer_r, start_point, start_tangent)])
        App.Console.PrintMessage(
            "FlexHoseSolid: Profile bei %s, Tangente %s, Aussenradius %.2f"
            "%s.\n" % (start_point, start_tangent, outer_r,
                       (", Innenradius %.2f" % inner_r) if obj.Hollow else
                       " (massiv)"))

        if not obj.Hollow:
            # Schneller Standardpfad: nur der Aussenkreis wird gesweept, kein
            # Innenkreis, kein Boolescher Schnitt - laut Profiling ist genau
            # dieser Schnitt bei vielen Schlaeuchen der dominante
            # Kostenfaktor (0.2-3s je Schlauch). Massiv statt hohl ist bei
            # sichtbarer Groessenordnung (wenige mm Durchmesser) visuell
            # kaum unterscheidbar, aber deutlich schneller.
            try:
                _t = _profile_start()
                result = path_wire.makePipeShell([outer_circle], True, False)
                _profile_log("Massiv-Sweep", _t)
                App.Console.PrintMessage(
                    "FlexHoseSolid: Massiv-Sweep ok, Volumen=%.2f, "
                    "valid=%s.\n" % (result.Volume, result.isValid()))
            except Exception as exc:
                App.Console.PrintError(
                    "FlexHoseSolid: Massiv-Sweep fehlgeschlagen: %s\n" % exc)
                return
            obj.Shape = result
            obj._LastSignature = signature
            return

        # Hollow=True: Hohlkoerper - zuerst Ring-Sweep (ein Aufruf, kein
        # Boolescher Schnitt) versuchen, bei Fehlschlag auf den bewaehrten
        # Zwei-Sweep+Schnitt-Weg zurueckfallen.
        inner_circle = Part.Wire([Part.makeCircle(
            inner_r, start_point, start_tangent)])

        try:
            # WICHTIG: Part.makeCircle() erzeugt IMMER CCW-Orientierung
            # (siehe eitech-freecad-workbench-Skill) - damit OCCs MakeSolid()
            # den Innenkreis als Loch statt als zweite Aussenkontur erkennt,
            # muss er GEGENSINNIG zum Aussenkreis orientiert sein. Deshalb
            # hier explizit umkehren. (Hat den bekannten "MakeSolid"-Fehler
            # allein nicht behoben - Ring-Sweep bleibt experimentell, daher
            # der Fallback.)
            inner_circle_rev = inner_circle.reversed()
            _t = _profile_start()
            ring_solid = path_wire.makePipeShell(
                [outer_circle, inner_circle_rev], True, False)
            _profile_log("Ring-Sweep (Aussen+Innen in einem Zug)", _t)
            if ring_solid is None or ring_solid.isNull() \
                    or not ring_solid.isValid():
                raise ValueError(
                    "Ring-Sweep lieferte keine gueltige Shape "
                    "(None/Null/invalid)")
            result = ring_solid
            App.Console.PrintMessage(
                "FlexHoseSolid: Ring-Sweep ok, Volumen=%.2f, valid=%s.\n"
                % (result.Volume, result.isValid()))
        except Exception as exc:
            App.Console.PrintWarning(
                "FlexHoseSolid: Ring-Sweep fehlgeschlagen (%s) - falle "
                "zurueck auf Sweep+Sweep+Booleschen Schnitt.\n" % exc)
            try:
                _t = _profile_start()
                outer_solid = path_wire.makePipeShell(
                    [outer_circle], True, False)
                _profile_log("Aussen-Sweep (Fallback)", _t)
                App.Console.PrintMessage(
                    "FlexHoseSolid: Aussen-Sweep ok, Volumen=%.2f, "
                    "valid=%s.\n"
                    % (outer_solid.Volume, outer_solid.isValid()))
                _t = _profile_start()
                inner_solid = path_wire.makePipeShell(
                    [inner_circle], True, False)
                _profile_log("Innen-Sweep (Fallback)", _t)
                App.Console.PrintMessage(
                    "FlexHoseSolid: Innen-Sweep ok, Volumen=%.2f, "
                    "valid=%s.\n"
                    % (inner_solid.Volume, inner_solid.isValid()))
                _t = _profile_start()
                result = outer_solid.cut(inner_solid)
                _profile_log("Boolescher Schnitt (Fallback)", _t)
                App.Console.PrintMessage(
                    "FlexHoseSolid: Boolescher Schnitt ok, Volumen=%.2f, "
                    "valid=%s, isNull=%s.\n"
                    % (result.Volume, result.isValid(), result.isNull()))
            except Exception as exc2:
                App.Console.PrintError(
                    "FlexHoseSolid: Sweep/Boolescher Schnitt (Fallback) "
                    "ebenfalls fehlgeschlagen: %s\n" % exc2)
                return

        obj.Shape = result
        obj._LastSignature = signature


class ViewProviderFlexHoseSolid:
    def __init__(self, vobj):
        vobj.Proxy = self

    def getIcon(self):
        return ":/icons/Part_Tube.svg"

    def attach(self, vobj):
        self.ViewObject = vobj
        self.Object = vobj.Object
        vobj.Transparency = 50
        vobj.ShapeColor = (0.8549, 0.898, 0.9373)  # #dae5ef
        # "Shaded" existiert bei diesem ViewProvider nicht als eigener
        # DisplayMode (nur "Flat Lines" u.ae., je nach FreeCAD-Version) -
        # stattdessen die Kanten "verstecken", indem ihre Farbe der
        # Flaechenfarbe angeglichen wird (verschmilzt visuell), plus - falls
        # in dieser FreeCAD-Version vorhanden - eine eigene Kanten-
        # Transparenz setzen.
        vobj.LineColor = vobj.ShapeColor
        try:
            vobj.LineTransparency = 100
        except Exception:
            pass  # aeltere FreeCAD-Versionen kennen LineTransparency nicht

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


def make_flex_hose_solid(path_obj, outer_diameter=4.0, wall_thickness=0.5,
                          hollow=False, color=None, transparency=None,
                          name="SchlauchKoerper"):
    doc = App.ActiveDocument
    obj = doc.addObject("Part::FeaturePython", name)
    FlexHoseSolid(obj)
    ViewProviderFlexHoseSolid(obj.ViewObject)
    obj.PathObject = path_obj
    obj.OuterDiameter = outer_diameter
    obj.WallThickness = wall_thickness
    obj.Hollow = hollow
    if color is not None:
        obj.ViewObject.ShapeColor = color
        obj.ViewObject.LineColor = color
    if transparency is not None:
        obj.ViewObject.Transparency = transparency
    doc.recompute()
    # Der rohe Pfad ist nur noch als Berechnungsgrundlage interessant, nicht
    # mehr zur Anzeige - sobald ein Koerper existiert, ausblenden.
    try:
        path_obj.ViewObject.Visibility = False
    except Exception:
        pass
    return obj


# ---------------------------------------------------------------------------
# Starre Zwischenstueck-Haelften: gerade Rohrstuecke mit GENAU EINEM LCS_tube
# am freien Ende (Einstecklaenge 0 gedacht), das gegenueberliegende Ende ist
# eine plane Stirnflaeche ohne LCS. Bewusst als ZWEI separate Haelften-
# Bauteile konzipiert (nicht ein Bauteil mit zwei LCS_tube-Enden), weil
# unsere gesamte Auswahl-/Erkennungslogik (get_selected_linksub,
# _find_child_lcs, LCS_LABEL_HINTS) implizit "ein Bauteil = ein relevantes
# LCS" voraussetzt. Die feste Verbindung der beiden Haelften untereinander
# und zu den Nippeln erfolgt bewusst NICHT automatisiert hier, sondern
# manuell ueber Gelenke in der Assembly-Werkbank.
# ---------------------------------------------------------------------------

def _ensure_rigidsegmenthalf_properties(obj):
    def add(ptype, name, group, doc, default=None):
        if not hasattr(obj, name):
            obj.addProperty(ptype, name, group, doc)
            if default is not None:
                setattr(obj, name, default)
            return True
        return False

    add("App::PropertyLength", "Length", "RigidHoseSegment",
        "Laenge dieser Haelfte (Stirnflaeche bei 0 bis LCS_tube bei "
        "Length)", default=50.0)
    add("App::PropertyLength", "OuterDiameter", "RigidHoseSegment",
        "Aussendurchmesser (wie beim flexiblen Schlauch)", default=4.0)
    add("App::PropertyLength", "WallThickness", "RigidHoseSegment",
        "Wandstaerke", default=0.5)
    add("App::PropertyLink", "LCSObject", "RigidHoseSegment",
        "Das zugehoerige LCS_tube-Objekt am freien Ende (Platzierung wird "
        "hier automatisch mitgefuehrt)")


class RigidHoseSegmentHalf:
    """Starres, gerades Rohrstueck (eine Haelfte eines Zwischenstuecks) mit
    genau einem LCS_tube am freien (aeusseren) Ende - Z-Achse zeigt weiter
    nach aussen, wie bei den flexiblen Anschluessen. Das Ende bei Z=0 ist
    eine einfache plane Stirnflaeche ohne LCS, gedacht zum manuellen
    Verbinden (Fastened-Joint) mit der Zwillingshaelfte bzw. einem Nippel
    in der Assembly-Werkbank."""

    def __init__(self, obj):
        obj.Proxy = self
        _ensure_rigidsegmenthalf_properties(obj)

    def execute(self, obj):
        length = obj.Length.Value
        outer_r = obj.OuterDiameter.Value / 2.0
        wall = obj.WallThickness.Value
        inner_r = outer_r - wall

        if length <= 1e-6 or inner_r <= 1e-6:
            App.Console.PrintWarning(
                "RigidHoseSegmentHalf: ungueltige Abmessungen (Length=%.2f, "
                "Aussenradius=%.2f, Wandstaerke=%.2f) - keine Geometrie "
                "erzeugt.\n" % (length, outer_r, wall))
            return

        outer = Part.makeCylinder(outer_r, length)
        inner = Part.makeCylinder(inner_r, length)
        obj.Shape = outer.cut(inner)

        if obj.LCSObject is not None:
            obj.LCSObject.Placement = App.Placement(
                App.Vector(0.0, 0.0, length), App.Rotation())


class ViewProviderRigidHoseSegmentHalf:
    def __init__(self, vobj):
        vobj.Proxy = self

    def getIcon(self):
        return ":/icons/Part_Tube.svg"

    def attach(self, vobj):
        self.ViewObject = vobj
        self.Object = vobj.Object
        vobj.ShapeColor = (0.8549, 0.898, 0.9373)  # #dae5ef, wie der Schlauch
        vobj.Transparency = 50  # wie beim flexiblen Schlauch

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


def make_hose_segment_half(length, outer_diameter=4.0, wall_thickness=0.5,
                            name="Zwischenstueck"):
    """Erzeugt EIN Zwischenstueck (trotz Funktionsname historisch "Haelfte"
    genannt - kann auch als vollstaendiges, einzelnes Teil verwendet werden,
    siehe make_straight_hose_segment() fuer die Zwei-Teile-Variante): einen
    App::Part-Container mit dem Rohr-Koerper (Part::FeaturePython) und
    einem eigenen LCS_tube-Objekt (PartDesign::CoordinateSystem) am freien
    Ende. UNGETESTET, ob ein PartDesign::CoordinateSystem ausserhalb eines
    PartDesign::Body zuverlaessig funktioniert - bitte beim ersten Aufruf
    pruefen, ob es ohne Fehler erzeugt wird und eine sinnvolle Placement
    zeigt."""
    doc = App.ActiveDocument

    container = doc.addObject("App::Part", name)
    container.Label = name

    tube = doc.addObject("Part::FeaturePython", name + "_Rohr")
    RigidHoseSegmentHalf(tube)
    ViewProviderRigidHoseSegmentHalf(tube.ViewObject)
    # Farbe/Transparenz zusaetzlich explizit setzen (nicht nur in attach()) -
    # bei Objekten innerhalb eines App::Part-Containers hat sich attach()
    # allein als nicht zuverlaessig genug erwiesen (Farbe blieb Standard-grau).
    tube.ViewObject.ShapeColor = (0.8549, 0.898, 0.9373)  # #dae5ef
    tube.ViewObject.Transparency = 50

    lcs = doc.addObject("PartDesign::CoordinateSystem", name + "_LCS")
    lcs.Label = "LCS_tube"

    tube.LCSObject = lcs
    tube.Length = length
    tube.OuterDiameter = outer_diameter
    tube.WallThickness = wall_thickness

    container.Group = [tube, lcs]
    doc.recompute()
    return container


def make_straight_hose_segment(total_length, outer_diameter=4.0,
                                wall_thickness=0.5, name="Zwischenstueck"):
    """Erzeugt ein starres, gerades Zwischenstueck als ZWEI separate
    Haelften-Bauteile (je total_length/2, je ein eigenes LCS_tube) - siehe
    Klassendocstring von RigidHoseSegmentHalf fuer den Grund. Beide
    Haelften werden zur ersten Sichtkontrolle direkt aneinandergesetzt;
    die tatsaechliche feste Verbindung (untereinander und zu den Nippeln)
    erfolgt manuell ueber Gelenke in der Assembly-Werkbank."""
    half_length = total_length / 2.0
    half_a = make_hose_segment_half(half_length, outer_diameter,
                                     wall_thickness, name + "A")
    half_b = make_hose_segment_half(half_length, outer_diameter,
                                     wall_thickness, name + "B")
    half_b.Placement = App.Placement(App.Vector(0.0, 0.0, half_length),
                                      App.Rotation())
    App.ActiveDocument.recompute()
    return half_a, half_b


def make_flex_hose(name, lcs1, lcs2, length, ins1=0.0, ins2=0.0):
    doc = App.ActiveDocument
    obj = doc.addObject("Part::FeaturePython", name)
    FlexHosePath(obj)
    ViewProviderFlexHosePath(obj.ViewObject)
    obj.LCS1 = lcs1
    obj.LCS2 = lcs2
    obj.Length = length
    obj.InsertionLength1 = ins1
    obj.InsertionLength2 = ins2
    doc.recompute()
    return obj


# Bevorzugtes Label fuer das schlauch-relevante LCS, falls ein Bauteil
# mehrere Koordinatensysteme enthaelt (z.B. zusaetzlich ein generisches
# "Local_CS" des Bodys/Ursprungs). Bei Bedarf anpassen/erweitern.
LCS_LABEL_HINTS = ["LCS_tube"]


def _collect_lcs_candidates(obj, _depth=0, _seen=None, results=None):
    """Sammelt rekursiv (bis Tiefe 4) ALLE PartDesign::CoordinateSystem-
    Objekte im Teilbaum - nicht nur das erste gefundene, damit anschliessend
    nach Label ausgewaehlt werden kann."""
    if results is None:
        results = []
    if _seen is None:
        _seen = set()
    if _depth > 4 or obj is None or id(obj) in _seen:
        return results
    _seen.add(id(obj))

    children = getattr(obj, "Group", None)
    if not children:
        children = getattr(obj, "OutList", [])
    for child in children:
        if getattr(child, "TypeId", "") == "PartDesign::CoordinateSystem":
            results.append(child)
    for child in children:
        _collect_lcs_candidates(child, _depth + 1, _seen, results)
    return results


def _find_child_lcs(obj):
    """Sucht das schlauch-relevante LCS im Teilbaum eines Objekts. Bei
    mehreren gefundenen Koordinatensystemen wird eines mit einem Label aus
    LCS_LABEL_HINTS bevorzugt (z.B. 'LCS_tube'); sonst Fallback auf das
    erste gefundene (mit Warnung, da dann ggf. das falsche getroffen wird -
    z.B. ein generisches 'Local_CS' statt des tatsaechlich gemeinten LCS)."""
    candidates = _collect_lcs_candidates(obj)
    if not candidates:
        return None
    for hint in LCS_LABEL_HINTS:
        for c in candidates:
            if c.Label == hint:
                return c
    if len(candidates) > 1:
        App.Console.PrintWarning(
            "FlexHosePath: %d Koordinatensysteme gefunden, keines davon "
            "mit Label aus %s - nehme das erste ('%s'). Falls falsch: "
            "Label anpassen oder LCS_LABEL_HINTS erweitern.\n"
            % (len(candidates), LCS_LABEL_HINTS, candidates[0].Label))
    return candidates[0]


def _rebind_proxy(obj, cls):
    """Versucht, obj.Proxy an `cls` zu binden. Normalfall (Proxy zeigt auf
    eine veraltete/andere Klasseninstanz aus einer frueheren exec()-
    Ausfuehrung): direkte Zuweisung reicht. Selteneres, schwereres Problem:
    wurde das Dokument geoeffnet BEVOR das Makro in dieser Sitzung geladen
    war, kann FreeCAD die Proxy-Property beim Laden komplett verwerfen
    (Objekt faellt in Python auf die generische App.DocumentObject-
    Basisklasse zurueck - `obj.Proxy = ...` schlaegt dann mit
    AttributeError fehl, nicht nur mit falscher Klasse). In diesem Fall
    wird zusaetzlich versucht, die Property explizit neu anzulegen -
    NICHT garantiert erfolgreich, siehe Rueckgabewert."""
    try:
        if not isinstance(getattr(obj, "Proxy", None), cls):
            obj.Proxy = cls.__new__(cls)
            obj.Proxy.__dict__ = {}
        return True
    except AttributeError:
        pass
    try:
        obj.addProperty("App::PropertyPythonObject", "Proxy")
        obj.Proxy = cls.__new__(cls)
        obj.Proxy.__dict__ = {}
        return True
    except Exception:
        return False


def upgrade_hose_objects():
    """Bringt bereits vorhandene SchlauchPfad-/SchlauchKoerper-Objekte
    (erzeugt mit einer aelteren Version dieses Skripts) auf den aktuellen
    Stand, OHNE sie neu zu erzeugen - alle bereits gesetzten Werte
    (Length, InsertionLength1/2, PullAngle1/2, PullStrength1/2, OuterDiameter, ...)
    bleiben erhalten.

    Macht pro erkanntem Objekt drei Dinge:
    1. Proxy-Klasse neu binden (falls die alte Klassendefinition aus einer
       frueheren exec()-Ausfuehrung stammt und nicht mehr existiert bzw.
       veraltet ist) - siehe _rebind_proxy() fuer den selteneren, schwereren
       Fall (Dokument vor dem Laden des Makros geoeffnet)
    2. Fehlende Properties ergaenzen (_ensure_flexhosepath_properties() /
       _ensure_flexhosesolid_properties() - idempotent, ueberschreibt keine
       vorhandenen Werte)
    3. Bei FlexHoseSolid zusaetzlich die aktuellen Anzeige-Einstellungen
       (Farbe, Transparenz, Linienfarbe) anwenden, da diese nur in
       attach() gesetzt werden, was bei Bestandsobjekten nicht automatisch
       erneut laeuft

    Erkennung erfolgt ueber die vorhandenen Properties (nicht ueber
    isinstance/TypeId), da bei einer alten/gebrochenen Proxy-Klassenbindung
    isinstance-Pruefungen nicht zuverlaessig funktionieren wuerden. Ein
    einzelnes nicht reparierbares Objekt bricht den Rest NICHT ab (try/
    except pro Objekt) - am Ende gibt es eine Sammelmeldung."""
    doc = App.ActiveDocument
    if doc is None:
        App.Console.PrintWarning("upgrade_hose_objects(): kein aktives "
                                  "Dokument.\n")
        return

    n_paths = 0
    n_solids = 0
    failed = []
    view_warnings = []
    for obj in doc.Objects:
        try:
            is_path = hasattr(obj, "LCS1") and hasattr(obj, "LCS2") and \
                hasattr(obj, "Length")
            is_solid = hasattr(obj, "PathObject") and hasattr(obj, "OuterDiameter")

            if is_path:
                if not _rebind_proxy(obj, FlexHosePath):
                    failed.append(obj.Name)
                    continue
                _ensure_flexhosepath_properties(obj)
                try:
                    if obj.ViewObject is not None and not isinstance(
                            getattr(obj.ViewObject, "Proxy", None),
                            ViewProviderFlexHosePath):
                        obj.ViewObject.Proxy = ViewProviderFlexHosePath.__new__(
                            ViewProviderFlexHosePath)
                except Exception as exc_view:
                    # Kommt vor, wenn das Objekt als Assembly-Komponente
                    # verwendet wird - FreeCAD ersetzt dessen ViewObject
                    # dann durch einen eigenen Gui.ViewProviderLink, der
                    # kein settable "Proxy" mehr kennt. NICHT fatal fuer
                    # die Geometrie/Adaptivitaet (die haengt nur an
                    # obj.Proxy, nicht an obj.ViewObject.Proxy) - deshalb
                    # hier nur vormerken, nicht den Rest des Objekts
                    # abbrechen (touch() muss trotzdem noch laufen).
                    view_warnings.append("%s (%s)" % (obj.Name, exc_view))
                obj.touch()
                n_paths += 1
                App.Console.PrintMessage(
                    "upgrade_hose_objects(): '%s' (Pfad) aktualisiert.\n"
                    % obj.Name)

            elif is_solid:
                if not _rebind_proxy(obj, FlexHoseSolid):
                    failed.append(obj.Name)
                    continue
                _ensure_flexhosesolid_properties(obj)
                vobj = obj.ViewObject
                try:
                    if vobj is not None:
                        if not isinstance(getattr(vobj, "Proxy", None),
                                           ViewProviderFlexHoseSolid):
                            vobj.Proxy = ViewProviderFlexHoseSolid.__new__(
                                ViewProviderFlexHoseSolid)
                        # Anzeige-Einstellungen erneut anwenden (laufen
                        # sonst nur in attach() bei Neuerzeugung)
                        vobj.Transparency = 50
                        vobj.ShapeColor = (0.8549, 0.898, 0.9373)  # #dae5ef
                        vobj.LineColor = vobj.ShapeColor
                        try:
                            vobj.LineTransparency = 100
                        except Exception:
                            pass
                except Exception as exc_view:
                    # Siehe Kommentar im Pfad-Zweig oben - gleiche Ursache
                    # (Assembly-Komponente mit Gui.ViewProviderLink).
                    view_warnings.append("%s (%s)" % (obj.Name, exc_view))
                obj.touch()
                n_solids += 1
                App.Console.PrintMessage(
                    "upgrade_hose_objects(): '%s' (Koerper) aktualisiert.\n"
                    % obj.Name)
        except Exception as exc:
            failed.append("%s (%s)" % (obj.Name, exc))

    doc.recompute()
    App.Console.PrintMessage(
        "upgrade_hose_objects(): fertig - %d Pfad-Objekt(e), %d "
        "Koerper-Objekt(e) aktualisiert.\n" % (n_paths, n_solids))
    if view_warnings:
        App.Console.PrintWarning(
            "upgrade_hose_objects(): bei %d Objekt(en) konnte nur der "
            "ViewObject-Proxy nicht neu gebunden werden (vermutlich "
            "Assembly-Komponenten mit eigenem Gui.ViewProviderLink) - "
            "Geometrie/Adaptivitaet ist davon NICHT betroffen, nur "
            "Anzeige-Details (Icon/Standardfarbe) evtl.: %s\n"
            % (len(view_warnings), ", ".join(view_warnings)))
    if failed:
        App.Console.PrintError(
            "upgrade_hose_objects(): %d Objekt(e) NICHT reparierbar: %s\n"
            "Vermutlich wurde das Dokument geoeffnet, BEVOR das Makro in "
            "dieser Sitzung geladen war - dabei kann FreeCAD die Proxy-"
            "Bindung dieser Objekte irreparabel verlieren. Abhilfe: "
            "Dokument OHNE speichern schliessen, Makro laden, DANACH das "
            "Dokument erneut oeffnen (dann klappt die Wiederherstellung "
            "beim Laden automatisch).\n" % (len(failed), ", ".join(failed)))


def refresh_all_hoses():
    """Erzwingt eine Neuberechnung ALLER FlexHosePath- und FlexHoseSolid-
    Objekte im aktiven Dokument in einem Rutsch - Ersatz fuer 'jeden
    Schlauch einzeln im Baum markieren und Aktualisieren waehlen'.

    Hintergrund/Vermutung (nicht sicher verifiziert, da ich FreeCAD nicht
    selbst ausfuehren kann): LCS1/LCS2 sind App::PropertyXLinkSub und
    sollten damit eigentlich eine Abhaengigkeit im Dokument-Graphen
    registrieren, die bei Aenderung der referenzierten Platzierung
    automatisch ein 'touch' ausloest. Falls der Assembly-Loeser
    Platzierungen aber auf einem Weg setzt, der diese Benachrichtigung
    nicht (zuverlaessig) durchreicht - oder falls generell kein
    automatischer Dokument-Recompute nach dem Loesen erfolgt - bleiben
    abhaengige Objekte optisch veraltet, bis man sie manuell anstoesst.
    Diese Funktion ist der pragmatische Weg, das fuer alle Schlauch-Objekte
    auf einmal zu erledigen, unabhaengig von der genauen Ursache."""
    doc = App.ActiveDocument
    if doc is None:
        App.Console.PrintWarning("refresh_all_hoses(): kein aktives "
                                  "Dokument.\n")
        return
    count = 0
    for obj in doc.Objects:
        proxy = getattr(obj, "Proxy", None)
        if isinstance(proxy, (FlexHosePath, FlexHoseSolid)):
            obj.touch()
            count += 1
    doc.recompute()
    App.Console.PrintMessage(
        "refresh_all_hoses(): %d Schlauch-Objekt(e) aktualisiert.\n" % count)


def get_selected_linksub():
    """Nimmt die aktuelle Baum-/3D-Auswahl. Ist direkt ein LCS ausgewaehlt
    (Typ PartDesign::CoordinateSystem - ggf. anpassen, falls eure LCS-
    Objekte anders angelegt sind), wird es unveraendert uebernommen (inkl.
    vollem Unterpfad fuer mehrfach verlinkte Bauteile). Ist stattdessen das
    Bauteil/der Koerper selbst ausgewaehlt (z.B. per Klick im 3D-Fenster auf
    die Geometrie statt im Baum auf das LCS), wird schrittweise auf jeder
    Verschachtelungsebene (von der geklickten Geometrie nach oben) nach
    einem enthaltenen LCS gesucht - dann reicht ein einfacher Klick auf den
    Anschlussstutzen, auch bei tief verschachtelten Assemblies. WICHTIG:
    `topobj` (s.Object) bleibt dabei IMMER dasselbe Objekt wie ausgewaehlt -
    nur der Unterpfad wird auf das gefundene LCS umgebogen, damit die
    Instanz-Information (welche konkrete Verlinkung/Instanz) erhalten
    bleibt."""
    sel = Gui.Selection.getSelectionEx('', 0)
    if not sel:
        raise RuntimeError("Nichts ausgewaehlt - bitte erst im Baum oder "
                            "3D-Fenster das LCS oder das Bauteil anklicken.")
    s = sel[0]
    topobj = s.Object
    subnames = list(s.SubElementNames)
    subname = subnames[0] if subnames else ""

    App.Console.PrintMessage(
        "FlexHosePath: Auswahl topobj='%s', subname='%s'\n"
        % (topobj.Name, subname))

    resolved = topobj.getSubObject(subname, retType=1) if subname \
        else topobj  # retType=1 -> DocObject (siehe getSubObject-Hinweis oben)

    if resolved is not None and getattr(resolved, "TypeId", "") == \
            "PartDesign::CoordinateSystem":
        App.Console.PrintMessage(
            "FlexHosePath: direkt ein LCS getroffen ('%s', Label '%s').\n"
            % (resolved.Name, resolved.Label))
        return (topobj, subnames)  # direkt ein LCS getroffen - unveraendert

    # Schrittweise von der geklickten Geometrie nach oben durch alle
    # Verschachtelungsebenen gehen (ein Punkt-Segment nach dem anderen
    # abschneiden) und bei jeder Ebene pruefen, ob das dort liegende Objekt
    # ein Kind-LCS enthaelt. Nur EIN Segment abzuschneiden reicht bei tief
    # verschachtelten Assemblies (Assembly.Assembly001.Verdichterventil.
    # Nippel028....) nicht aus, da die eigentliche Body-Ebene oft mehrere
    # Ebenen ueber der geklickten Geometrie liegt.
    parts = subname.split(".") if subname else []
    for cut in range(1, len(parts) + 1):
        prefix_parts = parts[:-cut]
        prefix = ".".join(p for p in prefix_parts if p)
        prefix_dotted = (prefix + ".") if prefix else ""
        parent = topobj.getSubObject(prefix_dotted, retType=1) \
            if prefix_dotted else topobj
        if parent is None:
            continue
        App.Console.PrintMessage(
            "FlexHosePath: pruefe Ebene '%s' (Objekt '%s', Label '%s') auf "
            "enthaltenes LCS...\n"
            % (prefix_dotted or "(topobj)", parent.Name, parent.Label))
        lcs = _find_child_lcs(parent)
        if lcs is not None:
            # Pfad-Praefix so weit wie moeglich verkuerzen: rein
            # topologische Zwischensegmente (z.B. Face-Hash-Strings der
            # urspruenglich angeklickten Geometrie) im Praefix koennen bei
            # der spaeteren Platzierungs-Aufloesung (retType=3) die
            # akkumulierte Transformation verfaelschen - Position bleibt
            # ungefaehr richtig, Richtung/Tangente kippt aber komplett.
            # Deshalb: so lange weitere Segmente abschneiden, wie das
            # DASSELBE Zielobjekt (parent) aufgeloest wird, und den
            # kuerzesten/saubersten Praefix verwenden.
            clean_prefix_dotted = prefix_dotted
            for longer_cut in range(cut + 1, len(parts) + 1):
                shorter_prefix = ".".join(
                    p for p in parts[:-longer_cut] if p)
                shorter_prefix_dotted = \
                    (shorter_prefix + ".") if shorter_prefix else ""
                candidate = topobj.getSubObject(
                    shorter_prefix_dotted, retType=1) \
                    if shorter_prefix_dotted else topobj
                if candidate is not None and \
                        getattr(candidate, "Name", None) == parent.Name:
                    clean_prefix_dotted = shorter_prefix_dotted
                else:
                    break  # Zielobjekt wechselt - nicht weiter kuerzen

            if clean_prefix_dotted != prefix_dotted:
                App.Console.PrintMessage(
                    "FlexHosePath: Praefix bereinigt (topologisches "
                    "Zwischensegment entfernt): '%s' -> '%s'.\n"
                    % (prefix_dotted, clean_prefix_dotted))

            App.Console.PrintMessage(
                "FlexHosePath: LCS gefunden - '%s' (Label '%s') in Ebene "
                "'%s'.\n" % (lcs.Name, lcs.Label, prefix_dotted or "(topobj)"))
            new_subname = clean_prefix_dotted + lcs.Name + "."
            return (topobj, [new_subname])

    # Falls subname leer war (Klick direkt auf ein Top-Level-Objekt ohne
    # Unterpfad), zusaetzlich noch direkt in topobj selbst suchen
    if not parts:
        lcs = _find_child_lcs(topobj)
        if lcs is not None:
            App.Console.PrintMessage(
                "FlexHosePath: LCS gefunden - '%s' (Label '%s') direkt in "
                "topobj.\n" % (lcs.Name, lcs.Label))
            return (topobj, [lcs.Name + "."])

    raise RuntimeError(
        "Kein LCS gefunden: weder '%s' selbst noch eine der uebergeordneten "
        "Ebenen enthaelt ein PartDesign::CoordinateSystem. Bitte das LCS "
        "direkt anklicken (oder _find_child_lcs anpassen, falls eure "
        "LCS-Objekte einen anderen TypeId haben)."
        % getattr(resolved, "Label", topobj.Label))


# ---------------------------------------------------------------------------
# Task-Panel: Konfiguration eines neuen Schlauchs (Anfangs-/Endteil, Laenge).
# Alle weiteren Steuerparameter (Segments, PullAngle1/2, PullStrength1/2,
# InsertionLength1/2, FlipStart/End, Aussendurchmesser/Wandstaerke der
# Extrusion) bleiben bewusst ausserhalb des Panels - die lassen sich danach
# jederzeit im Eigenschaften-/Detailfenster des erzeugten Objekts anpassen.
# ---------------------------------------------------------------------------

from PySide import QtGui, QtCore  # FreeCADs Qt-Kompatibilitaetsschicht


class HoseTaskPanel:
    def __init__(self):
        self._lcs1 = None
        self._lcs2 = None

        self.form = QtGui.QWidget()
        self.form.setWindowTitle("Schlauch konfigurieren")
        self.form.setMaximumWidth(420)
        layout = QtGui.QFormLayout(self.form)

        self.lcs1_label = QtGui.QLabel("(nicht gewaehlt)")
        self.lcs1_label.setMaximumWidth(160)
        self.lcs1_label.setMinimumWidth(0)
        self.lcs1_label.setSizePolicy(QtGui.QSizePolicy.Ignored,
                                       QtGui.QSizePolicy.Preferred)
        lcs1_button = QtGui.QPushButton("Auswahl uebernehmen")
        lcs1_button.clicked.connect(self._pick_lcs1)
        row1 = QtGui.QHBoxLayout()
        row1.addWidget(self.lcs1_label, 1)
        row1.addWidget(lcs1_button, 0)
        layout.addRow("Anfangsteil (LCS1):", row1)

        self.lcs2_label = QtGui.QLabel("(nicht gewaehlt)")
        self.lcs2_label.setMaximumWidth(160)
        self.lcs2_label.setMinimumWidth(0)
        self.lcs2_label.setSizePolicy(QtGui.QSizePolicy.Ignored,
                                       QtGui.QSizePolicy.Preferred)
        lcs2_button = QtGui.QPushButton("Auswahl uebernehmen")
        lcs2_button.clicked.connect(self._pick_lcs2)
        row2 = QtGui.QHBoxLayout()
        row2.addWidget(self.lcs2_label, 1)
        row2.addWidget(lcs2_button, 0)
        layout.addRow("Endteil (LCS2):", row2)

        self.distance_label = QtGui.QLabel("Abstand: -")
        layout.addRow(self.distance_label)

        self.length_spin = QtGui.QDoubleSpinBox()
        self.length_spin.setRange(0.1, 100000.0)
        self.length_spin.setDecimals(1)
        self.length_spin.setSuffix(" mm")
        self.length_spin.setValue(100.0)
        layout.addRow("Laenge:", self.length_spin)

        self.type_combo = QtGui.QComboBox()
        self.type_combo.addItem("Schlauch (Hose)")
        self.type_combo.addItem("Kabel (Wire)")
        self.type_combo.currentIndexChanged.connect(self._apply_type_defaults)
        layout.addRow("Typ:", self.type_combo)

        self.diameter_spin = QtGui.QDoubleSpinBox()
        self.diameter_spin.setRange(0.1, 1000.0)
        self.diameter_spin.setDecimals(2)
        self.diameter_spin.setSuffix(" mm")
        layout.addRow("Durchmesser:", self.diameter_spin)

        self._color = HOSE_DEFAULT_COLOR
        self.color_button = QtGui.QPushButton()
        self.color_button.setFixedWidth(60)
        self.color_button.clicked.connect(self._pick_color)
        self._update_color_button()
        layout.addRow("Farbe:", self.color_button)

        self._apply_type_defaults()  # Anfangsvorbelegung (Hose)

        self.create_solid_check = QtGui.QCheckBox(
            "Volumenkoerper mit erzeugen (Durchmesser/Farbe siehe oben - "
            "danach im Eigenschaftenfenster weiter anpassbar)")
        self.create_solid_check.setChecked(True)
        layout.addRow(self.create_solid_check)

        create_again_button = QtGui.QPushButton(
            "Erzeugen (Panel bleibt offen, fuer weiteren Schlauch)")
        create_again_button.clicked.connect(self._create_keep_open)
        layout.addRow(create_again_button)

        hint = QtGui.QLabel(
            "Weitere Parameter (Einstecklaengen, Segmentanzahl, "
            "Regularisierung, Durchmesser ...) lassen sich nach dem "
            "Erzeugen im Eigenschaftenfenster des Objekts anpassen.")
        hint.setWordWrap(True)
        layout.addRow(hint)

        refresh_button = QtGui.QPushButton(" Schlaeuche aktualisieren")
        refresh_icon = self.form.style().standardIcon(
            QtGui.QStyle.SP_BrowserReload)
        refresh_button.setIcon(refresh_icon)
        refresh_button.clicked.connect(self._refresh_hoses)
        layout.addRow(refresh_button)

        activate_button = QtGui.QPushButton("Activate hoses")
        activate_button.setToolTip(
            "Nach dem Oeffnen eines gespeicherten Dokuments (mit bereits "
            "geladenem Makro) sind Schlaeuche oft nicht mehr adaptiv - "
            "dieser Button repariert die Proxy-Bindung (ruft "
            "upgrade_hose_objects() auf), ohne die Objekte neu zu "
            "erzeugen.")
        activate_icon = self.form.style().standardIcon(
            QtGui.QStyle.SP_DialogApplyButton)
        activate_button.setIcon(activate_icon)
        activate_button.clicked.connect(self._activate_hoses)
        layout.addRow(activate_button)

        separator = QtGui.QFrame()
        separator.setFrameShape(QtGui.QFrame.HLine)
        layout.addRow(separator)

        segment_label = QtGui.QLabel(
            "<b>Starres Zwischenstueck</b> (ein Teil, ein LCS_tube am "
            "freien Ende; Gegenende ist eine plane Stirnflaeche - "
            "Verbindung manuell in der Assembly-Werkbank)")
        segment_label.setWordWrap(True)
        layout.addRow(segment_label)

        self.segment_length_spin = QtGui.QDoubleSpinBox()
        self.segment_length_spin.setRange(1.0, 100000.0)
        self.segment_length_spin.setDecimals(1)
        self.segment_length_spin.setSuffix(" mm")
        self.segment_length_spin.setValue(100.0)
        layout.addRow("Laenge:", self.segment_length_spin)

        segment_button = QtGui.QPushButton("Zwischenstueck erzeugen")
        segment_button.clicked.connect(self._create_segment)
        layout.addRow(segment_button)

    def _refresh_hoses(self):
        try:
            refresh_all_hoses()
        except Exception as exc:
            QtGui.QMessageBox.warning(
                self.form, "Fehler beim Aktualisieren", str(exc))

    def _activate_hoses(self):
        try:
            upgrade_hose_objects()
        except Exception as exc:
            QtGui.QMessageBox.warning(
                self.form, "Fehler beim Aktivieren", str(exc))

    def _create_segment(self):
        try:
            make_hose_segment_half(self.segment_length_spin.value())
        except Exception as exc:
            QtGui.QMessageBox.warning(
                self.form, "Fehler beim Erzeugen", str(exc))

    def _label_for(self, linksub):
        """Kurze, lesbare Anzeige statt des rohen Unterpfads - der enthaelt
        bei per Klick gefundenen LCS oft lange, fuer Menschen kaum lesbare
        Namen der urspruenglich angeklickten Geometrie (topologische
        Element-Namen). Zeigt stattdessen 'Instanz-Label -> LCS-Label'."""
        obj, subnames = linksub
        if not subnames:
            text = obj.Label
        else:
            try:
                chain = obj.getSubObjectList(subnames[0])
            except Exception:
                chain = []
            if len(chain) >= 2:
                text = "%s -> %s" % (chain[-2].Label, chain[-1].Label)
            elif len(chain) == 1:
                text = chain[-1].Label
            else:
                text = obj.Label
        metrics = QtGui.QFontMetrics(self.form.font())
        return metrics.elidedText(text, QtCore.Qt.ElideMiddle, 200)

    def _pick_lcs1(self):
        try:
            self._lcs1 = get_selected_linksub()
            self.lcs1_label.setText(self._label_for(self._lcs1))
        except RuntimeError as exc:
            QtGui.QMessageBox.warning(self.form, "Hinweis", str(exc))
        self._update_distance()

    def _pick_lcs2(self):
        try:
            self._lcs2 = get_selected_linksub()
            self.lcs2_label.setText(self._label_for(self._lcs2))
        except RuntimeError as exc:
            QtGui.QMessageBox.warning(self.form, "Hinweis", str(exc))
        self._update_distance()

    def _update_distance(self):
        if self._lcs1 is None or self._lcs2 is None:
            self.distance_label.setText("Abstand: -")
            return
        try:
            pl1 = resolve_lcs_placement(self._lcs1)
            pl2 = resolve_lcs_placement(self._lcs2)
            distance = (pl2.Base - pl1.Base).Length
            self.distance_label.setText("Abstand: %.1f mm" % distance)
            self.length_spin.setValue(1.2 * distance)
        except Exception as exc:
            self.distance_label.setText("Abstand: (Fehler: %s)" % exc)

    def _validate(self):
        if self._lcs1 is None or self._lcs2 is None:
            QtGui.QMessageBox.warning(
                self.form, "Unvollstaendig",
                "Bitte zuerst Anfangs- und Endteil auswaehlen (LCS im "
                "Baum/3D-Fenster anklicken, dann jeweils den Button "
                "druecken).")
            return False
        return True

    def _apply_type_defaults(self):
        if self.type_combo.currentIndex() == 0:  # Hose
            self.diameter_spin.setValue(HOSE_DEFAULT_DIAMETER)
            self._color = HOSE_DEFAULT_COLOR
            self._transparency = HOSE_DEFAULT_TRANSPARENCY
        else:  # Wire
            self.diameter_spin.setValue(WIRE_DEFAULT_DIAMETER)
            self._color = WIRE_DEFAULT_COLOR
            self._transparency = WIRE_DEFAULT_TRANSPARENCY
        self._update_color_button()

    def _update_color_button(self):
        r, g, b = [int(round(c * 255)) for c in self._color]
        self.color_button.setStyleSheet(
            "background-color: rgb(%d,%d,%d);" % (r, g, b))

    def _pick_color(self):
        r, g, b = [int(round(c * 255)) for c in self._color]
        initial = QtGui.QColor(r, g, b)
        chosen = QtGui.QColorDialog.getColor(initial, self.form,
                                              "Farbe waehlen")
        if chosen.isValid():
            self._color = (chosen.redF(), chosen.greenF(), chosen.blueF())
            self._update_color_button()

    def _create_hose(self):
        path_obj = make_flex_hose("SchlauchPfad", self._lcs1, self._lcs2,
                                   self.length_spin.value())
        if self.create_solid_check.isChecked():
            make_flex_hose_solid(path_obj,
                                  outer_diameter=self.diameter_spin.value(),
                                  color=self._color,
                                  transparency=self._transparency)
        return path_obj

    def _create_keep_open(self):
        if not self._validate():
            return
        self._create_hose()
        # Auswahl zuruecksetzen, damit der naechste Schlauch nicht versehentlich
        # mit denselben LCS angelegt wird
        self._lcs1 = None
        self._lcs2 = None
        self.lcs1_label.setText("(nicht gewaehlt)")
        self.lcs2_label.setText("(nicht gewaehlt)")
        self.distance_label.setText("Abstand: -")

    def accept(self):
        if not self._validate():
            return False
        self._create_hose()
        Gui.Control.closeDialog()
        return True

    def reject(self):
        Gui.Control.closeDialog()
        return True

    def getStandardButtons(self):
        # KEIN int(...) hier - in aktuellen PySide-Versionen sind die
        # QDialogButtonBox-Flags eigene Enum-/Flag-Objekte, kein Integer
        # mehr; int(...) darauf wirft "TypeError: int() argument must be
        # a string, a bytes-like object or a real number, not
        # 'StandardButton'". Den rohen Flag-Wert zurueckgeben.
        return QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel


def show_hose_task_panel():
    panel = HoseTaskPanel()
    Gui.Control.showDialog(panel)


# Beispielaufruf per Konsole (falls du statt des Panels lieber Python
# direkt benutzen willst):
# lcs1 = get_selected_linksub()
# lcs2 = get_selected_linksub()
# obj = make_flex_hose("SchlauchPfad", lcs1, lcs2, 250.0, ins1=15.0, ins2=15.0)
# obj.PullAngle1 = 45  # Grad, bei Bedarf zur Formkontrolle
# obj.PullAngle2 = 45
# obj.PullStrength1 = 0.05
# obj.PullStrength2 = 0.05
#
# solid = make_flex_hose_solid(obj, outer_diameter=4.0, wall_thickness=0.5)


# Macro-Dialog fuehrt Skripte teils in einem EIGENEN Namensraum aus, der
# nicht mit dem der interaktiven Konsole geteilt wird - Funktionen, die nur
# ueber "Makro > Ausfuehren" definiert wurden, waeren danach in der Konsole
# mit NameError nicht auffindbar. Deshalb hier explizit in __main__ (dort
# arbeitet die interaktive Konsole normalerweise) ablegen, unabhaengig davon,
# in welchem Namensraum dieses Skript selbst lief.
import __main__ as _main
for _name in ("get_selected_linksub", "make_flex_hose", "make_flex_hose_solid",
              "set_connector_insertion_length", "refresh_all_hoses",
              "upgrade_hose_objects", "show_hose_task_panel",
              "FlexHosePath", "FlexHoseSolid",
              "ViewProviderFlexHosePath", "ViewProviderFlexHoseSolid",
              "make_hose_segment_half", "make_straight_hose_segment",
              "RigidHoseSegmentHalf", "ViewProviderRigidHoseSegmentHalf",
              "set_profiling", "resolve_lcs_placement"):
    setattr(_main, _name, globals()[_name])


# Macro-Einstiegspunkt: beim Ausfuehren ueber Makro > Makros... > Ausfuehren
# (statt per exec() in der Konsole) oeffnet sich das Konfigurations-Panel
# direkt, ohne dass danach noch etwas in die Konsole eingegeben werden muss.
if App.GuiUp:
    show_hose_task_panel()
