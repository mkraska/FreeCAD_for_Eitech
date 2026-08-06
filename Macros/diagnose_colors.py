# -*- coding: utf-8 -*-
"""
diagnose_colors.py

Zeigt die komplette Instanzfarb-Zuordnung an (dieselbe Logik wie
export_visible.py), OHNE zu exportieren - zum manuellen Durchsehen,
ob irgendwelche Zuordnungen offensichtlich falsch aussehen (z.B.
Schrauben mit einer Farbe, die eigentlich zu einem Elastikstellring
gehört).
"""

import FreeCAD as App

ASSEMBLY_CONTAINER_TYPES = {"Assembly::AssemblyObject", "Assembly::AssemblyLink"}


def get_effective_group(obj):
    """Liefert (Kinder-Liste, force_container). Fällt auf
    LinkedObject.Group zurück, wenn obj keine eigene Group hat, aber
    ein App::Link auf einen Container mit Group ist (Kinder leben nur
    im Quelldokument) - force_container=True in dem Fall, weil so ein
    Link oft trotzdem eine eigene, gültige Shape hat und sonst
    fälschlich als unzerlegtes Blatt behandelt würde."""
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


def collect_source_colors(obj, color_map, path, trace):
    key = (obj.Document.Name, obj.Name)
    if key in path:
        return
    path = path | {key}

    group, force_container = get_effective_group(obj)
    own_shape = getattr(obj, "Shape", None)
    has_own_shape = own_shape is not None and not own_shape.isNull()
    is_assembly_container = obj.TypeId in ASSEMBLY_CONTAINER_TYPES

    if group and (is_assembly_container or not has_own_shape or force_container or obj.TypeId == "App::Link"):
        linked = getattr(obj, "LinkedObject", None)
        source_group = getattr(linked, "Group", None) if linked is not None else None
        if source_group:
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
                    continue
                used.add(best_i)
                src_vo = getattr(source_group[best_i], "ViewObject", None)
                if src_vo is not None and getattr(src_vo, "OverrideMaterial", False):
                    try:
                        color = tuple(src_vo.ShapeMaterial.DiffuseColor)
                        color_map[(child.Document.Name, child.Name)] = color
                        trace.append(
                            (obj.Name, best_dist, child.Label, source_group[best_i].Label, color)
                        )
                    except Exception:
                        pass
        for child in group:
            collect_source_colors(child, color_map, path, trace)
        return

    own_vo = getattr(obj, "ViewObject", None)
    if own_vo is not None and getattr(own_vo, "OverrideMaterial", False):
        try:
            color = tuple(own_vo.ShapeMaterial.DiffuseColor)
            color_map[(obj.Document.Name, obj.Name)] = color
            trace.append(("(direkt)", None, obj.Label, obj.Label, color))
        except Exception:
            pass


def get_top_level_objects(doc):
    grouped_names = set()
    for obj in doc.Objects:
        group = getattr(obj, "Group", None)
        if group:
            for child in group:
                grouped_names.add(child.Name)
    return [obj for obj in doc.Objects if obj.Name not in grouped_names]


def diagnose(doc=None):
    doc = doc or App.ActiveDocument
    color_map = {}
    trace = []
    for root in get_top_level_objects(doc):
        collect_source_colors(root, color_map, frozenset(), trace)

    print("=== %d Farbzuordnungen gefunden ===" % len(color_map))
    print("%-25s %8s %-30s %-30s %s" % ("Container", "Abstand", "Lokal-Label", "Quell-Label", "Farbe"))
    for container, dist, local_label, src_label, color in trace:
        mismatch = " <-- LABEL WEICHT AB!" if local_label != src_label else ""
        dist_str = ("%.4f" % dist) if dist is not None else "-"
        print(
            "%-25s %8s %-30s %-30s %s%s"
            % (container, dist_str, local_label, src_label, color, mismatch)
        )


if __name__ == "__main__":
    diagnose()
