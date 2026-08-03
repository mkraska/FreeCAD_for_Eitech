# paint.py - Eitech Farbeinfärbung für Assembly-Links, Bodies und Features
# Zwei Buttonreihen: Gummi/Plastik-Farben + Metall/Standard
# Icons: gerenderte Kugeln mit Phong-ähnlicher Beleuchtung
#
# Ablageort: C:/Users/kraska/AppData/Roaming/FreeCAD/v1-1/Macro/

import FreeCAD as App
import FreeCADGui as Gui

try:
    from PySide6 import QtWidgets, QtCore, QtGui
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui

# ---------------------------------------------------------------------------
# Materialdefinitionen
# (Tooltip, diffuse, specular, ambient, shininess)
#
# WICHTIG (Juli 2026): Bei App::Link-Instanzen wird von FreeCAD 1.1 trotz
# OverrideMaterial=True nur DiffuseColor tatsaechlich pro Instanz gerendert -
# Specular/Ambient/Shininess kommen immer aus der Quelldatei (bekannter,
# von FreeCAD-Entwicklern bestaetigter Einschraenkung, siehe GitHub Issue
# FreeCAD/FreeCAD#19135). Deshalb: Specular/Ambient/Shininess sind bei allen
# Farben unten auf ein gemeinsames, an der Konsole validiertes generisches
# Profil vereinheitlicht (Specular 0.60/0.60/0.60, Ambient 0.30/0.30/0.30,
# Shininess 0.25 - hoeher als urspruenglich verwendet, da niedrigeres
# Shininess bei neutral-grauem Specular zu blassen/verwaesserten Farben
# fuehrt, siehe Rot-Test; bei diesem Wert reicht das auch bei Orange ohne
# gesonderte Behandlung). Diese Werte muessen zusaetzlich per
# normalize_plastik.py (o.ae.) an der Quelldatei gesetzt werden, damit sie
# bei Links wirken. Fuer "direct"-Modus-Objekte (PartDesign-Body/Feature
# ohne Link-Wrapper) wirken sie weiterhin direkt ueber dieses Skript.
# ---------------------------------------------------------------------------

# Zeile 1: Gummi / Plastik
ROW1 = [
    ("Schwarz",      (0.228000,0.228000,0.228000), (0.600000,0.600000,0.600000), (0.300000,0.300000,0.300000), 0.25),
    ("Rot",          (1.000000,0.000000,0.000000), (0.600000,0.600000,0.600000), (0.300000,0.300000,0.300000), 0.25),
    ("Orange",       (1.000000,0.505882,0.007843), (0.600000,0.600000,0.600000), (0.300000,0.300000,0.300000), 0.25),
    ("Gelb",         (1.000000,1.000000,0.000000), (0.600000,0.600000,0.600000), (0.300000,0.300000,0.300000), 0.25),
    ("Beige (C13)",  (0.992157,0.729412,0.003922), (0.600000,0.600000,0.600000), (0.300000,0.300000,0.300000), 0.25),
    ("Blau",         (0.003922,0.329412,0.635294), (0.600000,0.600000,0.600000), (0.300000,0.300000,0.300000), 0.25),
    ("Grau",         (0.678431,0.709804,0.741176), (0.600000,0.600000,0.600000), (0.300000,0.300000,0.300000), 0.25),
    ("Weiss",        (1.000000,0.984314,0.941176), (0.600000,0.600000,0.600000), (0.300000,0.300000,0.300000), 0.25),
]

# Zeile 2: Metall + Standard-Reset
# Basiert auf FreeCAD-Standard: Diffuse(173,181,189) Ambient(85,85,85) Specular(136,136,136) Shininess=0.90
ROW2 = [
    ("Metall (hell)",   (0.881961,0.922745,0.963529), (0.693333,0.693333,0.693333), (0.433333,0.433333,0.433333), 0.90),
    ("Metall (mittel)", (0.678431,0.709804,0.741176), (0.533333,0.533333,0.533333), (0.333333,0.333333,0.333333), 0.90),
    ("Metall (dunkel)", (0.440980,0.461373,0.481765), (0.346667,0.346667,0.346667), (0.216667,0.216667,0.216667), 0.90),
]

