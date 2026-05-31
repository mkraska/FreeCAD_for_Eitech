# loeseBindungen.py
# Löst Constraints (Bindungen) eines selektierten Bauteils.
# Nicht-modal, bleibt offen für mehrere Teile.
#
# Installation:
#   C:/Users/kraska/AppData/Roaming/FreeCAD/v1-1/Macro/loeseBindungen.py

import FreeCAD as App
import FreeCADGui as Gui

try:
    from PySide6 import QtWidgets, QtCore
except ImportError:
    from PySide2 import QtWidgets, QtCore

_loeseBindungen_dialog = None
_last_link_name        = None
_last_link_candidates  = []
_sel_observer          = None

COLOR_SELF    = (0.0, 0.8, 0.0)   # Grün: betrachtetes Teil
COLOR_CHECKED = (0.7, 1.0, 0.7)   # Hellgrün: angehakte Partner



# ---------------------------------------------------------------------------
# SelectionObserver
# ---------------------------------------------------------------------------

class _LinkSelObserver:
    def addSelection(self, doc, obj, sub, pnt):
        global _last_link_name, _last_link_candidates, _loeseBindungen_dialog

        # Wenn Dialog wartet: Teil-Selektion weiterleiten
        if (_loeseBindungen_dialog is not None
                and _loeseBindungen_dialog.isVisible()
                and _loeseBindungen_dialog.waiting_for_selection):
            active_doc = App.ActiveDocument
            if active_doc is None:
                return
            link = _find_link_from_event(active_doc, doc, obj, sub)
            if link:
                _loeseBindungen_dialog._load_part(link)
                return
            # Fallback: suche via Part-Dokument
            candidates = _find_candidates_for_doc(active_doc, doc)
            if len(candidates) == 1:
                _loeseBindungen_dialog._load_part(candidates[0])
            # Mehrdeutig: Hinweis in Listenüberschrift
            _loeseBindungen_dialog.lbl_list_hdr.setText(
                "<b>→ Bitte Teil doppelklicken</b>")
            return

        # Dialog offen aber nicht wartend: ignorieren
        if (_loeseBindungen_dialog is not None
                and _loeseBindungen_dialog.isVisible()):
            return

        active_doc = App.ActiveDocument
        if active_doc is None:
            return
        link = _find_link_from_event(active_doc, doc, obj, sub)
        if link:
            _last_link_name       = link.Name
            _last_link_candidates = [link.Name]
        else:
            # Mehrere Kandidaten aus Part-Dokument
            candidates = _find_candidates_for_doc(active_doc, doc)
            _last_link_candidates = [o.Name for o in candidates]
            _last_link_name = candidates[0].Name if len(candidates) == 1 else None


def _find_link_from_event(active_doc, doc, obj, sub):
    """Versucht den App::Link aus einem Selection-Event zu bestimmen."""
    # Direkt im Assembly-Dokument
    if doc == active_doc.Name:
        link = active_doc.getObject(obj)
        if link and link.TypeId == "App::Link":
            return link
    # Sub-Pfad: erstes Segment ist Link-Name
    if sub and '.' in sub:
        parts = sub.split('.')
        if parts[0]:
            link = active_doc.getObject(parts[0])
            if link and link.TypeId == "App::Link":
                return link
    return None


def _find_candidates_for_doc(active_doc, part_doc_name):
    """Findet alle App::Links die auf ein bestimmtes Part-Dokument zeigen."""
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
        _sel_observer = _LinkSelObserver()
        Gui.Selection.addObserver(_sel_observer)


# ---------------------------------------------------------------------------
# Highlight-Hilfsfunktionen
# ---------------------------------------------------------------------------

def _set_color(obj, color):
    try:
        vo = obj.ViewObject
        orig_override = vo.OverrideMaterial
        orig_diffuse  = (vo.ShapeMaterial.DiffuseColor
                         if hasattr(vo.ShapeMaterial, "DiffuseColor")
                         else (0.8, 0.8, 0.8))
        vo.OverrideMaterial = True
        vo.ShapeMaterial.DiffuseColor = color
        return (orig_override, orig_diffuse)
    except Exception:
        return None


def _restore_color(obj, saved):
    if saved is None:
        return
    try:
        orig_override, orig_diffuse = saved
        vo = obj.ViewObject
        vo.ShapeMaterial.DiffuseColor = orig_diffuse
        vo.OverrideMaterial = orig_override
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Constraint-Suche
# ---------------------------------------------------------------------------

