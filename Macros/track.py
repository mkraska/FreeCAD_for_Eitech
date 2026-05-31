# kette_visualisierung.py  v5
# FreeCAD 1.1 – Raupenketten-Visualisierung mit GUI-Konfigurator

import FreeCAD as App
import FreeCADGui as Gui
import Part
import math

try:
    from PySide6 import QtWidgets, QtCore, QtGui
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui

# ---------------------------------------------------------------------------
# Kettenparameter (mm)
# ---------------------------------------------------------------------------
CHAIN_WIDTH      = 18.0
BAND_HEIGHT      = 1.5
OUTER_RIB_H      = 1.0
OUTER_RIB_W_BOT  = 2.0
OUTER_RIB_W_TOP  = 1.5
INNER_RIB_R      = 2.0
INNER_RIB_W      = 2.5
INNER_RIB_OFFSET = 1.0
CHAIN_COLOR      = (85/255, 85/255, 85/255)

CHAIN_TYPES = [
    {"label": "Standard (n=36, ~300mm)", "n_inner": 36},
    {"label": "Lang     (n=60, ~500mm)", "n_inner": 60},
]

# ---------------------------------------------------------------------------
# Vektorrechnung
# ---------------------------------------------------------------------------
def vadd(a, b):   return (a[0]+b[0], a[1]+b[1], a[2]+b[2])
def vsub(a, b):   return (a[0]-b[0], a[1]-b[1], a[2]-b[2])
def vscale(a, s): return (a[0]*s, a[1]*s, a[2]*s)
def vdot(a, b):   return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]
def vlen(a):      return math.sqrt(vdot(a, a))
def vnorm(a):
    l = vlen(a)
    return (a[0]/l, a[1]/l, a[2]/l) if l > 1e-10 else (0.0, 0.0, 0.0)
def vcross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
def vfc(v):
    return App.Vector(float(v[0]), float(v[1]), float(v[2]))

# ---------------------------------------------------------------------------
# Globales Placement
# ---------------------------------------------------------------------------
def get_global_placement(link_obj):
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

# ---------------------------------------------------------------------------
# LCS_track finden
# ---------------------------------------------------------------------------
def find_lcs_track_links(doc, max_depth=2):
    """
    Sucht rekursiv alle App::Link-Objekte mit LCS_track bis zur gegebenen Tiefe.
    Gibt Liste von (label, obj, chain) zurück.
    chain = Liste der Link-Objekte von der Wurzel bis zur Rolle (für Placement).

    Struktur: ein App::Link kann auf ein Part (hat LCS_track direkt)
    oder auf eine Sub-Assembly (Assembly::AssemblyObject) zeigen.
    Bei Sub-Assembly: deren Group-Property enthält weitere App::Link-Objekte.
    """
    result = []

    def resolve_linked(link_obj):
        """Löst App::Link-Ketten auf bis ein echtes Objekt erreicht wird."""
        obj = link_obj.LinkedObject
        for _ in range(5):
            if obj is None: return None
            if obj.TypeId != "App::Link": return obj
            obj = obj.LinkedObject
        return obj

    def find_lcs(link_obj):
        """
        Sucht LCS_track im Originaldokument des verlinkten Parts.
        Verwendet get_part_document_objects für konsistente Suche.
        """
        for o in get_part_document_objects(link_obj):
            if (o.TypeId == "Part::LocalCoordinateSystem"
                    and o.Label == "LCS_track"
                    and "radius" in o.PropertiesList):
                return o
        return None

    def is_sub_assembly(link_obj):
        """Prüft ob der Link auf eine Assembly zeigt."""
        linked = link_obj.LinkedObject
        if linked is None: return False
        real = resolve_linked(link_obj)
        if real and real.TypeId == "Assembly::AssemblyObject":
            return True
        if linked.TypeId == "App::Link" and hasattr(linked, "Group"):
            return bool(linked.Group)
        return False

    def get_sub_links(link_obj):
        """Gibt die App::Link-Kinder einer Sub-Assembly zurück."""
        linked = link_obj.LinkedObject
        if linked is None: return []
        if hasattr(linked, "Group"):
            grp = [o for o in linked.Group
                   if hasattr(o, "TypeId") and o.TypeId == "App::Link"]
            if grp: return grp
        real = resolve_linked(link_obj)
        if real and hasattr(real, "Group"):
            return [o for o in real.Group
                    if hasattr(o, "TypeId") and o.TypeId == "App::Link"]
        return []

    def get_lcs_data_direct(link_obj, chain):
        """Berechnet Mittelpunkt, Achse, Radius direkt beim Finden."""
        lcs = find_lcs(link_obj)
        if lcs is None: return None
        radius = float(lcs.radius.getValueAs("mm"))
        if len(chain) > 1:
            gp = App.Placement()
            for lnk in chain:
                gp = gp.multiply(lnk.Placement)
        else:
            gp = get_global_placement(link_obj)
        lg  = gp.multiply(lcs.Placement)
        pos = lg.Base
        xax = lg.Rotation.multVec(App.Vector(1, 0, 0))
        return ((float(pos.x), float(pos.y), float(pos.z)),
                (float(xax.x), float(xax.y), float(xax.z)),
                radius)

    def search(obj, depth, chain):
        if not hasattr(obj, "TypeId") or obj.TypeId != "App::Link":
            return
        if obj.LinkedObject is None: return
        lcs = find_lcs(obj)
        if lcs is not None:
            result.append((obj.Label, obj, chain + [obj]))
        elif depth < max_depth and is_sub_assembly(obj):
            for sub_obj in get_sub_links(obj):
                search(sub_obj, depth + 1, chain + [obj])

    for obj in doc.Objects:
        search(obj, 1, [])

    return result

def resolve_to_part(link_obj):
    """
    Löst App::Link-Ketten auf bis ein echtes Part-Objekt erreicht wird.
    Gibt (part_obj, part_doc) zurück - part_doc ist das Originaldokument
    des Parts, nicht das Dokument wo der Link liegt.
    """
    obj = link_obj
    last_link = link_obj
    for _ in range(6):
        linked = getattr(obj, "LinkedObject", None)
        if linked is None: break
        last_link = obj
        obj = linked
    # obj ist jetzt das finale Objekt (z.B. PartDesign::Body)
    # Das Originaldokument ist das Dokument von last_link.LinkedObject
    return obj


