# duplicate_part.py - Eitech: Assembly-Teil duplizieren (leicht versetzte Kopie)
# Nicht-modales Panel mit einem Hauptbutton, analog zu paint.py:
# Teil im 3D-View markieren, Button klicken -> Kopie erscheint versetzt.
#
# Funktioniert auch fuer Teile aus Subassemblies: die Kopie landet dann in
# der aktiven Assembly, nicht in der Subassembly des Originals - dabei ohne
# Versatz/Placement-Berechnung, einfach mit Standard-Placement (wie
# "Komponente einfuegen"). Der Versatz gilt nur, wenn die Kopie im selben
# Container wie das Original bleibt.
#
# WICHTIG: die Ziel-Assembly wird beim Oeffnen des Panels EINMAL erfasst
# ("gepinnt"), nicht bei jedem Klick auf "Kopie erstellen" neu abgefragt -
# das Markieren eines Teils aus einer Subassembly laesst FreeCADs
# App.ActiveDocument/Gui.ActiveDocument auf deren Dokument umspringen, auch
# wenn man visuell weiter in der Top-Level-Assembly arbeitet. Panel also
# IMMER aus der gewuenschten Ziel-Assembly heraus oeffnen (oder "Ziel neu
# erfassen" klicken, waehrend diese aktiv ist).
#
# Ablageort: C:/Users/kraska/Documents/GitHub/FreeCAD_for_Eitech/Macros/

import FreeCAD as App
import FreeCADGui as Gui

try:
    from PySide6 import QtWidgets, QtCore
except ImportError:
    from PySide2 import QtWidgets, QtCore

# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------

# TypeIds, die als "duplizierbares Assembly-Bauteil" akzeptiert werden
# (gleiche Liste wie _LINK_TYPES in paint.py)
_LINK_TYPES = ("App::Link", "Assembly::AssemblyLink")

# Properties, die nicht generisch mitkopiert werden: Placement wird separat
# mit Versatz gesetzt, Shape ist ohnehin nur abgeleitet/schreibgeschuetzt.
_SKIP_PROPERTIES = {"Placement", "Shape"}


# ---------------------------------------------------------------------------
# Selektion auflösen (gleiche Traversierung wie paint.py._get_current_selection,
# hier auf ein einzelnes Ergebnis reduziert)
# ---------------------------------------------------------------------------
def _get_selected_link():
    """Liefert das aktuell markierte App::Link/Assembly::AssemblyLink-Objekt,
    auch wenn es in einer verschachtelten Unterbaugruppe liegt (dann ueber
    getSubObjectList() bis zum tiefsten Link in der Kette aufgeloest), oder
    None wenn nichts Passendes markiert ist."""
    active_doc = App.ActiveDocument
    if active_doc is None:
        return None

    for sel in Gui.Selection.getSelectionEx("", 0):
        obj = sel.Object
        if obj is None:
            continue

        if obj.TypeId in _LINK_TYPES:
            return obj

        # Verschachtelte Unterbaugruppe: ueber die komplette Kette den
        # tatsaechlich angeklickten (tiefsten) Link finden, nicht nur den
        # Link zur Unterbaugruppe selbst.
        for sub in sel.SubElementNames:
            try:
                kette = obj.getSubObjectList(sub)
            except Exception:
                kette = []
            for kette_obj in reversed(kette):
                if kette_obj.TypeId in _LINK_TYPES:
                    return kette_obj

    return None


def _find_parent_group(link_obj):
    """Struktureller Elterncontainer (Assembly/Gruppe) des Originals - NUR
    zum Erkennen des "einfachen Falls" (Original liegt bereits direkt im
    Zieldokument/-container), NICHT als Ziel zum Einfuegen der Kopie
    geeignet: Bei einem Teil aus einer starren (Rigid) Subassembly liegt
    dieser Container in einem ANDEREN Dokument, in das man ohne das
    Dokument selbst zu oeffnen gar nicht schreibend eingreifen kann - genau
    das fuehrte vorher zum Solver-Absturz."""
    for parent in link_obj.InList:
        if hasattr(parent, "Group"):
            return parent
    return None