# Standard = FreeCAD-Standardmaterial (Reset)
MAT_STANDARD = ("FreeCAD Standard", (0.678431,0.709804,0.741176), (0.533333,0.533333,0.533333), (0.333333,0.333333,0.333333), 0.90)

# TypeIds die direkt eingefärbt werden (kein Link-Override)
_DIRECT_TYPES = {
    "PartDesign::Body", "PartDesign::Pad", "PartDesign::Pocket",
    "PartDesign::Revolution", "PartDesign::Groove", "PartDesign::Chamfer",
    "PartDesign::Fillet", "PartDesign::Boolean", "PartDesign::Mirrored",
    "PartDesign::LinearPattern", "PartDesign::PolarPattern",
    "Part::Feature", "Part::Box", "Part::Sphere", "Part::Cylinder",
}

# ---------------------------------------------------------------------------
# Globaler Zustand
# ---------------------------------------------------------------------------
_selected_objs  = []   # Liste von (obj, mode) Tupeln
_sel_observer   = None


# ---------------------------------------------------------------------------
# Kugel-Icon rendern
# ---------------------------------------------------------------------------
def make_sphere_pixmap(diffuse, shininess, size=32):
    """Rendert eine Kugel mit Phong-ähnlicher Beleuchtung."""
    pix = QtGui.QPixmap(size, size)
    pix.fill(QtGui.QColor(240, 240, 240))
    painter = QtGui.QPainter(pix)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)

    r = size / 2
    lx, ly = r * 0.4, r * 0.35
    br, bg, bb = diffuse
    ambient = 0.45
    ar = int(br * 255 * ambient)
    ag = int(bg * 255 * ambient)
    ab = int(bb * 255 * ambient)

    # Diffuse-Gradient – füllt den ganzen Button
    grad_diff = QtGui.QRadialGradient(lx, ly, size * 0.9)
    grad_diff.setColorAt(0.0, QtGui.QColor(int(br*255), int(bg*255), int(bb*255)))
    grad_diff.setColorAt(1.0, QtGui.QColor(ar, ag, ab))
    painter.setBrush(QtGui.QBrush(grad_diff))
    painter.setPen(QtCore.Qt.NoPen)
    painter.drawEllipse(QtCore.QRectF(1, 1, size-2, size-2))

    # Specular-Glanzpunkt
    spec_size = size * (0.08 + (1.0 - shininess) * 0.25)
    spec_alpha = int(120 + shininess * 135)
    grad_spec = QtGui.QRadialGradient(lx, ly, spec_size)
    grad_spec.setColorAt(0.0, QtGui.QColor(255, 255, 255, spec_alpha))
    grad_spec.setColorAt(1.0, QtGui.QColor(255, 255, 255, 0))
    painter.setBrush(QtGui.QBrush(grad_spec))
    painter.drawEllipse(QtCore.QRectF(1, 1, size-2, size-2))

    # Rand
    painter.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0, 80), 0.5))
    painter.setBrush(QtCore.Qt.NoBrush)
    painter.drawEllipse(QtCore.QRectF(1, 1, size-2, size-2))
    painter.end()
    return pix


# ---------------------------------------------------------------------------
# SelectionObserver
# ---------------------------------------------------------------------------
class _PaintSelObserver:
    def addSelection(self, doc, obj, sub, pnt):
        global _selected_objs
        active_doc = App.ActiveDocument
        if active_doc is None:
            return

        new_obj  = None
        new_mode = None

        link = _find_link_from_event(active_doc, doc, obj, sub)
        if link:
            new_obj  = link
            new_mode = "link"
        else:
            part_doc = App.getDocument(doc)
            if part_doc:
                part_obj = part_doc.getObject(obj)
                if part_obj and part_obj.TypeId in _DIRECT_TYPES:
                    new_obj  = part_obj
                    new_mode = "direct"

        if new_obj is None:
            return

        # Ctrl gedrückt → zur Liste hinzufügen, sonst ersetzen
        modifiers = QtWidgets.QApplication.keyboardModifiers()
        if modifiers & QtCore.Qt.ControlModifier:
            if not any(o is new_obj for o, _ in _selected_objs):
                _selected_objs.append((new_obj, new_mode))
        else:
            _selected_objs = [(new_obj, new_mode)]
        _update_toolbar_status()

    def clearSelection(self, doc):
        global _selected_objs
        _selected_objs = []
        _update_toolbar_status()