def get_part_document_objects(link_obj):
    """
    Gibt alle Objekte im Originaldokument des verlinkten Parts zurück,
    inklusive der Kinder (OutList, Group) aller Objekte — rekursiv.
    Folgt der gesamten Link-Kette bis zum echten Part-Dokument.
    """
    # Folge der Link-Kette bis zum Ende
    obj = link_obj
    for _ in range(6):
        linked = getattr(obj, "LinkedObject", None)
        if linked is None: break
        obj = linked
    # obj ist jetzt das finale Objekt (z.B. PartDesign::Body in Raupenrad_Basis)
    # Sein Dokument ist das Originaldokument
    try:
        doc = obj.Document
    except Exception:
        return []

    # BFS über alle Objekte im Dokument + deren Kinder
    all_objs = []
    seen = set()
    queue = list(doc.Objects)
    while queue:
        o = queue.pop()
        if id(o) in seen: continue
        seen.add(id(o))
        all_objs.append(o)
        if hasattr(o, "OutList"):
            queue.extend(o.OutList)
        if hasattr(o, "Group"):
            queue.extend(o.Group)
    return all_objs


def get_lcs_data(obj, chain=None):
    """
    Gibt (mittelpunkt, achse, radius) für einen Link mit LCS_track zurück.
    chain: Liste von Link-Objekten von der Wurzel bis zu obj.
    Löst App::Link-Ketten auf um das echte Part-Dokument zu finden.
    """
    candidates = get_part_document_objects(obj)
    lcs = None
    for o in candidates:
        if (o.TypeId == "Part::LocalCoordinateSystem"
                and o.Label == "LCS_track"
                and "radius" in o.PropertiesList):
            lcs = o; break
    if lcs is None: return None
    radius = float(lcs.radius.getValueAs("mm"))
    if chain and len(chain) > 1:
        gp = App.Placement()
        for link in chain:
            gp = gp.multiply(link.Placement)
    else:
        gp = get_global_placement(obj)
    lg  = gp.multiply(lcs.Placement)
    pos = lg.Base
    xax = lg.Rotation.multVec(App.Vector(1, 0, 0))
    return (float(pos.x), float(pos.y), float(pos.z)), \
           (float(xax.x), float(xax.y), float(xax.z)), radius

def get_chain_plane(rollen):
    # Normalvektor: X-Achse der ersten Rolle (Rollenachse)
    normal = vnorm(rollen[0][1])

    if len(rollen) >= 3:
        # Ebene aus 3 Punkten: zwei Verbindungsvektoren in der Ebene
        m0 = rollen[0][0]; m1 = rollen[1][0]; m2 = rollen[2][0]
        v1 = vsub(m1, m0); v2 = vsub(m2, m0)
        # Projektion auf Ebene senkrecht zu normal
        v1p = vsub(v1, vscale(normal, vdot(v1, normal)))
        v2p = vsub(v2, vscale(normal, vdot(v2, normal)))
        # e1: erste Richtung in der Ebene
        if vlen(v1p) > 1e-6:
            e1 = vnorm(v1p)
        elif vlen(v2p) > 1e-6:
            e1 = vnorm(v2p)
        else:
            # Fallback: Verbindung erste→zweite Rolle
            d = vsub(rollen[1][0], rollen[0][0])
            e1 = vnorm(vsub(d, vscale(normal, vdot(d, normal))))
    else:
        # 2 Rollen: e1 aus Verbindungsvektor
        d  = vsub(rollen[1][0], rollen[0][0])
        e1 = vnorm(vsub(d, vscale(normal, vdot(d, normal))))

    e2 = vcross(normal, e1)
    return normal, e1, e2

def project_to_plane(point, origin, e1, e2):
    d = vsub(point, origin)
    return (vdot(d, e1), vdot(d, e2))

def unproject(p2d, origin, e1, e2):
    return vadd(origin, vadd(vscale(e1, p2d[0]), vscale(e2, p2d[1])))

def tangente_aussen(m1, r1, m2, r2, cx=None, cy=None):
    """
    Äußere Tangente zwischen zwei Kreisen.
    Wählt die Tangente deren Mittelpunkt am weitesten vom Schwerpunkt (cx,cy)
    der Hülle entfernt ist — das ist immer die Außentangente.
    Wenn cx/cy nicht gegeben: erste Variante (Fallback).
    """
    dx = m2[0]-m1[0]; dy = m2[1]-m1[1]
    d  = math.sqrt(dx*dx + dy*dy)
    if d < 1e-10: return None
    alpha = math.atan2(dy, dx)
    dr    = r1 - r2
    if abs(dr) > d: return None
    beta  = math.asin(max(-1.0, min(1.0, dr/d)))

    best = None; best_dist = -1
    for sign in [+1, -1]:
        theta = alpha + sign * (math.pi/2.0 - beta)
        T1 = (m1[0]+r1*math.cos(theta), m1[1]+r1*math.sin(theta))
        T2 = (m2[0]+r2*math.cos(theta), m2[1]+r2*math.sin(theta))
        if cx is None:
            return (T1, T2)   # Fallback: erste nehmen
        tmx = (T1[0]+T2[0])/2; tmy = (T1[1]+T2[1])/2
        dist = math.sqrt((tmx-cx)**2 + (tmy-cy)**2)
        if dist > best_dist:
            best_dist = dist; best = (T1, T2)

    return best


def cross2d(o, a, b):
    """Kreuzprodukt (a-o) × (b-o). Positiv = CCW."""
    return (a[0]-o[0])*(b[1]-o[1]) - (a[1]-o[1])*(b[0]-o[0])