def _active_assembly():
    """Liefert die gerade aktive Assembly (Assembly::AssemblyObject), oder
    None wenn keine aktiv ist.

    Empirisch an der FreeCAD-Python-Konsole ermittelt (der aus dem
    FreeCAD-Kern via Web-Recherche vermutete Key "part" war schlicht
    falsch): Gui.ActiveDocument.ActiveView.getActiveObject("assembly")
    liefert die aktive Assembly direkt, "part" liefert dort zuverlaessig
    None. isInEditMode() auf dem so gefundenen Objekt lieferte in
    demselben Test korrekt True - koennte also als zusaetzliche
    Bestaetigung ergaenzt werden, ist aber (nach den bisherigen falschen
    Fallback-Versuchen mit dem falschen Key) bewusst NICHT zusaetzlich
    verlangt, um nicht erneut eine zu strenge Bedingung einzubauen."""
    try:
        gdoc = Gui.ActiveDocument
        if gdoc is None or gdoc.ActiveView is None:
            return None
        active = gdoc.ActiveView.getActiveObject("assembly")
        if active is None or not active.isDerivedFrom("Assembly::AssemblyObject"):
            return None
        return active
    except Exception:
        return None


def _copy_properties(src, dst, skip=_SKIP_PROPERTIES):
    """Kopiert generisch alle Properties (inkl. custom Eitech-Properties wie
    radius/suppress_in_BOM), damit kuenftige neue Properties automatisch
    mitgenommen werden, ohne dieses Skript anzupassen. Wird sowohl fuer das
    Dokumentobjekt als auch (separat) fuer dessen ViewObject aufgerufen -
    Farbe/Material (OverrideMaterial, ShapeMaterial) haengen am ViewObject,
    nicht am Dokumentobjekt selbst, siehe paint.py."""
    for prop in src.PropertiesList:
        if prop in skip:
            continue
        try:
            if prop not in dst.PropertiesList:
                group = src.getGroupOfProperty(prop)
                typ = src.getTypeIdOfProperty(prop)
                dst.addProperty(typ, prop, group)
            setattr(dst, prop, getattr(src, prop))
        except Exception:
            pass


