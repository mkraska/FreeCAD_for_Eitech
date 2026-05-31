# stueckliste.py
# Erzeugt eine flache Stückliste als FreeCAD-Spreadsheet.
# Traversiert rekursiv alle Sub-Assemblies und summiert Mengen.
# Erfasst auch direkt erzeugte Features (Seile, Ketten).
#
# Installation:
#   C:/Users/kraska/AppData/Roaming/FreeCAD/v1-1/Macro/stueckliste.py

import FreeCAD as App
import FreeCADGui as Gui

try:
    from PySide6 import QtWidgets
except ImportError:
    from PySide2 import QtWidgets

# TypeIds die als "erzeugte Features" gelten (Seile, Ketten, etc.)
FEATURE_TYPES = {
    "Part::Feature",
    "Part::Compound",
}

# Längengrenzen für Kettenerkennung (nominelle Länge)
KETTE_300 = (250.0, 370.0)   # n=36, nominal 300mm
KETTE_500 = (420.0, 580.0)   # n=60, nominal 500mm


def get_feature_name(obj):
    """
    Gibt einen sprechenden Namen für direkt erzeugte Features zurück.
    - Ketten: Label beginnt mit "Kette_" → Länge aus Property kette_laenge
    - Seile: Label enthält "Seil" → "Seil"
    - Sonstiges: Label
    """
    label = obj.Label

    # Seil: Label enthält "seil" oder endet auf "seil" (Hakenseil, Auslegerseil)
    label_lower = label.lower()
    if "seil" in label_lower:
        return "Seil"

    # Kette: Label beginnt mit "Kette_" (vom Kettenmakro so benannt)
    if label.startswith("Kette_"):
        # Länge aus Property kette_laenge (mm), gesetzt beim Erzeugen
        try:
            if "kette_laenge" in obj.PropertiesList:
                length = float(obj.kette_laenge.getValueAs("mm"))
                if KETTE_300[0] <= length <= KETTE_300[1]:
                    return "Kette 300mm"
                elif KETTE_500[0] <= length <= KETTE_500[1]:
                    return "Kette 500mm"
                else:
                    return f"Kette {length:.0f}mm"
        except Exception:
            pass
        # Fallback: nur "Kette" ohne Länge
        return "Kette"

    return label

# TypeIds die ignoriert werden (Constraints, Ursprünge, etc.)
IGNORE_TYPES = {
    "App::Origin", "App::Line", "App::Plane", "App::Point",
    "Assembly::JointGroup", "App::FeaturePython",
    "Assembly::BomGroup", "Assembly::BomObject",
    "App::TextDocument", "Sketcher::SketchObject",
    "PartDesign::Body",
}

# Labels die ignoriert werden
IGNORE_LABELS = {
    "Joints", "Origin", "Ursprung", "Bills_of_Materials",
    "Bill_of_Materials",
}

# Interne FreeCAD-Labels die nie in der BOM erscheinen sollen
IGNORE_LABEL_PREFIXES = ("Sweep", "Shell", "Solid")


def get_part_name(link_obj):
    """
    Gibt das Label des verlinkten Parts zurück.
    Für Fold-Objekte: Label aus BaseObject-Property.
    Sonst: Link-Kette bis zum echten Part-Objekt folgen.
    """
    # Fold: LinkedObject ist direkt das Part (Part::FeaturePython mit baseObject)
    try:
        linked = getattr(link_obj, "LinkedObject", None)
        if linked is not None and linked.TypeId == "Part::FeaturePython":
            return linked.Label.strip()
    except Exception:
        pass

    # Normaler Link: Kette auflösen
    obj = link_obj
    for _ in range(6):
        linked = getattr(obj, "LinkedObject", None)
        if linked is None:
            break
        obj = linked
    return obj.Label.strip()


def is_suppressed(obj):
    """
    Prüft ob ein Objekt in der Stückliste unterdrückt werden soll.
    Kriterium: Property 'suppress_in_BOM' (Gruppe Eitech) ist True.
    Prüft sowohl das Objekt selbst als auch das verlinkte Part
    (da App::Link die Property meist nicht selbst trägt).
    Wenn die Property nicht vorhanden ist: nicht unterdrücken.
    """
    def check(o):
        try:
            if "suppress_in_BOM" in o.PropertiesList:
                return bool(o.suppress_in_BOM)
        except Exception:
            pass
        return False

    if check(obj): return True

    # Auch verlinktes Objekt prüfen (Link-Kette auflösen)
    current = obj
    for _ in range(6):
        linked = getattr(current, "LinkedObject", None)
        if linked is None: break
        if check(linked): return True
        current = linked

    return False