def convex_hull_ccw(points):
    """
    Graham Scan. Gibt Indizes der konvexen Hülle in CCW-Reihenfolge zurück.
    Berücksichtigt nur die Mittelpunkte — für die Bogenwahl wird die
    Außentangente (linke Seite bei CCW) verwendet.
    """
    n = len(points)
    if n <= 2:
        return list(range(n))
    idx = sorted(range(n), key=lambda i: (points[i][0], points[i][1]))
    lower = []
    for i in idx:
        while len(lower) >= 2 and cross2d(points[lower[-2]], points[lower[-1]], points[i]) <= 0:
            lower.pop()
        lower.append(i)
    upper = []
    for i in reversed(idx):
        while len(upper) >= 2 and cross2d(points[upper[-2]], points[upper[-1]], points[i]) <= 0:
            upper.pop()
        upper.append(i)
    return lower[:-1] + upper[:-1]  # CCW


def compute_segments_2d(rollen_2d, radien):
    """
    Berechnet Wire-Segmente als konvexen Außengürtel (outer belt).
    1. Konvexe Hülle der Rollenmittelpunkte (CCW) bestimmt die Reihenfolge.
    2. Zwischen je zwei Rollen: äußere Tangente auf der linken Seite (CCW-Umlauf).
    3. Bogenwahl: bei CCW-Umlauf ist der Außenbogen immer CW (da < 0).
    Funktioniert korrekt für beliebige Rollenanordnungen und unterschiedliche Radien.
    """
    n = len(rollen_2d)
    if n < 2: return []

    # Konvexe Hülle → CCW-Reihenfolge
    hull = convex_hull_ccw(rollen_2d)
    m    = len(hull)

    # Schwerpunkt der Hüllenpunkte
    cx = sum(rollen_2d[i][0] for i in hull) / m
    cy = sum(rollen_2d[i][1] for i in hull) / m

    # Äußere Tangenten: Mittelpunkt am weitesten vom Schwerpunkt
    tang_pts = []
    for k in range(m):
        i = hull[k]; j = hull[(k+1) % m]
        res = tangente_aussen(rollen_2d[i], radien[i],
                               rollen_2d[j], radien[j], cx, cy)
        if res is None:
            App.Console.PrintError(
                f"kette: Tangente {i}→{j} nicht berechenbar!\n")
            return []
        tang_pts.append(res)

    # Segmente aufbauen
    segments = []
    for k in range(m):
        i = hull[k]
        mx, my = rollen_2d[i]; r = radien[i]
        T_an = tang_pts[(k-1) % m][1]   # einlaufend
        T_ab = tang_pts[k][0]            # auslaufend

        ang_an = math.atan2(T_an[1]-my, T_an[0]-mx)
        ang_ab = math.atan2(T_ab[1]-my, T_ab[0]-mx)

        da_ccw = (ang_ab - ang_an) % (2*math.pi)
        if da_ccw < 1e-6: da_ccw = 2*math.pi
        da_cw = -(2*math.pi - da_ccw)

        # Außenbogen: Bogenmittelpunkt weiter vom Hüllen-Schwerpunkt als Rollenmitte
        d_m = math.sqrt((mx-cx)**2 + (my-cy)**2)
        def arc_centroid_dist(da):
            angle_mid = ang_an + da/2
            bx = mx + r*math.cos(angle_mid)
            by = my + r*math.sin(angle_mid)
            return math.sqrt((bx-cx)**2 + (by-cy)**2)

        da = da_ccw if arc_centroid_dist(da_ccw) > arc_centroid_dist(da_cw) else da_cw

        segments.append({'type':'arc', 'center':(mx,my), 'r':r,
                         'start_angle':ang_an, 'delta':da})
        segments.append({'type':'line', 'start':T_ab, 'end':tang_pts[k][1]})

    return segments

def build_segment_table(segments):
    cum = [0.0]
    for s in segments:
        if s['type']=='arc':
            cum.append(cum[-1]+abs(float(s['delta']))*float(s['r']))
        else:
            dx=s['end'][0]-s['start'][0]; dy=s['end'][1]-s['start'][1]
            cum.append(cum[-1]+math.sqrt(dx*dx+dy*dy))
    return cum, cum[-1]

def point_at_dist_2d(segments, cum, total, dist):
    dist = dist % total
    lo, hi = 0, len(segments)-1
    while lo < hi:
        mid = (lo+hi)//2
        if cum[mid+1] < dist-1e-10: lo=mid+1
        else: hi=mid
    s=segments[lo]; slen=cum[lo+1]-cum[lo]
    local=max(0.0,min(dist-cum[lo],slen))
    frac=local/slen if slen>1e-10 else 0.0
    if s['type']=='arc':
        cx,cy=s['center']; r=float(s['r']); da=float(s['delta'])
        angle=float(s['start_angle'])+da*frac
        x=cx+r*math.cos(angle); y=cy+r*math.sin(angle)
        tx,ty=(-math.sin(angle),math.cos(angle)) if da>=0 \
              else (math.sin(angle),-math.cos(angle))
    else:
        dx=s['end'][0]-s['start'][0]; dy=s['end'][1]-s['start'][1]
        ll=math.sqrt(dx*dx+dy*dy)
        tx,ty=(dx/ll,dy/ll) if ll>1e-10 else (1.0,0.0)
        x=s['start'][0]+dx*frac; y=s['start'][1]+dy*frac
    return x,y,tx,ty

def compute_wire_length(rollennamen, doc):
    """Berechnet Wire-Länge für eine Liste von Rollennamen oder (name,chain)-Tupeln."""
    rollen = []
    for entry in rollennamen:
        name  = entry[0] if isinstance(entry, tuple) else entry
        chain = entry[1] if isinstance(entry, tuple) else None
        obj = next((o for o in doc.Objects
                    if o.TypeId=="App::Link" and o.Label==name), None)
        if obj is None: return None
        data = get_lcs_data(obj, chain)
        if data is None: return None
        rollen.append(data)
    if len(rollen) < 2: return None
    normal, e1, e2 = get_chain_plane(rollen)
    origin = rollen[0][0]
    rollen_2d = [project_to_plane(m, origin, e1, e2) for m,_,_ in rollen]
    radien    = [r for _,_,r in rollen]
    segs = compute_segments_2d(rollen_2d, radien)
    if not segs: return None
    _, total = build_segment_table(segs)
    return total