def _refresh_override_materials(doc):
    """Workaround wie refresh_colors.py: OverrideMaterial aller betroffenen
    Link-Instanzen im Dokument aus/an triggern, damit per-Instanz zugewiesene
    Farben korrekt angezeigt werden. Noetig sowohl beim Start dieses Makros
    (derselbe Effekt wie beim Oeffnen einer Datei: die zuletzt angelegte
    Kopie zeigt ohne den Trigger die Basisfarbe) als auch nach jedem
    Duplizieren (das Anlegen eines weiteren Links faellt sonst auf eine
    bereits vorhandene, bisher korrekt eingefaerbte Kopie zurueck). Reine
    Property-Umschaltung, kein Recompute -> guenstig genug, um es immer
    mitlaufen zu lassen."""
    for o in doc.Objects:
        try:
            vobj = o.ViewObject
            if vobj is None or not hasattr(vobj, "OverrideMaterial"):
                continue
            if not vobj.OverrideMaterial:
                continue
            vobj.OverrideMaterial = False
            vobj.OverrideMaterial = True
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Duplizieren
# ---------------------------------------------------------------------------
def duplicate_selected(offset_vec, target_doc, target_parent):
    """target_doc/target_parent kommen NICHT aus einer frischen App.Active
    Document/_active_assembly()-Abfrage hier drin, sondern werden dem Panel
    beim Oeffnen (oder per "Ziel neu erfassen") EINMAL uebergeben (siehe
    DuplicatePartPanel._capture_target). Grund: Gui.Selection.addSelection()
    setzt bei Auswahl eines Objekts aus einem ANDEREN Dokument (z.B. ein
    Teil, das optisch Teil einer starren/Rigid-Subassembly ist, aber
    tatsaechlich zu deren eigener .FCStd-Datei gehoert) automatisch
    App.ActiveDocument/Gui.ActiveDocument auf DIESES fremde Dokument um -
    unabhaengig davon, welcher Tab im FreeCAD-Fenster sichtbar ist. Direkt
    beim Button-Klick frisch abgefragt, waere "die aktive Assembly" nach
    dem Anklicken eines Subassembly-Teils faelschlich None bzw. die falsche
    (fremde) Assembly - bestaetigt durch Log: nach Klick auf ein Teil in
    Subassembly 'Gleiter' waren sowohl App.ActiveDocument als auch
    Gui.ActiveDocument auf 'Gleiter' umgesprungen, obwohl der Nutzer
    weiterhin in der Top-Level-Assembly gearbeitet hat."""
    link_obj = _get_selected_link()
    if link_obj is None:
        App.Console.PrintMessage("duplicate_part.py: kein Bauteil erkannt (Selektion leer/kein Link).\n")
        return None, "Kein Assembly-Bauteil markiert."

    # --- Diagnose-Logging ------------------------------------------------
    App.Console.PrintMessage(
        "duplicate_part.py: Link zum Bauteil = '%s' (Label '%s', TypeId %s, Dokument '%s')\n"
        % (link_obj.Name, link_obj.Label, link_obj.TypeId, link_obj.Document.Name)
    )
    App.Console.PrintMessage(
        "duplicate_part.py: aktuell (live, evtl. verfaelscht) App.ActiveDocument = '%s' ; "
        "Gui.ActiveDocument = '%s'\n"
        % (App.ActiveDocument.Name if App.ActiveDocument else "None",
           Gui.ActiveDocument.Document.Name if Gui.ActiveDocument else "None")
    )
    App.Console.PrintMessage(
        "duplicate_part.py: gepinntes Ziel-Dokument = '%s' ; gepinnte Ziel-Assembly = %s\n"
        % (target_doc.Name if target_doc else "None",
           ("'%s' (Label '%s')" % (target_parent.Name, target_parent.Label))
           if target_parent is not None else "None")
    )
    # ----------------------------------------------------------------------

    if target_doc is None or target_parent is None:
        return None, (
            "Keine Ziel-Assembly gepinnt. Bitte das Panel einmal schliessen "
            "und aus der gewuenschten Assembly heraus neu starten (oder "
            "'Ziel neu erfassen' klicken), dann erneut versuchen."
        )

    doc = target_doc

    # "Einfacher Fall" (lokale Placement + Versatz sinnvoll): das Original
    # liegt bereits im selben Dokument UND im selben Container wie das
    # Ziel. Sobald das Original aus einem anderen Dokument/Container kommt
    # (typischerweise: eine Rigid-Subassembly), ist eine Position relativ
    # zum Original nicht aussagekraeftig - dann einfach mit Standard-
    # Placement einfuegen, wie "Komponente einfuegen".
    reparented = (link_obj.Document is not doc) or (
        target_parent is not _find_parent_group(link_obj)
    )
    doc.openTransaction("Teil duplizieren")
    try:
        new_link = doc.addObject(link_obj.TypeId, link_obj.Name)
        new_name = new_link.Name  # fuer den Gueltigkeits-Check nach recompute()
        _copy_properties(link_obj, new_link)

        # Farbe/Material (OverrideMaterial + ShapeMaterial, per-Instanz via
        # paint.py gesetzt) haengen am ViewObject, nicht am Dokumentobjekt -
        # muss separat kopiert werden, sonst erscheint die Kopie ungefaerbt.
        src_vp = link_obj.ViewObject
        dst_vp = new_link.ViewObject
        if src_vp is not None and dst_vp is not None:
            _copy_properties(src_vp, dst_vp, skip=set())

        if reparented:
            # Teil kommt aus einer anderen (Sub-)Assembly als der Ziel-
            # Assembly - keine Versatz-/Placement-Berechnung, einfach mit
            # Standard-Placement einfuegen (wie "Komponente einfuegen").
            # Weniger Rechnerei hier = weniger moegliche Reibung mit dem
            # Assembly-Solver, der auf neu hinzugefuegte, noch unverbundene
            # Teile in einer bereits geloesten Baugruppe empfindlich
            # reagieren kann.
            pass
        else:
            new_link.Placement = App.Placement(
                link_obj.Placement.Base + offset_vec,
                link_obj.Placement.Rotation,
            )

        if target_parent is not None:
            target_parent.addObject(new_link)

        doc.recompute()

        # Der Assembly-Solver kann bei einem neu hinzugefuegten, noch
        # unverbundenen Teil in einer bereits geloesten Baugruppe mit
        # "Solve failed" scheitern und das Objekt dabei intern wieder
        # entfernen (Report View zeigt dann "pending remove of ..." +
        # "invalid vector subscript", aber es wird KEINE Python-Exception
        # ausgeloest) - also nach dem Recompute explizit pruefen, ob die
        # Kopie noch existiert, statt mit einem ungueltigen Objekt
        # weiterzuarbeiten (das fuehrte vorher zum Absturz bei der
        # anschliessenden Selektion).
        if doc.getObject(new_name) is None:
            doc.commitTransaction()
            return None, (
                "Der Assembly-Solver hat die Kopie beim Neuberechnen wieder "
                "entfernt ('Solve failed', siehe Report View). Bitte pruefen, "
                "ob das Original-Teil moeglicherweise selbst schlecht "
                "definierte Bindungen/Joints hat."
            )

        _refresh_override_materials(doc)
    except Exception as exc:
        doc.abortTransaction()
        return None, str(exc)

    doc.commitTransaction()
    return new_link, None


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------
AXES = {
    "Z (Standard, hoch)": App.Vector(0, 0, 1),
    "X": App.Vector(1, 0, 0),
    "Y": App.Vector(0, 1, 0),
}