def is_sub_assembly(link_obj):
    """Prüft ob der Link auf eine Assembly zeigt."""
    linked = link_obj.LinkedObject
    if linked is None:
        return False
    # Direkt Assembly
    if linked.TypeId == "Assembly::AssemblyObject":
        return True
    # Via weiteren Link
    if linked.TypeId == "App::Link":
        inner = linked.LinkedObject
        if inner and inner.TypeId == "Assembly::AssemblyObject":
            return True
    # Hat Group-Property mit Links (zusammengebautes Teil)
    if hasattr(linked, "Group") and linked.Group:
        for child in linked.Group:
            if hasattr(child, "TypeId") and child.TypeId == "App::Link":
                return True
    return False


def collect_parts(obj, counts, depth=0, max_depth=10):
    """
    Traversiert rekursiv die Assembly und zählt alle Teile.
    counts: dict {part_name: count}
    """
    if depth > max_depth:
        return

    type_id = getattr(obj, "TypeId", "")
    label   = getattr(obj, "Label", "")

    # Ignorieren
    if type_id in IGNORE_TYPES:
        return
    if label in IGNORE_LABELS:
        return
    if any(label.startswith(p) for p in IGNORE_LABEL_PREFIXES):
        return

    if type_id == "App::Link":
        if is_suppressed(obj):
            return
        # Fold-Links: gebogene Teile — Name aus verlinktem Objekt
        # (nicht ignorieren, sondern wie normale Teile behandeln)
        # Kette: Label beginnt mit "Kette_"
        if label.startswith("Kette_"):
            name = get_feature_name(obj)
            counts[name] = counts.get(name, 0) + 1
            return
        # Seil: Label enthält "seil"
        if "seil" in label.lower():
            counts["Seil"] = counts.get("Seil", 0) + 1
            return
        if is_sub_assembly(obj):
            # Sub-Assembly: rekursiv in die Kinder
            linked = obj.LinkedObject
            children = []
            if hasattr(linked, "Group"):
                children = linked.Group
            elif linked.TypeId == "App::Link":
                inner = linked.LinkedObject
                if inner and hasattr(inner, "Group"):
                    children = inner.Group
            for child in children:
                collect_parts(child, counts, depth+1, max_depth)
        else:
            # Einzelteil: zählen
            name = get_part_name(obj)
            counts[name] = counts.get(name, 0) + 1

    elif type_id in FEATURE_TYPES:
        # Direkt erzeugtes Feature (Hakenseil, Auslegerseil, etc.)
        if label not in IGNORE_LABELS and not is_suppressed(obj):
            if any(label.startswith(p) for p in IGNORE_LABEL_PREFIXES):
                return
            name = get_feature_name(obj)
            counts[name] = counts.get(name, 0) + 1

    elif type_id == "Assembly::AssemblyObject":
        # Assembly-Objekt: Kinder traversieren
        if hasattr(obj, "Group"):
            for child in obj.Group:
                collect_parts(child, counts, depth+1, max_depth)

    elif type_id == "Assembly::AssemblyLink":
        if is_suppressed(obj):
            return
        linked = getattr(obj, "LinkedObject", None)
        if linked is None: return
        if linked.TypeId == "Assembly::AssemblyObject":
            if hasattr(linked, "Group"):
                for child in linked.Group:
                    collect_parts(child, counts, depth+1, max_depth)
        else:
            name = get_part_name(obj)
            counts[name] = counts.get(name, 0) + 1