# ---------------------------------------------------------------------------
# 3D Wire erzeugen
# ---------------------------------------------------------------------------
def make_wire_3d(segments, origin, e1, e2, normal):
    """
    Baut 3D-Wire aus 2D-Segmenten.
    Bögen werden in kurze Liniensegmente aufgeteilt (Polygonalisierung)
    damit alle Punkte exakt auf der Kettenebene liegen und Part.Wire
    keine Lücken findet.
    Anzahl Segmente pro Bogen: 1 pro 5° Bogenwinkel, mindestens 6.
    """
    e1_fc = App.Vector(float(e1[0]), float(e1[1]), float(e1[2]))
    e2_fc = App.Vector(float(e2[0]), float(e2[1]), float(e2[2]))
    orig  = App.Vector(float(origin[0]), float(origin[1]), float(origin[2]))

    def to3d(x, y):
        return orig + e1_fc * x + e2_fc * y

    edges = []
    for s in segments:
        if s['type'] == 'line':
            p1 = to3d(*s['start'])
            p2 = to3d(*s['end'])
            if (p1-p2).Length > 1e-6:
                edges.append(Part.makeLine(p1, p2))
        else:
            cx, cy = s['center']
            r  = float(s['r'])
            a1 = float(s['start_angle'])
            da = float(s['delta'])
            # Anzahl Unterteilungen: 1 pro 5°, min 6
            n_seg = max(6, int(abs(math.degrees(da)) / 5.0 + 0.5))
            pts = []
            for k in range(n_seg + 1):
                angle = a1 + da * k / n_seg
                x = cx + r * math.cos(angle)
                y = cy + r * math.sin(angle)
                pts.append(to3d(x, y))
            for k in range(n_seg):
                if (pts[k] - pts[k+1]).Length > 1e-6:
                    edges.append(Part.makeLine(pts[k], pts[k+1]))

    if not edges: return None
    try:
        return Part.Wire(edges)
    except Exception as ex:
        App.Console.PrintError(f"kette: Wire-Fehler: {ex}\n")
        return None

# ---------------------------------------------------------------------------
# Frames (für Band-Sweep)
# ---------------------------------------------------------------------------
def build_edge_table(wire):
    try:    edges = wire.OrderedEdges
    except: edges = wire.Edges
    cum = [0.0]
    for e in edges: cum.append(cum[-1]+float(e.Length))
    return edges, cum

def point_on_wire(wire, dist, edge_table=None):
    if edge_table is None: edge_table = build_edge_table(wire)
    edges, cum = edge_table
    total = cum[-1]; dist = dist % total
    lo,hi = 0,len(edges)-1
    while lo<hi:
        mid=(lo+hi)//2
        if cum[mid+1]<dist-1e-10: lo=mid+1
        else: hi=mid
    edge=edges[lo]; elen=float(edge.Length)
    local=max(0.0,min(dist-cum[lo],elen))
    t=edge.FirstParameter+(local/elen if elen>1e-10 else 0)*(
        edge.LastParameter-edge.FirstParameter)
    pt=edge.valueAt(t); tan=edge.tangentAt(t); tan.normalize()
    return pt,tan

def compute_frames(wire, n_points, rollen_center, chain_normal, edge_table=None):
    if edge_table is None: edge_table = build_edge_table(wire)
    total=edge_table[1][-1]; step=total/n_points
    n_vec=App.Vector(float(chain_normal[0]),float(chain_normal[1]),float(chain_normal[2]))
    rc   =App.Vector(float(rollen_center[0]),float(rollen_center[1]),float(rollen_center[2]))
    frames=[]
    for k in range(n_points):
        pt,tan=point_on_wire(wire,(k+0.5)*step,edge_table)
        b_vec=n_vec
        h_vec=tan.cross(b_vec)
        if h_vec.Length<1e-10: h_vec=App.Vector(0,1,0).cross(b_vec)
        h_vec.normalize()
        if h_vec.dot(rc-pt)>0: h_vec=h_vec*-1.0
        frames.append((pt,tan,h_vec,b_vec))
    return frames

# ---------------------------------------------------------------------------
# Band, Rippen
# ---------------------------------------------------------------------------
def make_band_and_outer_ribs(segments, cum, total, n_outer,
                              origin, e1_t, e2_t, normal,
                              chain_width, band_height,
                              rib_h, rib_w_bot, rib_w_top,
                              rollen_center):
    """
    Band + Außenrippen als ein Solid:
    - Außenkontur: Trapez-Rippen mit verbindenden Rippenfuß-Linien
    - Innenkante: Wire-Punkte (dicht abgetastet)
    - Geschlossene Face → extrusion in normal-Richtung um chain_width
    Alles aus analytischen 2D-Punkten.
    """
    try:
        e1_fc = App.Vector(float(e1_t[0]), float(e1_t[1]), float(e1_t[2]))
        e2_fc = App.Vector(float(e2_t[0]), float(e2_t[1]), float(e2_t[2]))
        orig  = App.Vector(float(origin[0]), float(origin[1]), float(origin[2]))
        n_vec = App.Vector(float(normal[0]), float(normal[1]), float(normal[2]))
        rc    = App.Vector(float(rollen_center[0]), float(rollen_center[1]),
                           float(rollen_center[2]))

        def to3d(x, y):
            return orig + e1_fc*x + e2_fc*y

        # Außenrichtung: h = (-ty, tx) in 2D, Vorzeichen weg von Rollenschwerpunkt
        x0,y0,tx0,ty0 = point_at_dist_2d(segments, cum, total, 0.0)
        h3d = e1_fc*(-ty0) + e2_fc*(tx0)
        h_sign = -1.0 if h3d.dot(rc - to3d(x0,y0)) > 0 else 1.0

        pitch  = total / n_outer
        hw_bot = rib_w_bot / 2.0
        hw_top = rib_w_top / 2.0

        # Außenkontur: Rippenfolge p_fl, p_sl, p_sr, p_fr ohne Extraverbindungen
        # p_fr der Rippe k liegt direkt neben p_fl der Rippe k+1 → keine Querlinie
        outer_pts = []
        for k in range(n_outer):
            d_rib = (k + 0.5) * pitch
            x,y,tx,ty = point_at_dist_2d(segments, cum, total, d_rib)
            hx = -ty * h_sign; hy = tx * h_sign

            p_fl = (x - tx*hw_bot + hx*band_height,
                    y - ty*hw_bot + hy*band_height)
            p_sl = (x - tx*hw_top + hx*(band_height+rib_h),
                    y - ty*hw_top + hy*(band_height+rib_h))
            p_sr = (x + tx*hw_top + hx*(band_height+rib_h),
                    y + ty*hw_top + hy*(band_height+rib_h))
            p_fr = (x + tx*hw_bot + hx*band_height,
                    y + ty*hw_bot + hy*band_height)

            outer_pts.extend([p_fl, p_sl, p_sr, p_fr])

        # Innenkante: Wire dicht abtasten (rückwärts für geschlossenes Polygon)
        n_wire_pts = n_outer * 8
        inner_pts = []
        for k in range(n_wire_pts):
            dist = total * k / n_wire_pts
            x,y,_,_ = point_at_dist_2d(segments, cum, total, dist)
            inner_pts.append((x, y))

        # Geschlossenes Polygon: außen vorwärts + innen rückwärts
        all_pts = [to3d(x,y) for x,y in outer_pts] +                   [to3d(x,y) for x,y in reversed(inner_pts)]
        all_pts.append(all_pts[0])   # schließen

        edges = []
        for k in range(len(all_pts)-1):
            if (all_pts[k]-all_pts[k+1]).Length > 1e-6:
                edges.append(Part.makeLine(all_pts[k], all_pts[k+1]))

        face  = Part.Face(Part.Wire(edges))
        solid = face.extrude(n_vec * chain_width)
        solid.translate(n_vec * (-chain_width / 2.0))
        App.Console.PrintMessage(
            f"kette:   Band+Außenrippen OK ({n_outer} Rippen)\n")
        return solid

    except Exception as ex:
        App.Console.PrintError(f"kette: Band+Rippen-Fehler: {ex}\n")
        return None



