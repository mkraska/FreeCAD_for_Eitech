"""
refresh_colors.py – FreeCAD Makro
Ablage: C:/Users/kraska/AppData/Roaming/FreeCAD/v1-1/Macro/refresh_colors.py

Zweck: Alle App::Link-Objekte mit OverrideMaterial=True neu triggern,
damit die zugewiesene Farbe korrekt angezeigt wird.
Einmalig nach dem Laden einer Assembly ausführen.
Workaround für FreeCAD-Bug bis v1.1 – in neueren Versionen nicht mehr nötig.
"""

import FreeCAD as App

count = 0
for doc in App.listDocuments().values():
    for obj in doc.Objects:
        try:
            vobj = obj.ViewObject
            if vobj is None: continue
            if not hasattr(vobj, 'OverrideMaterial'): continue
            if not vobj.OverrideMaterial: continue
            vobj.OverrideMaterial = False
            vobj.OverrideMaterial = True
            count += 1
        except Exception:
            pass

App.Console.PrintMessage(f"[refresh_colors] {count} Link(s) neu eingefärbt.\n")