def _find_link_from_event(active_doc, doc, obj, sub):
    if doc == active_doc.Name:
        link = active_doc.getObject(obj)
        if link and link.TypeId == "App::Link":
            return link
    if sub and '.' in sub:
        parts = sub.split('.')
        if parts[0]:
            link = active_doc.getObject(parts[0])
            if link and link.TypeId == "App::Link":
                return link
    candidates = _find_candidates_for_doc(active_doc, doc)
    if len(candidates) == 1:
        return candidates[0]
    return None


def _find_candidates_for_doc(active_doc, part_doc_name):
    candidates = []
    for o in active_doc.Objects:
        if o.TypeId != "App::Link":
            continue
        cur = o
        for _ in range(4):
            linked = getattr(cur, "LinkedObject", None)
            if linked is None:
                break
            if linked.Document.Name == part_doc_name:
                candidates.append(o)
                break
            cur = linked
    return candidates


def _ensure_observer():
    global _sel_observer
    if _sel_observer is None:
        _sel_observer = _PaintSelObserver()
        Gui.Selection.addObserver(_sel_observer)


def _update_toolbar_status():
    mw = Gui.getMainWindow()
    tb = mw.findChild(QtWidgets.QWidget, "EitechPaintToolbar")
    if tb and hasattr(tb, 'update_status'):
        tb.update_status()


# ---------------------------------------------------------------------------
# Material anwenden
# ---------------------------------------------------------------------------
def _set_appearance(vp, diffuse, specular, ambient, shininess):
    try:
        sa = vp.ShapeAppearance
        m = sa[0] if sa else None
        if m is None:
            raise ValueError("no appearance")
        m.DiffuseColor  = (diffuse[0],  diffuse[1],  diffuse[2],  1.0)
        m.SpecularColor = (specular[0], specular[1], specular[2], 1.0)
        m.AmbientColor  = (ambient[0],  ambient[1],  ambient[2],  1.0)
        m.EmissiveColor = (0.0, 0.0, 0.0, 1.0)
        m.Shininess     = shininess
        vp.ShapeAppearance = [m]
    except Exception:
        vp.ShapeColor = (diffuse[0], diffuse[1], diffuse[2])
        try:
            m = vp.ShapeMaterial
            m.DiffuseColor  = (diffuse[0],  diffuse[1],  diffuse[2],  1.0)
            m.SpecularColor = (specular[0], specular[1], specular[2], 1.0)
            m.AmbientColor  = (ambient[0],  ambient[1],  ambient[2],  1.0)
            m.Shininess     = shininess
            vp.ShapeMaterial = m
        except Exception:
            pass


_LINK_TYPES = ("App::Link", "Assembly::AssemblyLink")