def get_rib_frames_2d(segments, cum, total, n_ribs, origin, e1, e2,
                       chain_normal, rollen_center, offset_fraction=0.0):
    """Berechnet n_ribs gleichmäßige Frames direkt aus 2D-Segmenten."""
    n_vec=App.Vector(float(chain_normal[0]),float(chain_normal[1]),float(chain_normal[2]))
    rc   =App.Vector(float(rollen_center[0]),float(rollen_center[1]),float(rollen_center[2]))
    result=[]
    for k in range(n_ribs):
        dist=(k+offset_fraction)/n_ribs*total
        x,y,tx,ty=point_at_dist_2d(segments,cum,total,dist)
        pt =App.Vector(*unproject((x,y),origin,e1,e2))
        tan=App.Vector(*vadd(vscale(e1,tx),vscale(e2,ty))); tan.normalize()
        b_vec=n_vec
        h_vec=tan.cross(b_vec)
        if h_vec.Length<1e-10: h_vec=App.Vector(0,1,0).cross(b_vec)
        h_vec.normalize()
        if h_vec.dot(rc-pt)>0: h_vec=h_vec*-1.0
        result.append((pt,tan,h_vec,b_vec))
    return result


def make_inner_ribs(rib_frames, band_height, rib_r, rib_w, rib_offset):
    shapes=[]; hw=rib_w/2.0
    for pt,tan,h_vec,b_vec in rib_frames:
        try:
            center=pt-h_vec*rib_offset
            shapes.append(Part.makeCylinder(rib_r,rib_w,center-b_vec*hw,b_vec))
        except Exception as ex:
            App.Console.PrintWarning(f"kette: Innenrippe: {ex}\n")
    return shapes

# ---------------------------------------------------------------------------
# Kette erzeugen
# ---------------------------------------------------------------------------
def create_one_chain(doc, rollennamen, name, n_inner, color=CHAIN_COLOR):
    n_outer = 2 * n_inner
    App.Console.PrintMessage(f"kette: Erzeuge '{name}' ({rollennamen})...\n")

    # rollennamen kann (label, chain) Tupel oder einfach label sein
    rollen = []
    for entry in rollennamen:
        if isinstance(entry, tuple):
            rname, chain = entry
        else:
            rname, chain = entry, None
        # Link suchen (auch in Sub-Assemblies)
        obj = None
        for o in doc.Objects:
            if o.TypeId == "App::Link" and o.Label == rname:
                obj = o; break
        if obj is None:
            App.Console.PrintError(f"kette: Rolle nicht gefunden: {rname}\n")
            return
        data = get_lcs_data(obj, chain)
        if data is None:
            App.Console.PrintError(f"kette: LCS_track nicht gefunden: {rname}\n")
            return
        rollen.append(data)
        App.Console.PrintMessage(f"kette:   '{rname}': M={data[0]}, r={data[2]}\n")

    normal, e1, e2 = get_chain_plane(rollen)
    origin = rollen[0][0]
    rollen_center = vscale(
        tuple(sum(r[0][i] for r in rollen) for i in range(3)),
        1.0/len(rollen))

    rollen_2d = [project_to_plane(m,origin,e1,e2) for m,_,_ in rollen]
    radien    = [r for _,_,r in rollen]
    segments  = compute_segments_2d(rollen_2d, radien)
    if not segments: return

    cum, total = build_segment_table(segments)
    pitch = total / n_inner
    App.Console.PrintMessage(
        f"kette:   Länge={total:.1f}mm, {n_inner} Innenrippen, pitch={pitch:.2f}mm\n")

    wire = make_wire_3d(segments, origin, e1, e2, normal)
    if wire is None: return

    # Band + Außenrippen als ein Solid aus 2D-Profil
    band_and_outer = make_band_and_outer_ribs(
        segments, cum, total, n_outer,
        origin, e1, e2, normal,
        CHAIN_WIDTH, BAND_HEIGHT,
        OUTER_RIB_H, OUTER_RIB_W_BOT, OUTER_RIB_W_TOP,
        rollen_center)

    # Innenrippen
    inner_frames = get_rib_frames_2d(segments,cum,total,n_inner,
                                      origin,e1,e2,normal,rollen_center,0.0)
    inner = make_inner_ribs(inner_frames,BAND_HEIGHT,INNER_RIB_R,INNER_RIB_W,INNER_RIB_OFFSET)
    App.Console.PrintMessage(f"kette:   {len(inner)} Innenrippen\n")

    all_shapes = ([band_and_outer] if band_and_outer else []) + inner
    shape = Part.makeCompound(all_shapes) if all_shapes else None
    if shape is None:
        App.Console.PrintError("kette:   Keine Shapes erzeugt!\n"); return

    existing = doc.getObject(name)
    if existing:
        existing.Shape = shape
        App.Console.PrintMessage(f"kette:   '{name}' aktualisiert.\n")
    else:
        feature = doc.addObject("Part::Feature", name)
        feature.Shape = shape
        feature.ViewObject.ShapeColor   = color
        feature.ViewObject.Transparency = 0
        assembly = next((o for o in doc.Objects
                         if o.TypeId=="Assembly::AssemblyObject"), None)
        if assembly:
            try:
                grp = list(assembly.Group); grp.append(feature)
                assembly.Group = grp
            except Exception as ex:
                App.Console.PrintWarning(f"kette: Assembly-Einhängen: {ex}\n")
        App.Console.PrintMessage(f"kette:   '{name}' erzeugt.\n")

# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------
class KetteDialog(QtWidgets.QDialog):
    def __init__(self, doc, parent=None):
        super().__init__(parent or Gui.getMainWindow())
        self.doc = doc
        self.setWindowTitle("Ketten-Konfigurator")
        self.setMinimumWidth(480)
        self.ketten = []   # Liste von {'name': str, 'rollen': [str], 'n_inner': int}
        self._build_ui()
        self._refresh_available()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        # Hauptbereich: links Rollen, rechts Ketten
        main = QtWidgets.QHBoxLayout()
        layout.addLayout(main)

        # --- Linke Seite: verfügbare Rollen ---
        left = QtWidgets.QVBoxLayout()
        row_depth = QtWidgets.QHBoxLayout()
        row_depth.addWidget(QtWidgets.QLabel("Suchtiefe:"))
        self.spin_depth = QtWidgets.QSpinBox()
        self.spin_depth.setMinimum(1); self.spin_depth.setMaximum(5)
        self.spin_depth.setValue(2)
        self.spin_depth.valueChanged.connect(self._refresh_available)
        row_depth.addWidget(self.spin_depth)
        row_depth.addStretch()
        left.addLayout(row_depth)
        left.addWidget(QtWidgets.QLabel("Verfügbare Rollen (mit LCS_track):"))
        self.list_available = QtWidgets.QListWidget()
        self.list_available.setMinimumWidth(140)
        self.list_available.setMaximumWidth(200)
        self.list_available.itemDoubleClicked.connect(self._on_available_dblclick)
        self.list_available.currentItemChanged.connect(self._on_available_hover)
        left.addWidget(self.list_available)
        main.addLayout(left)

        # --- Mitte: Buttons ---
        mid = QtWidgets.QVBoxLayout()
        mid.addStretch()
        btn_add_role = QtWidgets.QPushButton("→ Hinzufügen")
        btn_add_role.clicked.connect(self._add_role)
        btn_rem_role = QtWidgets.QPushButton("← Entfernen")
        btn_rem_role.clicked.connect(self._remove_role)
        btn_up = QtWidgets.QPushButton("↑")
        btn_dn = QtWidgets.QPushButton("↓")
        btn_up.clicked.connect(self._move_up)
        btn_dn.clicked.connect(self._move_down)
        for b in [btn_add_role, btn_rem_role, btn_up, btn_dn]:
            mid.addWidget(b)
        mid.addStretch()
        main.addLayout(mid)

        # --- Rechte Seite: Ketten ---
        right = QtWidgets.QVBoxLayout()
        right.addWidget(QtWidgets.QLabel("Ketten-Konfiguration:"))

        # Ketten-Auswahl (Tab-Widget)
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.currentChanged.connect(lambda _: self._update_chain_selection())
        right.addWidget(self.tabs)

        # Neue Kette / Kette entfernen
        btn_row = QtWidgets.QHBoxLayout()
        btn_new = QtWidgets.QPushButton("+ Neue Kette")
        btn_new.clicked.connect(self._new_chain)
        btn_del = QtWidgets.QPushButton("− Kette entfernen")
        btn_del.clicked.connect(self._del_chain)
        btn_row.addWidget(btn_new)
        btn_row.addWidget(btn_del)
        right.addLayout(btn_row)
        main.addLayout(right)

        # --- Buttons Erzeugen/Schließen ---
        btn_row = QtWidgets.QHBoxLayout()
        btn_create = QtWidgets.QPushButton("Ketten erzeugen")
        btn_create.setDefault(True)
        btn_create.clicked.connect(self._on_create)
        btn_close = QtWidgets.QPushButton("Schließen")
        btn_close.clicked.connect(self._on_close)
        btn_row.addStretch()
        btn_row.addWidget(btn_create)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

        # Erste Kette anlegen
        self._new_chain()

    def _refresh_available(self):
        self.list_available.clear()
        depth = self.spin_depth.value()
        links = find_lcs_track_links(self.doc, max_depth=depth)
        for label, obj, chain in links:
            item = QtWidgets.QListWidgetItem(label)
            item.setData(QtCore.Qt.UserRole, obj)
            item.setData(QtCore.Qt.UserRole + 1, chain)
            self.list_available.addItem(item)

    def _on_available_dblclick(self, item):
        """Doppelklick links: Rolle zur aktuellen Kette hinzufügen."""
        self._add_role()

    def _on_available_hover(self, current, previous):
        """Selektion links: Objekt(e) in der Kette blau markieren."""
        if current is None: return
        chain = current.data(QtCore.Qt.UserRole + 1)
        obj   = current.data(QtCore.Qt.UserRole)
        Gui.Selection.clearSelection()
        if chain:
            for link in chain:
                try:
                    Gui.Selection.addSelection(self.doc.Name, link.Name)
                except Exception:
                    pass
        elif obj:
            try:
                Gui.Selection.addSelection(self.doc.Name, obj.Name)
            except Exception:
                pass

    def _update_chain_selection(self):
        """Alle Rollen der aktuellen Kette hellblau markieren (select)."""
        Gui.Selection.clearSelection()
        tab = self._current_tab_widget()
        if tab is None: return
        link_index = {o.Label: o for o in self.doc.Objects
                      if o.TypeId == "App::Link"}
        for i in range(tab.list_rollen.count()):
            label = tab.list_rollen.item(i).text()
            obj   = link_index.get(label)
            if obj:
                try:
                    Gui.Selection.addSelection(self.doc.Name, obj.Name)
                except Exception:
                    pass

    def _current_tab_widget(self):
        idx = self.tabs.currentIndex()
        if idx < 0: return None
        return self.tabs.widget(idx)

    def _new_chain(self):
        n = self.tabs.count() + 1
        name = f"Kette_{n}"
        tab = ChainTab(name, self.doc)
        self.tabs.addTab(tab, name)
        self.tabs.setCurrentWidget(tab)

    def _del_chain(self):
        idx = self.tabs.currentIndex()
        if idx >= 0:
            self.tabs.removeTab(idx)

    def _add_role(self):
        tab = self._current_tab_widget()
        if tab is None: return
        item = self.list_available.currentItem()
        if item is None: return
        label = item.text()
        obj   = item.data(QtCore.Qt.UserRole)
        chain = item.data(QtCore.Qt.UserRole + 1)
        tab.add_role(label, obj, chain)
        row = self.list_available.row(item)
        self.list_available.takeItem(row)
        self._update_chain_selection()

    def _remove_role(self):
        tab = self._current_tab_widget()
        if tab is None: return
        row = tab.list_rollen.currentRow()
        if row < 0: return
        item  = tab.list_rollen.item(row)
        label = item.text()
        obj   = item.data(QtCore.Qt.UserRole)
        chain = item.data(QtCore.Qt.UserRole + 1)
        tab.list_rollen.takeItem(row)
        tab._update_length()
        link_index = {o.Label: o for o in self.doc.Objects if o.TypeId=="App::Link"}
        tab.restore_role_to_available(label, self.list_available,
                                       link_index, obj, chain)
        self._update_chain_selection()

    def _move_up(self):
        tab = self._current_tab_widget()
        if tab: tab.move_role(-1)

    def _move_down(self):
        tab = self._current_tab_widget()
        if tab: tab.move_role(+1)

    def _cleanup_all_previews(self):
        for i in range(self.tabs.count()):
            self.tabs.widget(i).cleanup_preview()

    def _on_create(self):
        ketten = self.get_ketten()
        if not ketten:
            QtWidgets.QMessageBox.warning(self, "Ketten erzeugen",
                "Keine gültige Kette konfiguriert\n(mind. 2 Rollen pro Kette).")
            return
        self._cleanup_all_previews()
        for spec in ketten:
            create_one_chain(self.doc, spec['rollen'], spec['name'], spec['n_inner'])
        self.doc.recompute()
        Gui.updateGui()
        App.Console.PrintMessage("kette: Fertig.\n")

    def _on_close(self):
        self._cleanup_all_previews()
        self.close()

    def closeEvent(self, event):
        self._cleanup_all_previews()
        event.accept()

    def get_ketten(self):
        result = []
        for i in range(self.tabs.count()):
            tab = self.tabs.widget(i)
            cfg = tab.get_config()
            if cfg and len(cfg['rollen']) >= 2:
                result.append(cfg)
        return result