class _DupSelObserver:
    def __init__(self, panel):
        self._panel = panel

    def addSelection(self, doc, obj, sub, pnt):
        self._panel.update_status()

    def clearSelection(self, doc):
        self._panel.update_status()


class DuplicatePartPanel(QtWidgets.QWidget):

    def __init__(self, parent=None):
        super().__init__(parent, QtCore.Qt.Tool | QtCore.Qt.WindowStaysOnTopHint)
        self.setWindowTitle("Teil duplizieren")
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self._observer = None
        self._target_doc = None
        self._target_assembly = None
        self._build_ui()
        self._ensure_observer()
        self._capture_target()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        self.lbl_target = QtWidgets.QLabel("")
        self.lbl_target.setWordWrap(True)
        layout.addWidget(self.lbl_target)

        self.recapture_btn = QtWidgets.QPushButton("Ziel neu erfassen")
        self.recapture_btn.setToolTip(
            "Merkt sich erneut, welches Dokument/welche Assembly gerade "
            "aktiv ist - falls Sie inzwischen zu einer anderen Assembly "
            "gewechselt haben. Anklicken, WAEHREND die gewuenschte "
            "Ziel-Assembly aktiv ist (noch bevor Sie ein Teil aus einer "
            "Subassembly markieren, das kann die aktive Auswahl von "
            "FreeCAD naemlich verfaelschen)."
        )
        self.recapture_btn.clicked.connect(self._capture_target)
        layout.addWidget(self.recapture_btn)

        self.lbl_status = QtWidgets.QLabel("<i>Teil im 3D-View markieren ...</i>")
        self.lbl_status.setStyleSheet("color: gray; padding: 1px;")
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)

        offset_row = QtWidgets.QHBoxLayout()
        offset_row.addWidget(QtWidgets.QLabel("Versatz:"))
        self.offset_spin = QtWidgets.QDoubleSpinBox()
        self.offset_spin.setSuffix(" mm")
        self.offset_spin.setRange(-1000.0, 1000.0)
        self.offset_spin.setValue(20.0)
        offset_row.addWidget(self.offset_spin)

        self.axis_combo = QtWidgets.QComboBox()
        self.axis_combo.addItems(list(AXES.keys()))
        offset_row.addWidget(self.axis_combo)
        layout.addLayout(offset_row)

        self.dup_btn = QtWidgets.QPushButton("Kopie erstellen")
        self.dup_btn.clicked.connect(self.on_duplicate)
        layout.addWidget(self.dup_btn)

        self.setFixedWidth(300)

    def _ensure_observer(self):
        self._observer = _DupSelObserver(self)
        Gui.Selection.addObserver(self._observer)

    def _capture_target(self):
        """Merkt sich JETZT das aktive Dokument und die aktive Assembly als
        Ziel fuer alle folgenden Duplizierungen - wird NICHT bei jedem
        Button-Klick neu abgefragt, weil das Markieren eines Teils aus
        einer (fremden) Subassembly App.ActiveDocument/Gui.ActiveDocument
        auf deren Dokument umspringen laesst (siehe duplicate_selected()-
        Docstring)."""
        self._target_doc = App.ActiveDocument
        self._target_assembly = _active_assembly()
        if self._target_doc is None or self._target_assembly is None:
            self.lbl_target.setText(
                "<b style='color:darkred;'>Keine Ziel-Assembly aktiv!</b> "
                "Bitte die gewuenschte Assembly aktivieren und "
                "'Ziel neu erfassen' klicken."
            )
        else:
            self.lbl_target.setText(
                "Ziel: <b>%s</b> <small>(%s)</small>"
                % (self._target_assembly.Label, self._target_doc.Name)
            )

    def update_status(self):
        link_obj = _get_selected_link()
        if link_obj is None:
            self.lbl_status.setText("<i>Teil im 3D-View markieren ...</i>")
            self.lbl_status.setStyleSheet("color: gray; padding: 1px;")
        else:
            self.lbl_status.setText("Markiert: <b>%s</b>" % link_obj.Label)
            self.lbl_status.setStyleSheet("padding: 1px;")

    def on_duplicate(self):
        axis = AXES[self.axis_combo.currentText()]
        offset_vec = axis * self.offset_spin.value()

        new_link, error = duplicate_selected(offset_vec, self._target_doc, self._target_assembly)
        if error:
            QtWidgets.QMessageBox.warning(self, "Teil duplizieren", error)
            return

        label = new_link.Label
        try:
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(new_link)
        except Exception:
            pass  # new_link wurde in duplicate_selected() bereits validiert,
                  # aber im Zweifel lieber keinen Absturz bei der Selektion
        Gui.updateGui()
        App.Console.PrintMessage("duplicate_part.py: Kopie erstellt: '%s'\n" % label)

    def closeEvent(self, event):
        if self._observer is not None:
            try:
                Gui.Selection.removeObserver(self._observer)
            except Exception:
                pass
            self._observer = None
        event.accept()


# ---------------------------------------------------------------------------
# Einstiegspunkt
# ---------------------------------------------------------------------------
if App.ActiveDocument is None:
    QtWidgets.QMessageBox.warning(None, "Teil duplizieren", "Kein aktives Dokument.")
else:
    _refresh_override_materials(App.ActiveDocument)

    mw = Gui.getMainWindow()
    existing = mw.findChild(QtWidgets.QWidget, "EitechDuplicatePartPanel")
    if existing:
        existing.close()

    panel = DuplicatePartPanel(mw)
    panel.setObjectName("EitechDuplicatePartPanel")
    panel.show()