def _get_current_selection():
    """Liest alle selektierten Objekte direkt aus der FreeCAD Selection View."""
    result = []
    seen = set()
    active_doc = App.ActiveDocument
    if active_doc is None:
        return result

    for sel in Gui.Selection.getSelectionEx('', 0):
        obj = sel.Object
        if obj is None or obj.Name in seen:
            continue

        # App::Link (oder Assembly::AssemblyLink) direkt selektiert
        if obj.TypeId in _LINK_TYPES:
            result.append((obj, "link"))
            seen.add(obj.Name)
            continue

        # Body oder Feature in Teiledatei
        if obj.TypeId in _DIRECT_TYPES:
            result.append((obj, "direct"))
            seen.add(obj.Name)
            continue

        # Verschachtelte Unterbaugruppe (obj ist der Assembly-Container,
        # z.B. Assembly::AssemblyObject): über getSubObjectList() die
        # komplette Verschachtelungskette auflösen (wie in nuts_and_bolts.py/
        # edit_constraints.py) statt nur das erste SubElementNames-Segment
        # zu nehmen - das wäre nur der Link zur Unterbaugruppe selbst, nicht
        # zum eigentlichen Teil. Tiefsten Link in der Kette nehmen (= das
        # tatsächlich angeklickte Teil), nicht den äußersten Container.
        for sub in sel.SubElementNames:
            try:
                kette = obj.getSubObjectList(sub)
            except Exception:
                kette = []
            gefunden = None
            for kette_obj in reversed(kette):
                if kette_obj.TypeId in _LINK_TYPES and kette_obj.Name not in seen:
                    gefunden = kette_obj
                    break
            if gefunden is not None:
                result.append((gefunden, "link"))
                seen.add(gefunden.Name)
                break

    return result


def apply_material(mat):
    objs = _get_current_selection()
    if not objs:
        App.Console.PrintWarning("paint.py: Kein Teil ausgewählt.\n")
        return
    tooltip, diffuse, specular, ambient, shininess = mat
    changed = 0
    for obj, mode in objs:
        vp = obj.ViewObject
        if vp is None:
            continue
        try:
            if mode == "link":
                vp.OverrideMaterial = True
                m = vp.ShapeMaterial
                m.DiffuseColor  = (diffuse[0],  diffuse[1],  diffuse[2],  1.0)
                m.SpecularColor = (specular[0], specular[1], specular[2], 1.0)
                m.AmbientColor  = (ambient[0],  ambient[1],  ambient[2],  1.0)
                m.EmissiveColor = (0.0, 0.0, 0.0, 1.0)
                m.Shininess     = shininess
                vp.ShapeMaterial = m
            else:
                _set_appearance(vp, diffuse, specular, ambient, shininess)
            changed += 1
            mode_str = "Link" if mode == "link" else obj.TypeId.split("::")[-1]
            App.Console.PrintMessage(
                f"paint.py: '{obj.Label}' [{mode_str}] -> {tooltip}\n"
            )
        except Exception as e:
            App.Console.PrintError(f"paint.py: Fehler bei '{obj.Label}': {e}\n")
    if changed:
        Gui.updateGui()
        App.Console.PrintMessage(f"paint.py: {changed} Objekt(e) eingefärbt.\n")


def reset_material():
    objs = _get_current_selection()
    if not objs:
        App.Console.PrintWarning("paint.py: Kein Teil ausgewählt.\n")
        return
    for obj, mode in objs:
        try:
            vp = obj.ViewObject
            if mode == "link":
                vp.OverrideMaterial = False
            else:
                _set_appearance(vp,
                    diffuse   = MAT_STANDARD[1],
                    specular  = MAT_STANDARD[2],
                    ambient   = MAT_STANDARD[3],
                    shininess = MAT_STANDARD[4],
                )
            App.Console.PrintMessage(f"paint.py: Zurückgesetzt: '{obj.Label}'\n")
        except Exception as e:
            App.Console.PrintError(f"paint.py: Fehler: {e}\n")
    Gui.updateGui()


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------
BTN_SIZE = 32
ICON_SIZE = 32
SPACING   = 3
MARGINS   = 8

class _SphereButton(QtWidgets.QLabel):
    """QLabel als Button – kein internes Padding, volle Pixmap-Kontrolle."""
    clicked = QtCore.Signal()

    def __init__(self, tooltip, pixmap, parent=None):
        super().__init__(parent)
        self.setPixmap(pixmap)
        self.setFixedSize(BTN_SIZE, BTN_SIZE)
        self.setToolTip(tooltip)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self._pix_normal = pixmap
        # Hover-Effekt: leicht aufhellen
        hover_pix = QtGui.QPixmap(pixmap)
        p = QtGui.QPainter(hover_pix)
        p.fillRect(hover_pix.rect(), QtGui.QColor(255, 255, 255, 40))
        p.end()
        self._pix_hover = hover_pix

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit()

    def enterEvent(self, event):
        self.setPixmap(self._pix_hover)

    def leaveEvent(self, event):
        self.setPixmap(self._pix_normal)