class ChainTab(QtWidgets.QWidget):
    def __init__(self, name, doc, parent=None):
        super().__init__(parent)
        self.doc  = doc
        self._layout = QtWidgets.QVBoxLayout(self)

        # Name
        row1 = QtWidgets.QHBoxLayout()
        row1.addWidget(QtWidgets.QLabel("Name:"))
        self.edit_name = QtWidgets.QLineEdit(name)
        row1.addWidget(self.edit_name)
        self._layout.addLayout(row1)

        # Typ (n_inner)
        row2 = QtWidgets.QHBoxLayout()
        row2.addWidget(QtWidgets.QLabel("Typ:"))
        self.combo_type = QtWidgets.QComboBox()
        for ct in CHAIN_TYPES:
            self.combo_type.addItem(ct["label"], ct["n_inner"])
        self.combo_type.currentIndexChanged.connect(self._update_length)
        row2.addWidget(self.combo_type)
        self._layout.addLayout(row2)

        # Rollenliste
        self._layout.addWidget(QtWidgets.QLabel("Rollen (in Reihenfolge):"))
        self.list_rollen = QtWidgets.QListWidget()
        self.list_rollen.setMinimumWidth(140)
        self.list_rollen.setMaximumWidth(200)
        self.list_rollen.currentItemChanged.connect(self._update_length)
        self.list_rollen.currentItemChanged.connect(self._on_rollen_hover)
        self.list_rollen.itemDoubleClicked.connect(self._on_rollen_dblclick)
        self._layout.addWidget(self.list_rollen)

        # Längenanzeige + Vorschau-Button
        row_len = QtWidgets.QHBoxLayout()
        self.lbl_length = QtWidgets.QLabel("Länge: –")
        self.lbl_length.setTextFormat(QtCore.Qt.RichText)
        row_len.addWidget(self.lbl_length)
        btn_preview = QtWidgets.QPushButton("Wire-Vorschau")
        btn_preview.clicked.connect(self._show_preview)
        row_len.addWidget(btn_preview)
        self._layout.addLayout(row_len)
        self._preview_name = None  # Name des Vorschau-Features

    def add_role(self, label, obj=None, chain=None):
        item = QtWidgets.QListWidgetItem(label)
        item.setData(QtCore.Qt.UserRole,     obj)
        item.setData(QtCore.Qt.UserRole + 1, chain)
        self.list_rollen.addItem(item)
        self._update_length()

    def remove_role_from_available(self, label, available_list):
        """Entfernt Rolle aus der verfügbaren Liste."""
        for i in range(available_list.count()):
            if available_list.item(i).text() == label:
                available_list.takeItem(i)
                return

    def restore_role_to_available(self, label, available_list, link_index,
                                    obj=None, chain=None):
        """Fügt Rolle wieder zur verfügbaren Liste hinzu."""
        for i in range(available_list.count()):
            if available_list.item(i).text() == label:
                return
        item = QtWidgets.QListWidgetItem(label)
        if obj is None: obj = link_index.get(label)
        item.setData(QtCore.Qt.UserRole,     obj)
        item.setData(QtCore.Qt.UserRole + 1, chain)
        available_list.addItem(item)

    def _on_rollen_dblclick(self, item):
        """Doppelklick rechts: Rolle entfernen und zurück zur linken Liste."""
        row = self.list_rollen.row(item)
        if row < 0: return
        label = item.text()
        obj   = item.data(QtCore.Qt.UserRole)
        chain = item.data(QtCore.Qt.UserRole + 1)
        self.list_rollen.takeItem(row)
        self._update_length()
        dlg = self._find_dialog()
        if dlg:
            link_index = {o.Label: o for o in self.doc.Objects if o.TypeId=="App::Link"}
            self.restore_role_to_available(label, dlg.list_available,
                                            link_index, obj, chain)
            dlg._update_chain_selection()

    def _find_dialog(self):
        """Findet den übergeordneten KetteDialog."""
        p = self.parent()
        while p:
            if isinstance(p, KetteDialog):
                return p
            p = p.parent() if hasattr(p, 'parent') else None
        return None

    def _on_rollen_hover(self, current, previous):
        """Selektion rechts: Objekt grün hervorheben (preselect)."""
        if current is None: return
        label = current.text()
        for obj in self.doc.Objects:
            if obj.TypeId == "App::Link" and obj.Label == label:
                try:
                    Gui.Selection.setPreselection(self.doc.Name, obj.Name, '')
                except Exception:
                    pass
                break

    def remove_selected_role(self):
        row = self.list_rollen.currentRow()
        if row >= 0:
            self.list_rollen.takeItem(row)
            self._update_length()

    def move_role(self, direction):
        row = self.list_rollen.currentRow()
        new_row = row + direction
        if 0 <= new_row < self.list_rollen.count():
            item = self.list_rollen.takeItem(row)
            self.list_rollen.insertItem(new_row, item)
            self.list_rollen.setCurrentRow(new_row)
            self._update_length()

    def _update_length(self):
        rollen = [self.list_rollen.item(i).text()
                  for i in range(self.list_rollen.count())]
        if len(rollen) < 2:
            self.lbl_length.setText("Länge: (mind. 2 Rollen nötig)")
            return
        length = compute_wire_length(rollen, self.doc)
        if length is None:
            self.lbl_length.setText("Länge: –")
        else:
            n = self.combo_type.currentData()
            # Nominallänge: n=36 → 300mm, n=60 → 500mm (ca. 8.33mm pitch)
            nominal = n * 8.333
            pct = length / nominal * 100.0
            diff = pct - 100.0
            sign = "+" if diff >= 0 else ""
            color = "green" if abs(diff) < 2 else "orange" if abs(diff) < 5 else "red"
            self.lbl_length.setText(
                f"Länge: {length:.1f} mm  "
                f"(<span style='color:{color}'>{sign}{diff:.1f}% von {nominal:.0f} mm</span>)"
            )
            self.lbl_length.setTextFormat(QtCore.Qt.RichText)

    def _show_preview(self):
        """Zeigt den Wire als temporäres Feature in der 3D-Ansicht."""
        rollen = [self.list_rollen.item(i).text()
                  for i in range(self.list_rollen.count())]
        if len(rollen) < 2:
            return
        doc = self.doc
        link_index = {obj.Label: obj for obj in doc.Objects
                      if obj.TypeId == "App::Link"}
        lcs_rollen = []
        for name in rollen:
            data = get_lcs_data(link_index.get(name))
            if data is None: return
            lcs_rollen.append(data)

        normal, e1, e2 = get_chain_plane(lcs_rollen)
        origin    = lcs_rollen[0][0]
        rollen_2d = [project_to_plane(m,origin,e1,e2) for m,_,_ in lcs_rollen]
        radien    = [r for _,_,r in lcs_rollen]
        segments  = compute_segments_2d(rollen_2d, radien)
        if not segments: return
        wire = make_wire_3d(segments, origin, e1, e2, normal)
        if wire is None: return

        # Altes Vorschau-Feature entfernen
        preview_name = f"_Vorschau_{self.edit_name.text().strip() or 'Kette'}"
        old = doc.getObject(preview_name)
        if old: doc.removeObject(preview_name)

        feat = doc.addObject("Part::Feature", preview_name)
        feat.Shape = wire
        feat.ViewObject.LineColor  = (1.0, 0.5, 0.0)
        feat.ViewObject.LineWidth  = 3.0
        feat.ViewObject.PointSize  = 1.0
        self._preview_name = preview_name
        doc.recompute()
        Gui.updateGui()

    def cleanup_preview(self):
        """Entfernt Vorschau-Feature."""
        if self._preview_name:
            old = self.doc.getObject(self._preview_name)
            if old:
                self.doc.removeObject(self._preview_name)
                self.doc.recompute()
            self._preview_name = None

    def get_config(self):
        items  = [self.list_rollen.item(i)
                  for i in range(self.list_rollen.count())]
        if len(items) < 2: return None
        # rollen: Liste von (label, chain) Tupeln
        rollen = [(item.text(), item.data(QtCore.Qt.UserRole + 1))
                  for item in items]
        return {
            'name':    self.edit_name.text().strip() or "Kette",
            'rollen':  rollen,
            'n_inner': self.combo_type.currentData(),
        }


# ---------------------------------------------------------------------------
# Hauptfunktion
# ---------------------------------------------------------------------------
# Globale Referenz damit der Dialog nicht garbage-collected wird
_kette_dialog = None

def create_chain(doc=None):
    global _kette_dialog
    if doc is None: doc = App.ActiveDocument
    if doc is None:
        App.Console.PrintError("kette: Kein aktives Dokument.\n"); return

    # Bestehenden Dialog in den Vordergrund bringen
    if _kette_dialog is not None and _kette_dialog.isVisible():
        _kette_dialog.raise_()
        _kette_dialog.activateWindow()
        return

    dlg = KetteDialog(doc)
    _kette_dialog = dlg
    dlg.show()   # nicht-modal: 3D-Ansicht bleibt bedienbar


if __name__ == "__main__":
    create_chain()