def _find_constraints(doc, obj):
    result = []
    for c in doc.Objects:
        if c.TypeId != "App::FeaturePython":
            continue
        refs_match = [r for r in c.OutList if r.Name == obj.Name]
        if refs_match:
            others = [r for r in c.OutList if r.Name != obj.Name]
            result.append((c, others))
    return result


# ---------------------------------------------------------------------------
# Hilfsfunktionen für Sub-Assembly-Suche
# ---------------------------------------------------------------------------

def _find_constraints_in_other_docs(current_doc, link):
    """
    Sucht Bindungen für ein Teil indem die Link-Kette verfolgt wird.
    link.LinkedObject kann ein weiterer App::Link in einer Sub-Assembly sein.
    Gibt (doc, link_in_doc, constraints) zurück.
    """
    # Folge der Link-Kette durch alle Dokumente
    visited_docs = {current_doc.Name}
    cur = link
    for _ in range(6):
        linked = getattr(cur, "LinkedObject", None)
        if linked is None:
            break
        linked_doc = linked.Document
        if linked_doc.Name not in visited_docs:
            visited_docs.add(linked_doc.Name)
            # Ist linked selbst ein App::Link in einer Assembly?
            if linked.TypeId == "App::Link":
                constraints = _find_constraints(linked_doc, linked)
                if constraints:
                    return linked_doc, linked, constraints
            # Suche in diesem Dokument nach Links die auf cur zeigen
            for o in linked_doc.Objects:
                if o.TypeId == "App::Link" and o.Name == cur.Name:
                    constraints = _find_constraints(linked_doc, o)
                    if constraints:
                        return linked_doc, o, constraints
        cur = linked

    # Fallback: alle geöffneten Dokumente nach Link mit gleichem Name durchsuchen
    for doc_name, doc in App.listDocuments().items():
        if doc_name in visited_docs:
            continue
        for o in doc.Objects:
            if o.TypeId == "App::Link" and o.Name == link.Name:
                constraints = _find_constraints(doc, o)
                if constraints:
                    return doc, o, constraints
    return None, None, []


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class LoesDialog(QtWidgets.QDialog):
    def __init__(self, doc, parent=None):
        super().__init__(parent or Gui.getMainWindow())
        self.doc  = doc
        self.obj  = None
        self.waiting_for_selection = False
        self._highlighted = {}    # name → (obj, saved_color)
        self.setWindowTitle("Bindungen")
        self.setWindowFlags(self.windowFlags() |
                            QtCore.Qt.WindowStaysOnTopHint)
        self.setMinimumWidth(500)
        self._build_ui()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        self.lbl_part = QtWidgets.QLabel("<i>Kein Teil gewählt</i>")
        self.lbl_part.setStyleSheet("font-weight: bold; padding: 4px;")
        layout.addWidget(self.lbl_part)

        # Listenüberschrift + "Teil wählen"-Button
        row_hdr = QtWidgets.QHBoxLayout()
        self.lbl_list_hdr = QtWidgets.QLabel("Bindungen:")
        row_hdr.addWidget(self.lbl_list_hdr)
        row_hdr.addStretch()
        btn_pick = QtWidgets.QPushButton("Teil wählen")
        btn_pick.setFixedWidth(80)
        btn_pick.clicked.connect(self._request_selection)
        row_hdr.addWidget(btn_pick)
        layout.addLayout(row_hdr)

        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setSelectionMode(
            QtWidgets.QAbstractItemView.SingleSelection)
        self.list_widget.currentItemChanged.connect(self._on_item_clicked)
        self.list_widget.itemChanged.connect(self._on_check_changed)
        layout.addWidget(self.list_widget)

        row_sel = QtWidgets.QHBoxLayout()
        btn_all  = QtWidgets.QPushButton("Alle")
        btn_none = QtWidgets.QPushButton("Keine")
        btn_all.setFixedWidth(44)
        btn_none.setFixedWidth(44)
        btn_all.setToolTip("Alle Del-Buttons aktivieren")
        btn_none.setToolTip("Alle Del-Buttons deaktivieren")
        btn_all.clicked.connect(self._select_all)
        btn_none.clicked.connect(self._select_none)
        row_sel.addWidget(btn_all)
        row_sel.addWidget(btn_none)
        row_sel.addStretch()
        layout.addLayout(row_sel)

        row_btn = QtWidgets.QHBoxLayout()
        self.btn_del = QtWidgets.QPushButton("Confirm Del")
        self.btn_del.setToolTip(
            "Löscht alle mit Del vorgemerkten Bindungen")
        self.btn_del.setDefault(True)
        self.btn_del.setEnabled(False)
        self.btn_del.clicked.connect(self._on_delete)
        btn_close = QtWidgets.QPushButton("Schließen")
        btn_close.clicked.connect(self._on_close)
        row_btn.addStretch()
        row_btn.addWidget(self.btn_del)
        row_btn.addWidget(btn_close)
        layout.addLayout(row_btn)

    # --- Teil laden ---

    def _load_part(self, link):
        """Lädt die Bindungen eines Links in den Dialog."""
        # Schließe Info-Popup falls offen
        self.waiting_for_selection = False

        # Farben zurücksetzen
        self._restore_all_colors()
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        self.list_widget.blockSignals(False)

        self.obj = link
        self.lbl_part.setText("Teil: <b>" + link.Label + "</b>"
                               + " <small>(" + link.Name + ")</small>")
        self.lbl_list_hdr.setText("Bindungen:")

        constraints = _find_constraints(self.doc, link)
        if not constraints:
            # Suche Bindungen in anderen geöffneten Dokumenten
            found_doc, found_link, found_constraints =                 _find_constraints_in_other_docs(self.doc, link)
            if found_doc and found_constraints:
                msg = (" — <i>keine Bindungen hier</i><br>"
                       "<small>Bindungen in <b>" + (found_doc.Label or found_doc.Name) +
                       "</b> gefunden</small>")
                self.lbl_part.setText(self.lbl_part.text() + msg)
                reply = QtWidgets.QMessageBox.question(
                    self,
                    "Bindungen in Sub-Assembly",
                    "Dieses Teil hat " + str(len(found_constraints)) +
                    " Bindung(en) in '" + (found_doc.Label or found_doc.Name) + "'. Zu dieser Assembly wechseln?",
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
                if reply == QtWidgets.QMessageBox.Yes:
                    App.setActiveDocument(found_doc.Name)
                    Gui.setActiveDocument(found_doc.Name)
                    self.doc = found_doc
                    self._load_part(found_link)
                    return
            else:
                self.lbl_part.setText(self.lbl_part.text() +
                                       " — <i>keine Bindungen</i>")
            self.btn_del.setEnabled(False)
            self._highlight_obj(link, COLOR_SELF)
            Gui.updateGui()
            return

        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        for c_obj, others in constraints:
            # GroundedJoint erkennen
            if hasattr(c_obj, 'ObjectToGround'):
                label = "⚓ " + c_obj.Label + "  (gegrounded)"
            else:
                other_labels = [o.Label for o in others
                                if o.TypeId == "App::Link"]
                label = c_obj.Label
                if other_labels:
                    label += "  →  " + ", ".join(other_labels)
            item = QtWidgets.QListWidgetItem()
            item.setData(QtCore.Qt.UserRole, (c_obj, others))
            self.list_widget.addItem(item)

            # Widget: Del-Toggle | Label | Edit
            row_widget = QtWidgets.QWidget()
            row_layout = QtWidgets.QHBoxLayout(row_widget)
            row_layout.setContentsMargins(4, 2, 4, 2)
            row_layout.setSpacing(4)

            btn_del = QtWidgets.QPushButton("Del")
            btn_del.setCheckable(True)
            btn_del.setFixedWidth(36)
            btn_del.setToolTip("Zum Löschen vormerken")
            btn_del.toggled.connect(
                lambda checked, it=item: self._on_del_toggled(it, checked))
            row_layout.addWidget(btn_del)

            lbl = QtWidgets.QLabel(label)
            lbl.setWordWrap(False)
            row_layout.addWidget(lbl, 1)

            btn_edit = QtWidgets.QPushButton("Edit")
            btn_edit.setFixedWidth(36)
            btn_edit.setToolTip("Bindung editieren")
            btn_edit.clicked.connect(
                lambda checked, o=c_obj: self._edit_constraint(o))
            row_layout.addWidget(btn_edit)

            item.setSizeHint(row_widget.sizeHint())
            self.list_widget.setItemWidget(item, row_widget)

        self.list_widget.blockSignals(False)

        self.btn_del.setEnabled(True)
        self._update_highlights()
        Gui.updateGui()
        App.Console.PrintMessage(
            "loese: " + str(len(constraints)) +
            " Bindungen fuer '" + link.Label + "'\n")

    def _request_selection(self):
        """Setzt Dialog in Wartestand auf Teilselektion."""
        self.waiting_for_selection = True
        self._restore_all_colors()
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        self.list_widget.blockSignals(False)
        self.obj = None
        self.lbl_part.setText("<i>Kein Teil gewählt</i>")
        self.lbl_list_hdr.setText(
            "<b>→ Bitte Teil doppelklicken</b>")
        self.btn_del.setEnabled(False)
        Gui.Selection.clearSelection()
        Gui.updateGui()

    # --- Einfärbung ---

    def _highlight_obj(self, obj, color):
        if obj.Name in self._highlighted:
            return
        saved = _set_color(obj, color)
        if saved is not None:
            self._highlighted[obj.Name] = (obj, saved)

    def _restore_all_colors(self):
        for name, (obj, saved) in self._highlighted.items():
            _restore_color(obj, saved)
        self._highlighted = {}

    def _on_del_toggled(self, item, checked):
        """Del-Button gedrückt/losgelassen → Farbe und Highlights aktualisieren."""
        # Sender-Button rot/normal einfärben
        w = self.list_widget.itemWidget(item)
        if w:
            btn = w.findChild(QtWidgets.QPushButton)
            if btn and btn.isCheckable():
                if checked:
                    btn.setStyleSheet(
                        "QPushButton { background-color: #cc3333; color: white; "
                        "font-weight: bold; border-radius: 3px; }")
                else:
                    btn.setStyleSheet("")
        self._update_highlights()

    def _edit_constraint(self, c_obj):
        """Öffnet den FreeCAD Joint-Editierdialog per doubleClicked."""
        try:
            c_obj.ViewObject.doubleClicked()
        except Exception as e:
            App.Console.PrintWarning(f"loese: Edit fehlgeschlagen: {e}\n")

    def _delete_constraint(self, c_obj, others):
        """Löscht eine einzelne Bindung direkt."""
        doc = c_obj.Document
        try:
            for o in others:
                if o.Name in self._highlighted:
                    obj, saved = self._highlighted.pop(o.Name)
                    _restore_color(obj, saved)
            doc.removeObject(c_obj.Name)
            doc.recompute()
            App.Console.PrintMessage(f"loese: Gelöscht: {c_obj.Label}\n")
        except Exception as e:
            App.Console.PrintWarning(f"loese: Löschen fehlgeschlagen: {e}\n")
            return
        # Liste neu laden
        if self.obj:
            _, link, constraints = _find_constraints_recursive(self.obj)
            if link and constraints:
                self._populate_list(link, constraints)
            else:
                self.list_widget.clear()
                self.lbl_list_hdr.setText("Bindungen: <i>keine</i>")
                self.btn_del.setEnabled(False)

    def _get_checked_refs(self):
        refs = {}
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if not self._item_is_checked(item):
                continue
            c_obj, others = item.data(QtCore.Qt.UserRole)
            for r in others:
                if (r.TypeId == "App::Link"
                        and self.obj
                        and r.Name != self.obj.Name):
                    refs[r.Name] = r
        return refs

    def _item_is_checked(self, item):
        """Liest den Del-Toggle-Zustand aus dem eingebetteten Widget."""
        w = self.list_widget.itemWidget(item)
        if w is None:
            return False
        btn = w.findChild(QtWidgets.QPushButton)
        return btn is not None and btn.isChecked()

    def _get_refs_for_item(self, item):
        if item is None:
            return {}
        c_obj, others = item.data(QtCore.Qt.UserRole)
        return {r.Name: r for r in others
                if r.TypeId == "App::Link"
                and self.obj and r.Name != self.obj.Name}

    def _update_highlights(self):
        self._restore_all_colors()
        if self.obj is None:
            return
        # Grün: betrachtetes Teil
        self._highlight_obj(self.obj, COLOR_SELF)
        # Alle Partner sammeln
        alle_partner = {}
        vorselektiert = set()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            c_obj, others = item.data(QtCore.Qt.UserRole)
            for o in others:
                if o.TypeId == "App::Link" and self.obj and o.Name != self.obj.Name:
                    alle_partner[o.Name] = o
            if self._item_is_checked(item):
                vorselektiert.add(id(c_obj))

        # Hellgrün: alle Partner die NICHT vorselektiert sind
        for name, ref in alle_partner.items():
            # Prüfen ob dieser Partner zu einem vorselektierten Joint gehört
            ist_vorselektiert = False
            for i in range(self.list_widget.count()):
                item = self.list_widget.item(i)
                if not self._item_is_checked(item):
                    continue
                c_obj, others = item.data(QtCore.Qt.UserRole)
                if any(o.Name == name for o in others):
                    ist_vorselektiert = True
                    break
            if not ist_vorselektiert:
                self._highlight_obj(ref, COLOR_CHECKED)
        Gui.updateGui()

    def _on_item_clicked(self, current, previous):
        Gui.Selection.clearSelection()
        if current is None:
            self._update_highlights()
            return
        # Refs des angeklickten Eintrags selektieren (blaue Umrandung)
        refs = self._get_refs_for_item(current)
        for name, r in refs.items():
            try:
                Gui.Selection.addSelection(self.doc.Name, r.Name)
            except Exception:
                pass
        # Keine eigene Einfärbung beim Klicken — Feedback via Haken

    def _on_check_changed(self, item):
        self._update_highlights()

    def _select_all(self):
        for i in range(self.list_widget.count()):
            w = self.list_widget.itemWidget(self.list_widget.item(i))
            if w:
                btn = w.findChild(QtWidgets.QPushButton)
                if btn and btn.isCheckable(): btn.setChecked(True)
        self._update_highlights()

    def _select_none(self):
        for i in range(self.list_widget.count()):
            w = self.list_widget.itemWidget(self.list_widget.item(i))
            if w:
                btn = w.findChild(QtWidgets.QPushButton)
                if btn and btn.isCheckable(): btn.setChecked(False)
        self._update_highlights()

    def _on_delete(self):
        to_delete = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if self._item_is_checked(item):
                c_obj, _ = item.data(QtCore.Qt.UserRole)
                to_delete.append(c_obj)

        if not to_delete:
            return

        self._restore_all_colors()
        Gui.Selection.clearSelection()

        for c_obj in to_delete:
            try:
                self.doc.removeObject(c_obj.Name)
            except Exception as ex:
                App.Console.PrintWarning("loese: " + str(ex) + "\n")

        self.doc.recompute()
        Gui.updateGui()
        App.Console.PrintMessage(
            "loese: " + str(len(to_delete)) + " Bindungen geloescht.\n")

        # Warte auf nächste Selektion
        self._request_selection()

    def _on_close(self):
        self._restore_all_colors()
        Gui.Selection.clearSelection()
        Gui.updateGui()
        self.close()

    def closeEvent(self, event):
        self._restore_all_colors()
        Gui.Selection.clearSelection()
        Gui.updateGui()
        event.accept()


# ---------------------------------------------------------------------------
# Hauptfunktion
# ---------------------------------------------------------------------------

def loese_bindungen(doc=None):
    global _loeseBindungen_dialog, _last_link_name, _last_link_candidates
    _ensure_observer()

    if doc is None:
        doc = App.ActiveDocument
    if doc is None:
        App.Console.PrintError("loese_bindungen: Kein aktives Dokument.\n")
        return

    # Bestehenden Dialog in den Vordergrund
    if (_loeseBindungen_dialog is not None
            and _loeseBindungen_dialog.isVisible()):
        _loeseBindungen_dialog.raise_()
        _loeseBindungen_dialog.activateWindow()
        return

    # Dialog öffnen
    dlg = LoesDialog(doc)
    _loeseBindungen_dialog = dlg
    dlg.show()

    # Teil aus letzter Selektion laden
    import time
    time.sleep(0.05)
    QtWidgets.QApplication.processEvents()

    link = None

    if _last_link_name:
        link = doc.getObject(_last_link_name)
        if link and link.TypeId != "App::Link":
            link = None

    # Bei Mehrdeutigkeit: kein Link setzen, Dialog wartet auf Klick

    if link:
        dlg._load_part(link)
    else:
        dlg._request_selection()


if __name__ == "__main__":
    loese_bindungen()