def _make_btn(mat):
    """Erstellt einen SphereButton für ein Material."""
    tooltip, diffuse, specular, ambient, shininess = mat
    pix = make_sphere_pixmap(diffuse, shininess, BTN_SIZE)
    btn = _SphereButton(tooltip, pix)
    btn.clicked.connect(lambda m=mat: apply_material(m))
    return btn


class PaintToolbar(QtWidgets.QWidget):

    def __init__(self, parent=None):
        super().__init__(parent, QtCore.Qt.Tool | QtCore.Qt.WindowStaysOnTopHint)
        self.setWindowTitle("Eitech Farben")
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self._build_ui()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(3)
        layout.setContentsMargins(MARGINS, MARGINS, MARGINS, MARGINS)

        # Statusanzeige
        self.lbl_status = QtWidgets.QLabel("<i>–</i>")
        self.lbl_status.setStyleSheet("color: gray; padding: 1px;")
        self.lbl_status.setAlignment(QtCore.Qt.AlignLeft)
        layout.addWidget(self.lbl_status)

        # Zeile 1: Gummi / Plastik
        row1 = QtWidgets.QHBoxLayout()
        row1.setSpacing(SPACING)
        row1.setContentsMargins(0, 0, 0, 0)
        for mat in ROW1:
            row1.addWidget(_make_btn(mat))
        row1.addStretch()
        layout.addLayout(row1)

        # Zeile 2: Metall + Standard-Reset
        row2 = QtWidgets.QHBoxLayout()
        row2.setSpacing(SPACING)
        row2.setContentsMargins(0, 0, 0, 0)
        for mat in ROW2:
            row2.addWidget(_make_btn(mat))

        # Trennlinie zwischen Metall und Reset
        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.VLine)
        sep.setFrameShadow(QtWidgets.QFrame.Sunken)
        sep.setFixedWidth(8)
        row2.addWidget(sep)

        # Standard-Reset-Button
        pix_std = make_sphere_pixmap(MAT_STANDARD[1], MAT_STANDARD[4], BTN_SIZE)
        std_btn = _SphereButton("FreeCAD Standard / Override zurücksetzen", pix_std)
        std_btn.clicked.connect(lambda: reset_material())
        row2.addWidget(std_btn)

        row2.addStretch()
        layout.addLayout(row2)

        # Fensterbreite: Zeile 1 bestimmt die Breite
        n = len(ROW1)
        self.setFixedWidth(n * (BTN_SIZE + SPACING) + MARGINS * 2)

    def update_status(self):
        if _selected_objs:
            if len(_selected_objs) == 1:
                obj, mode = _selected_objs[0]
                mode_str = "Link" if mode == "link" else obj.TypeId.split("::")[-1]
                color = "darkblue" if mode == "link" else "darkgreen"
                self.lbl_status.setText(
                    f"<b style='color:{color};'>{obj.Label}</b> "
                    f"<small>({mode_str})</small>"
                )
            else:
                self.lbl_status.setText(
                    f"<b>{len(_selected_objs)} Teile ausgewählt</b>"
                )
            self.lbl_status.setStyleSheet("padding: 1px;")
        else:
            self.lbl_status.setText("<i>–</i>")
            self.lbl_status.setStyleSheet("color: gray; padding: 1px;")

    def closeEvent(self, event):
        global _sel_observer, _selected_objs
        if _sel_observer is not None:
            Gui.Selection.removeObserver(_sel_observer)
            _sel_observer = None
        _selected_objs = []
        event.accept()


# ---------------------------------------------------------------------------
# Einstiegspunkt
# ---------------------------------------------------------------------------
mw = Gui.getMainWindow()
existing = mw.findChild(QtWidgets.QWidget, "EitechPaintToolbar")
if existing:
    existing.close()

_ensure_observer()

toolbar = PaintToolbar(mw)
toolbar.setObjectName("EitechPaintToolbar")
toolbar.show()