def export_csv(doc, counts, sorted_parts):
    """Exportiert die Stückliste als CSV-Datei neben dem FCStd-Dokument."""
    import os
    try:
        doc_path = doc.FileName
        if not doc_path:
            App.Console.PrintWarning("stueckliste: Dokument nicht gespeichert.\n")
            return None
        csv_path = os.path.splitext(doc_path)[0] + "_Stueckliste.csv"
        with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
            f.write("Pos.;Bauteil;Menge\n")
            for idx, (name, count) in enumerate(sorted_parts, 1):
                f.write(str(idx) + ";" + name + ";" + str(count) + "\n")
            total = sum(c for _, c in sorted_parts)
            f.write(";;" + str(total) + "\n")
        App.Console.PrintMessage("stueckliste: CSV: " + csv_path + "\n")
        return csv_path
    except Exception as ex:
        App.Console.PrintWarning("stueckliste: CSV-Export: " + str(ex) + "\n")
        return None


def create_spreadsheet(doc, counts):
    """Erzeugt ein Spreadsheet im Dokument mit der Stückliste."""
    # Altes Stücklisten-Sheet entfernen
    old = doc.getObject("Stueckliste")
    if old:
        doc.removeObject("Stueckliste")

    sheet = doc.addObject("Spreadsheet::Sheet", "Stueckliste")
    sheet.Label = "Stückliste"

    # Header
    sheet.set("A1", "Pos.")
    sheet.set("B1", "Bauteil")
    sheet.set("C1", "Menge")

    # Formatierung Header
    sheet.setStyle("A1:C1", "bold")
    sheet.setBackground("A1:C1", (0.8, 0.8, 0.8, 1.0))

    # Spaltenbreiten
    sheet.setColumnWidth("A", 50)
    sheet.setColumnWidth("B", 200)
    sheet.setColumnWidth("C", 80)

    # Sortiert nach Name
    sorted_parts = sorted(counts.items(), key=lambda x: x[0].strip().lower())

    for i, (name, count) in enumerate(sorted_parts, 1):
        row = i + 1
        sheet.set(f"A{row}", str(i))
        sheet.set(f"B{row}", name)
        sheet.set(f"C{row}", str(count))
        # Zebra-Streifen
        if i % 2 == 0:
            sheet.setBackground(f"A{row}:C{row}", (0.95, 0.95, 1.0, 1.0))

    # Summenzeile
    total_row = len(sorted_parts) + 2
    sheet.set(f"A{total_row}", "")
    sheet.set(f"B{total_row}", "Gesamt")
    sheet.set(f"C{total_row}", str(sum(counts.values())))
    sheet.setStyle(f"A{total_row}:C{total_row}", "bold")

    doc.recompute()
    return sheet, len(sorted_parts)


def create_stueckliste(doc=None):
    if doc is None:
        doc = App.ActiveDocument
    if doc is None:
        App.Console.PrintError("stueckliste: Kein aktives Dokument.\n")
        return

    App.Console.PrintMessage(f"stueckliste: Analysiere '{doc.Name}'...\n")

    counts = {}

    # Starte bei der Assembly oder allen Top-Level-Objekten
    assembly = None
    for obj in doc.Objects:
        if obj.TypeId == "Assembly::AssemblyObject":
            assembly = obj
            break

    if assembly:
        collect_parts(assembly, counts)
    else:
        # Kein Assembly-Objekt — alle Top-Level-Objekte durchsuchen
        for obj in doc.Objects:
            collect_parts(obj, counts)

    if not counts:
        App.Console.PrintWarning("stueckliste: Keine Teile gefunden.\n")
        QtWidgets.QMessageBox.warning(
            Gui.getMainWindow(), "Stückliste",
            "Keine Teile gefunden."
        )
        return

    App.Console.PrintMessage(
        f"stueckliste: {len(counts)} verschiedene Teile, "
        f"{sum(counts.values())} Stück gesamt.\n"
    )
    for name, count in sorted(counts.items()):
        App.Console.PrintMessage(f"  {count:3d}× {name}\n")

    sorted_parts = sorted(counts.items(), key=lambda x: x[0].strip().lower())
    sheet, n = create_spreadsheet(doc, counts)
    csv_path  = export_csv(doc, counts, sorted_parts)

    # Spreadsheet anzeigen
    sheet.ViewObject.doubleClicked()

    msg = f"stueckliste: Spreadsheet '{sheet.Label}' mit {n} Positionen erzeugt."
    if csv_path:
        import os
        msg += f"\nCSV: {os.path.basename(csv_path)}"
    App.Console.PrintMessage(msg + "\n")


if __name__ == "__main__":
    create_stueckliste()
