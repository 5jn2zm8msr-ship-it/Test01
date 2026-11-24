# SPDX-License-Identifier: GPL-3.0-or-later
"""
Parametrische Felge per Geometry Nodes (Blender 5.x): sauberes Quad-Mesh, nicht-destruktiv.

Aufbau: Felgenbett (Profil um die Achse), Außenring, Nabe, EINE Musterspeiche (Gitter, Breite/Biegung/Tiefe aus Kurven),
per Rotations-Instanzierung auf die Speichenzahl vervielfältigt, Nabe mit Radschrauben ODER Zentralverschluss.
Koordinaten wie das KI-Mesh: Radachse = Z, Vorderseite (Felgenhorn) bei z = 0 nach +Z, Bett nach -Z.
Die Tiefe der Speichen kommt aus der Float-Curve „Schnitt“ (x = Radius Nabe -> Horn, y = Tiefe); der Startpunkt der Kurve
bestimmt, wie tief Nabe/Schrauben/Zentralverschluss sitzen. Der Slider „Konkavität“ multipliziert die Kurve.
"""
import math

import bpy

GROUP_NAME = "Rim Generator | Parametrische Felge"
CURVE_SECTION, CURVE_EDGE_L, CURVE_EDGE_R, CURVE_SEAM = "Schnitt", "Speichenkante links", "Speichenkante rechts", "Nahtverlauf"
CURVE_WIDTH = CURVE_EDGE_L          # (Kennung des Muster-Baums)

# (Name, Typ, Standard, min, max, Beschreibung)
# Musterspeiche („Pizzastück“: Nabenkeil + Speiche + Ringkeil aus einem Gitter), eigene Node-Group am Muster-Objekt
SLICE_INPUTS = [
    ("Speichen", "INT", 5, 3, 24, "Anzahl der Speichen (Winkel des Pizzastücks = 360°/Speichen)"),
    ("Referenz-Durchmesser (Zoll)", "FLOAT", 20.0, 12.0, 26.0, "Größe, für die das Muster gebaut ist (die Felge skaliert es auf ihren Durchmesser)"),
    ("Referenz-Wandstärke (mm)", "FLOAT", 5.0, 2.0, 10.0, ""),
    ("Nabenradius (mm)", "FLOAT", 85.0, 40.0, 130.0, "Radius der flachen Nabenanlage (Dicke geht hier in die Speichendicke über)"),
    ("Wölbung (mm)", "FLOAT", 4.0, 0.0, 15.0, "Speichenrücken (Querschnitt gewölbt, wie im KI-Mesh)"),
    ("Nabenbund Höhe (mm)", "FLOAT", 6.0, 0.0, 40.0, "Erhabener Bund um die Nabe"),
    ("Nabenbund Radius (mm)", "FLOAT", 75.0, 20.0, 200.0, ""),
    ("Dicke Nabe (mm)", "FLOAT", 24.0, 10.0, 50.0, ""),
    ("Dicke Speiche (mm)", "FLOAT", 14.0, 6.0, 40.0, ""),
    ("Diamond-Cut Rand (%)", "FLOAT", 18.0, 0.0, 60.0, "Streifen am Speichenrand, der in der Grundfarbe bleibt (Rahmen um die polierte Fläche)"),
]
# Felge: Bett, Instanzierung des Musters, Nabe, Schnittkurve, Materialien
INPUTS = [
    ("Durchmesser (Zoll)", "FLOAT", 20.0, 12.0, 26.0, "Felgendurchmesser in Zoll"),
    ("Breite J (Zoll)", "FLOAT", 9.0, 5.0, 14.0, "Maulweite in Zoll"),
    ("Speichen", "INT", 5, 3, 24, "Anzahl der Instanzen (muss zum Muster passen)"),
    ("Drehung (Grad)", "FLOAT", 0.0, -180.0, 180.0, "Dreht das Speichenmuster um die Achse"),
    ("Schüsseltiefe (mm)", "FLOAT", 60.0, -80.0, 160.0, "Tiefe der Nabe bei Kurvenwert 1 (+ = konkav)"),
    ("Konkavität", "FLOAT", 1.0, 0.0, 2.5, "Globaler Multiplikator auf die Schnittkurve"),
    ("Front-Einzug (mm)", "FLOAT", 12.0, 0.0, 40.0, "Abstand der Speichen-Außenkante hinter dem Horn"),
    ("Zentralverschluss", "BOOL", False, 0, 1, "Aus = Radschrauben, an = Zentralverschluss"),
    ("Radschrauben", "INT", 5, 3, 8, ""),
    ("Lochkreis (mm)", "FLOAT", 112.0, 90.0, 140.0, ""),
    ("Flansch (mm)", "FLOAT", 17.0, 8.0, 30.0, "Höhe des Felgenhorns"),
    ("Wandstärke (mm)", "FLOAT", 5.0, 2.0, 10.0, ""),
    ("Tiefbett (mm)", "FLOAT", 22.0, 8.0, 40.0, ""),
    ("Auflösung", "INT", 96, 24, 256, "Segmente um die Achse (Bett)"),
    ("Diamond Cut", "BOOL", True, 0, 1, "Speichen-Frontflächen als eigenes Material (glanzgedreht); aus = alles in der Grundfarbe"),
    ("Referenz-Durchmesser (Zoll)", "FLOAT", 20.0, 12.0, 26.0, "Größe des Musters (nicht ändern)"),
    ("Referenz-Wandstärke (mm)", "FLOAT", 5.0, 2.0, 10.0, "Wandstärke des Musters (nicht ändern)"),
]
SLICE_ONLY = [n for n, *_ in SLICE_INPUTS if n not in ("Speichen", "Referenz-Durchmesser (Zoll)", "Referenz-Wandstärke (mm)")]
ROLE_TEMPLATE = "template"
MATERIAL_FRONT, MATERIAL_BODY = "Felge Front", "Felge Körper"
PARTS = {}          # Zwischenergebnisse (nur für Tests)
FRONT_COLOR_NODE, BODY_COLOR_NODE = "Farbe Front", "Farbe Grund"


class Ref:
    """Ausgang eines Knotens mit Rechenoperatoren (baut Math-Knoten)."""
    __slots__ = ("b", "s")

    def __init__(self, b, s):
        self.b, self.s = b, s

    def __add__(self, o): return self.b.math("ADD", self, o)
    def __radd__(self, o): return self.b.math("ADD", o, self)
    def __sub__(self, o): return self.b.math("SUBTRACT", self, o)
    def __rsub__(self, o): return self.b.math("SUBTRACT", o, self)
    def __mul__(self, o): return self.b.math("MULTIPLY", self, o)
    def __rmul__(self, o): return self.b.math("MULTIPLY", o, self)
    def __truediv__(self, o): return self.b.math("DIVIDE", self, o)
    def __rtruediv__(self, o): return self.b.math("DIVIDE", o, self)
    def __neg__(self): return self.b.math("MULTIPLY", self, -1.0)


_PY = {"ADD": lambda a, b: a + b, "SUBTRACT": lambda a, b: a - b, "MULTIPLY": lambda a, b: a * b,
       "DIVIDE": lambda a, b: a / b if b else 0.0, "MINIMUM": min, "MAXIMUM": max,
       "SINE": lambda a, b: math.sin(a), "COSINE": lambda a, b: math.cos(a), "SQRT": lambda a, b: math.sqrt(max(a, 0.0)),
       "POWER": lambda a, b: a ** b, "ABSOLUTE": lambda a, b: abs(a)}


class Builder:
    def __init__(self, ng):
        self.ng = ng
        self.gi = ng.nodes.new("NodeGroupInput")
        self.gi.location = (-1400, 0)
        self._x, self._y = -1200, 400

    def node(self, idname, **props):
        n = self.ng.nodes.new(idname)
        for k, v in props.items():
            setattr(n, k, v)
        n.location = (self._x, self._y)
        self._y -= 90
        if self._y < -1400:
            self._y, self._x = 400, self._x + 260
        return n

    # ---- Skalare
    def inp(self, name):
        return Ref(self, self.gi.outputs[name])

    def _feed(self, node, idx, v):
        if isinstance(v, Ref):
            self.ng.links.new(v.s, node.inputs[idx])
        else:
            node.inputs[idx].default_value = float(v)

    def math(self, op, a, b=0.0):
        if not isinstance(a, Ref) and not isinstance(b, Ref):
            return _PY[op](float(a), float(b))
        n = self.node("ShaderNodeMath", operation=op)
        self._feed(n, 0, a)
        self._feed(n, 1, b)
        return Ref(self, n.outputs[0])

    def minimum(self, a, b): return self.math("MINIMUM", a, b)
    def maximum(self, a, b): return self.math("MAXIMUM", a, b)
    def clamp01(self, a): return self.minimum(self.maximum(a, 0.0), 1.0)
    def sin(self, a): return self.math("SINE", a)
    def cos(self, a): return self.math("COSINE", a)
    def sqrt(self, a): return self.math("SQRT", a)
    def absolute(self, a): return self.math("ABSOLUTE", a)
    def power(self, a, e): return self.math("POWER", a, e)

    def curve(self, name, x, pts, ymin=0.0, ymax=1.0):
        """Float Curve mit Standardpunkten pts [(x, y), ...]; x = Ref."""
        n = self.node("ShaderNodeFloatCurve")
        n.name = n.label = name
        self._feed(n, 1, x)
        m = n.mapping
        m.use_clip = True
        m.clip_min_x, m.clip_max_x, m.clip_min_y, m.clip_max_y = 0.0, 1.0, ymin, ymax
        set_curve_points(m, pts)
        return Ref(self, n.outputs[0])

    # ---- Vektoren
    def comb(self, x, y, z):
        n = self.node("ShaderNodeCombineXYZ")
        for i, v in enumerate((x, y, z)):
            self._feed(n, i, v)
        return n.outputs[0]

    def sep(self, vec):
        n = self.node("ShaderNodeSeparateXYZ")
        self.ng.links.new(vec, n.inputs[0])
        return Ref(self, n.outputs[0]), Ref(self, n.outputs[1]), Ref(self, n.outputs[2])

    def position(self):
        return self.node("GeometryNodeInputPosition").outputs[0]

    def index(self):
        return Ref(self, self.node("GeometryNodeInputIndex").outputs[0])

    # ---- Geometrie
    def join(self, geos):
        n = self.node("GeometryNodeJoinGeometry")
        for g in geos:
            self.ng.links.new(g, n.inputs[0])
        return n.outputs[0]

    def revolve(self, pts, closed=True, sections=None, flip=False):
        """Profil (r, z) in Metern (Zahlen oder Ref) um die Z-Achse drehen. Gibt Geometrie (Quads) zurück."""
        segs = []
        count = len(pts) if closed else len(pts) - 1
        for k in range(count):
            a, b = pts[k], pts[(k + 1) % len(pts)]
            ln = self.node("GeometryNodeCurvePrimitiveLine")
            self.ng.links.new(self.comb(a[0] - 1.0, -a[1], 0.0), ln.inputs["Start"])
            self.ng.links.new(self.comb(b[0] - 1.0, -b[1], 0.0), ln.inputs["End"])
            segs.append(ln.outputs["Curve"])
        prof = self.join(segs)
        circ = self.node("GeometryNodeCurvePrimitiveCircle")
        circ.inputs["Radius"].default_value = 1.0
        if sections is not None:
            self.ng.links.new(sections.s, circ.inputs["Resolution"])
        c2m = self.node("GeometryNodeCurveToMesh")
        self.ng.links.new(circ.outputs["Curve"], c2m.inputs["Curve"])
        self.ng.links.new(prof, c2m.inputs["Profile Curve"])
        mg = self.node("GeometryNodeMergeByDistance")
        mg.inputs["Distance"].default_value = 0.00005
        self.ng.links.new(c2m.outputs["Mesh"], mg.inputs["Geometry"])
        out = mg.outputs[0]
        if flip:
            fl = self.node("GeometryNodeFlipFaces")
            self.ng.links.new(out, fl.inputs["Mesh"])
            out = fl.outputs[0]
        return out


def set_curve_points(m, pts):
    cur = m.curves[0]
    while len(cur.points) > 2:
        cur.points.remove(cur.points[-1])
    cur.points[0].location = pts[0]
    cur.points[1].location = pts[-1]
    for x, y in pts[1:-1]:
        cur.points.new(x, y)
    for p in cur.points:
        p.handle_type = "AUTO"
    m.update()


def default_section_points(hub_x=0.34, q=2.0):
    """Exakte Standardschnitt-Kurve (wie core.default_depth): flach bis zur Nabe, dann 1 - u^q."""
    xs = [0.0, hub_x] + [hub_x + u * (1.0 - hub_x) for u in (0.25, 0.5, 0.75)] + [1.0]
    return [(x, 1.0 - min(max((x - hub_x) / (1.0 - hub_x), 0.0), 1.0) ** q) for x in xs]


def _color_node(nt, name, color, loc):
    n = nt.nodes.get(name) or nt.nodes.new("ShaderNodeRGB")
    n.name = n.label = name
    n.outputs[0].default_value = color
    n.location = loc
    return n


def _front_material(name, color=(0.80, 0.81, 0.83, 1.0)):
    """Glanzgedrehtes Aluminium: hell, stark reflektierend, feine Drehriefen (Ringe um die Achse), anisotrope Reflexion."""
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (700, 0)
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    b.location = (400, 0)
    nt.links.new(b.outputs["BSDF"], out.inputs["Surface"])
    col = _color_node(nt, FRONT_COLOR_NODE, color, (-300, 300))
    nt.links.new(col.outputs[0], b.inputs["Base Color"])
    b.inputs["Metallic"].default_value = 1.0
    b.inputs["Roughness"].default_value = 0.16
    for nm in ("Anisotropic",):
        if nm in b.inputs:
            b.inputs[nm].default_value = 0.8
    tg = nt.nodes.new("ShaderNodeTangent")
    tg.direction_type, tg.axis = "RADIAL", "Z"
    tg.location = (100, -300)
    if "Tangent" in b.inputs:
        nt.links.new(tg.outputs["Tangent"], b.inputs["Tangent"])
    tc = nt.nodes.new("ShaderNodeTexCoord")
    tc.location = (-900, -300)
    wv = nt.nodes.new("ShaderNodeTexWave")
    wv.wave_type, wv.bands_direction, wv.rings_direction = "RINGS", "Z", "Z"
    wv.wave_profile = "SAW"
    wv.inputs["Scale"].default_value = 1100.0
    wv.inputs["Distortion"].default_value = 1.2
    wv.inputs["Detail"].default_value = 2.0
    wv.inputs["Detail Scale"].default_value = 2.5
    wv.location = (-650, -300)
    nt.links.new(tc.outputs["Object"], wv.inputs["Vector"])
    bp = nt.nodes.new("ShaderNodeBump")
    bp.inputs["Strength"].default_value = 0.08
    bp.inputs["Distance"].default_value = 0.0004
    bp.location = (100, -500)
    nt.links.new(wv.outputs["Fac"], bp.inputs["Height"])
    nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["To Min"].default_value, mr.inputs["To Max"].default_value = 0.12, 0.26
    mr.location = (-300, -150)
    nt.links.new(wv.outputs["Fac"], mr.inputs["Value"])
    nt.links.new(mr.outputs["Result"], b.inputs["Roughness"])
    m.diffuse_color = color
    return m


def _body_material(name, color=(0.012, 0.012, 0.014, 1.0)):
    """Grundfarbe: frei wählbar (Standard Schwarz glänzend), Klarlack."""
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (500, 0)
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    b.location = (200, 0)
    nt.links.new(b.outputs["BSDF"], out.inputs["Surface"])
    col = _color_node(nt, BODY_COLOR_NODE, color, (-200, 200))
    nt.links.new(col.outputs[0], b.inputs["Base Color"])
    b.inputs["Metallic"].default_value = 0.35
    b.inputs["Roughness"].default_value = 0.22
    for nm in ("Coat Weight", "Clearcoat"):
        if nm in b.inputs:
            b.inputs[nm].default_value = 0.8
            break
    m.diffuse_color = color
    return m


def _materials(suffix=""):
    return (_front_material(MATERIAL_FRONT + suffix), _body_material(MATERIAL_BODY + suffix))


def _new_group(name, inputs):
    ng = bpy.data.node_groups.new(name, "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    for nm, typ, dv, lo, hi, desc in inputs:
        sock_t = {"FLOAT": "NodeSocketFloat", "INT": "NodeSocketInt", "BOOL": "NodeSocketBool"}[typ]
        sk = ng.interface.new_socket(nm, in_out="INPUT", socket_type=sock_t)
        sk.default_value = dv
        if typ != "BOOL":
            sk.min_value, sk.max_value = lo, hi
        sk.description = desc
    return ng


def default_edges_for(n, hub=0.085, ring=0.012, width=0.062, r_face=0.250):
    """Standard-Kanten (rho, f) für ein neues Muster."""
    from . import paramdetect
    return paramdetect.default_edges(n, r_face, hub, ring, width)


def build_slice_group(name):
    """
    Musterspeiche als „Pizzastück“: EIN Gitter (Zeilen = Radius, Spalten = quer) deckt Nabenkeil, Speiche und Ringkeil ab.
    In Nabe und Ring ist die Spaltenbreite der volle Keilwinkel (±180°/N), im Speichenbereich wird sie auf die Speichenbreite
    verengt – dazwischen entsteht ein rundes Fenster. An den Nähten (±180°/N) passen die Nachbarn Punkt für Punkt, nach dem
    Instanzieren werden sie verschweißt: eine durchgehende Fläche ohne Überschneidungen.
    """
    ng = _new_group(name, SLICE_INPUTS)
    B = Builder(ng)
    I = B.inp
    mm = 0.001
    N = I("Speichen")
    half = math.pi / N
    r_face = I("Referenz-Durchmesser (Zoll)") * (0.0254 / 2.0) - I("Referenz-Wandstärke (mm)") * mm + 0.001
    r_hub = I("Nabenradius (mm)") * mm
    t_spoke, t_hub = I("Dicke Speiche (mm)") * mm, I("Dicke Nabe (mm)") * mm
    r_a = 0.012

    grid = B.node("GeometryNodeMeshGrid")
    grid.inputs["Size X"].default_value = grid.inputs["Size Y"].default_value = 1.0
    grid.inputs["Vertices X"].default_value, grid.inputs["Vertices Y"].default_value = 128, 11
    px, py, _pz = B.sep(B.position())
    rho, u = px + 0.5, py * 2.0
    r = r_a + (r_face - r_a) * rho
    # Planform: linke/rechte Speichenkante als Anteil der Keilbreite über dem Radius (aus der Maske abgeleitet, Float-Curves);
    # 0..1 = ganze Breite (Nabe/Ring), dazwischen die Speiche – die Fensterform ergibt sich aus den Kurven
    d_l, d_r = default_edges_for(5)
    fL = B.curve(CURVE_EDGE_L, rho, d_l)
    fR = B.curve(CURVE_EDGE_R, rho, d_r)
    # Nähte exakt auf ±180°/N einrasten; berührt nur EINE Seite die Naht, wird sie knapp zurückgenommen (sonst bliebe die Naht offen)
    tL = B.math("LESS_THAN", fL, 0.004)
    tR = B.math("GREATER_THAN", fR, 0.996)
    fL = (1.0 - tL) * fL + tL * (1.0 - tR) * 0.008
    fR = (1.0 - tR) * fR + tR * tL + tR * (1.0 - tL) * 0.992
    cf = B.curve(CURVE_SEAM, rho, [(0.0, 0.5), (1.0, 0.5)])           # Nahtverlauf (läuft durch die Fenster)
    ang = (cf - 0.5) * (2.0 * half) + half * (2.0 * fL - 1.0 + (fR - fL) * (u + 1.0))
    w = fR - fL
    b = B.clamp01((1.0 - w) * 6.0)                       # 1 = Speichenbereich, 0 = Nabe/Ring
    ridge = 1.0 - B.power(B.absolute(u), 2.2)            # Rücken wie im KI-Mesh (1 - (1-t)^2.2)
    bx = B.clamp01((I("Nabenbund Radius (mm)") * mm - r) / 0.015)
    boss = I("Nabenbund Höhe (mm)") * mm * bx * bx * (3.0 - 2.0 * bx)
    z_top = I("Wölbung (mm)") * mm * b * ridge + boss
    flag = (B.math("LESS_THAN", u, -0.999) * B.math("LESS_THAN", fL, 0.001)
            + B.math("GREATER_THAN", u, 0.999) * B.math("GREATER_THAN", fR, 0.999))       # Punkte auf der Naht
    st = B.node("GeometryNodeStoreNamedAttribute", data_type="FLOAT", domain="POINT")
    B.ng.links.new(grid.outputs["Mesh"], st.inputs["Geometry"])
    st.inputs["Name"].default_value = "naht"
    B.ng.links.new(flag.s, st.inputs["Value"])
    zone = b * B.math("LESS_THAN", B.absolute(u), 1.0 - I("Diamond-Cut Rand (%)") * 0.01)      # polierte Speichenfläche (ohne Rahmen)
    st2 = B.node("GeometryNodeStoreNamedAttribute", data_type="FLOAT", domain="POINT")
    B.ng.links.new(st.outputs[0], st2.inputs["Geometry"])
    st2.inputs["Name"].default_value = "zone"
    B.ng.links.new(zone.s, st2.inputs["Value"])
    sp = B.node("GeometryNodeSetPosition")
    B.ng.links.new(st2.outputs[0], sp.inputs["Geometry"])
    B.ng.links.new(B.comb(r * B.cos(ang), r * B.sin(ang), z_top), sp.inputs["Position"])
    # Solid: Region-Extrusion nach unten, Unterseite umdrehen, Oberseite dazu, Nähte verschweißen
    ex = B.node("GeometryNodeExtrudeMesh")
    B.ng.links.new(sp.outputs[0], ex.inputs["Mesh"])
    ex.inputs["Offset Scale"].default_value = -0.001
    ex.inputs["Individual"].default_value = False
    sp2 = B.node("GeometryNodeSetPosition")
    B.ng.links.new(ex.outputs["Mesh"], sp2.inputs["Geometry"])
    B.ng.links.new(ex.outputs["Top"], sp2.inputs["Selection"])
    qx, qy, _qz = B.sep(B.position())
    s_of = B.clamp01((r_face - B.sqrt(qx * qx + qy * qy)) / (r_face - r_hub))
    thick = t_spoke + (t_hub - t_spoke) * s_of
    B.ng.links.new(B.comb(0.0, 0.0, -(thick - 0.001)), sp2.inputs["Offset"])
    # Seitenwände auf den Nähten entfallen (dort schließt der Nachbar die Fläche): Wand, deren Punkte alle auf der Naht liegen
    na = B.node("GeometryNodeInputNamedAttribute", data_type="FLOAT")
    na.inputs["Name"].default_value = "naht"
    seam = B.node("FunctionNodeCompare", data_type="FLOAT", operation="GREATER_THAN")
    B.ng.links.new(na.outputs["Attribute"], seam.inputs[0])
    seam.inputs[1].default_value = 0.99
    both = B.node("FunctionNodeBooleanMath", operation="AND")
    B.ng.links.new(ex.outputs["Side"], both.inputs[0])
    B.ng.links.new(seam.outputs[0], both.inputs[1])
    dl = B.node("GeometryNodeDeleteGeometry", domain="FACE", mode="ALL")
    B.ng.links.new(sp2.outputs[0], dl.inputs["Geometry"])
    B.ng.links.new(both.outputs[0], dl.inputs["Selection"])
    fw = B.node("GeometryNodeFlipFaces")                  # Seitenwände zeigen sonst nach innen
    B.ng.links.new(dl.outputs[0], fw.inputs["Mesh"])
    B.ng.links.new(ex.outputs["Side"], fw.inputs["Selection"])
    fl = B.node("GeometryNodeFlipFaces")
    B.ng.links.new(fw.outputs[0], fl.inputs["Mesh"])
    B.ng.links.new(ex.outputs["Top"], fl.inputs["Selection"])
    mg = B.node("GeometryNodeMergeByDistance")
    mg.inputs["Distance"].default_value = 0.00005
    B.ng.links.new(B.join([fl.outputs[0], sp.outputs[0]]), mg.inputs["Geometry"])
    go = B.node("NodeGroupOutput")
    B.ng.links.new(mg.outputs[0], go.inputs["Geometry"])
    PARTS["slice"] = mg.outputs[0]
    return ng


def build_group(name=GROUP_NAME, hub_x=0.34, mat_suffix="", template=None):
    """Felge: Bett + das Muster (Objekt, per Object Info) auf N Positionen rotiert + Nabe + Schnittkurve + Materialien."""
    ng = _new_group(name, INPUTS)
    B = Builder(ng)
    I = B.inp
    mm = 0.001
    inch = 0.0254
    R = I("Durchmesser (Zoll)") * (inch / 2.0)
    W = I("Breite J (Zoll)") * inch
    wall, flange, drop = I("Wandstärke (mm)") * mm, I("Flansch (mm)") * mm, I("Tiefbett (mm)") * mm
    r_face = R - wall + 0.001
    r_face_ref = I("Referenz-Durchmesser (Zoll)") * (inch / 2.0) - I("Referenz-Wandstärke (mm)") * mm + 0.001
    dish = I("Schüsseltiefe (mm)") * mm * I("Konkavität")
    z_rim = -(I("Front-Einzug (mm)") * mm)
    sections = I("Auflösung")

    # ---------------- Felgenbett (Profil wie core.barrel_profile)
    outer = [(R + flange, 0.0), (R + flange, -0.006), (R + 0.002, -0.014), (R, -0.020), (R, W * -0.18), (R - drop, W * -0.30),
             (R - drop, W * -0.62), (R, W * -0.74), (R, -W + 0.020), (R + 0.002, -W + 0.014), (R + flange, -W + 0.006), (R + flange, -W)]
    inner = [(rr - wall, z) for rr, z in outer]
    barrel = B.revolve(outer + inner[::-1], True, sections)

    # ---------------- Muster (Objekt) skalieren und auf N Positionen rotieren, Nähte verschweißen
    oi = B.node("GeometryNodeObjectInfo", transform_space="ORIGINAL")
    if template is not None:
        oi.inputs["Object"].default_value = template
    k = r_face / r_face_ref
    tr = B.node("GeometryNodeTransform")
    B.ng.links.new(oi.outputs["Geometry"], tr.inputs["Geometry"])
    B.ng.links.new(B.comb(k, k, 1.0), tr.inputs["Scale"])
    pts = B.node("GeometryNodeMeshCircle")
    pts.inputs["Radius"].default_value = 0.0
    B.ng.links.new(I("Speichen").s, pts.inputs["Vertices"])
    ang = (B.index() * (2.0 * math.pi) / I("Speichen")) + I("Drehung (Grad)") * (math.pi / 180.0)
    iop = B.node("GeometryNodeInstanceOnPoints")
    B.ng.links.new(pts.outputs["Mesh"], iop.inputs["Points"])
    B.ng.links.new(tr.outputs[0], iop.inputs["Instance"])
    B.ng.links.new(B.comb(0.0, 0.0, ang), iop.inputs["Rotation"])
    rl = B.node("GeometryNodeRealizeInstances")
    B.ng.links.new(iop.outputs["Instances"], rl.inputs["Geometry"])
    weld = B.node("GeometryNodeMergeByDistance")
    weld.inputs["Distance"].default_value = 0.0004
    B.ng.links.new(rl.outputs[0], weld.inputs["Geometry"])

    # ---------------- Nabe: Radschrauben ODER Zentralverschluss (auf der flachen Nabenoberseite z = 0)
    bolt = B.node("GeometryNodeMeshCylinder")
    bolt.inputs["Vertices"].default_value = 6
    bolt.inputs["Radius"].default_value = 0.0105
    bolt.inputs["Depth"].default_value = 0.022
    bz = B.node("GeometryNodeTransform")
    B.ng.links.new(bolt.outputs["Mesh"], bz.inputs["Geometry"])
    bz.inputs["Translation"].default_value = (0.0, 0.0, 0.009)
    cpts = B.node("GeometryNodeMeshCircle")
    B.ng.links.new(I("Radschrauben").s, cpts.inputs["Vertices"])
    B.ng.links.new((I("Lochkreis (mm)") * (mm / 2.0)).s, cpts.inputs["Radius"])
    bi = B.node("GeometryNodeInstanceOnPoints")
    B.ng.links.new(cpts.outputs["Mesh"], bi.inputs["Points"])
    B.ng.links.new(bz.outputs[0], bi.inputs["Instance"])
    bl = B.node("GeometryNodeRealizeInstances")
    B.ng.links.new(bi.outputs["Instances"], bl.inputs["Geometry"])
    nut = B.node("GeometryNodeMeshCylinder")
    nut.inputs["Vertices"].default_value = 24
    nut.inputs["Radius"].default_value = 0.034
    nut.inputs["Depth"].default_value = 0.024
    nt = B.node("GeometryNodeTransform")
    B.ng.links.new(nut.outputs["Mesh"], nt.inputs["Geometry"])
    nt.inputs["Translation"].default_value = (0.0, 0.0, 0.011)
    sw = B.node("GeometryNodeSwitch", input_type="GEOMETRY")
    B.ng.links.new(I("Zentralverschluss").s, sw.inputs["Switch"])
    B.ng.links.new(bl.outputs[0], sw.inputs["False"])
    B.ng.links.new(nt.outputs[0], sw.inputs["True"])

    # ---------------- Schnittkurve: ein Float-Curve-Knoten hebt/senkt den ganzen Stern (Muster + Schrauben)
    flat = B.join([weld.outputs[0], sw.outputs[0]])
    zx, zy, _zz = B.sep(B.position())
    depth = B.curve(CURVE_SECTION, B.clamp01(B.sqrt(zx * zx + zy * zy) / r_face), default_section_points(hub_x))
    szp = B.node("GeometryNodeSetPosition")
    B.ng.links.new(flat, szp.inputs["Geometry"])
    B.ng.links.new(B.comb(0.0, 0.0, z_rim - dish * depth), szp.inputs["Offset"])
    star_geo = szp.outputs[0]
    PARTS.clear()
    PARTS.update(barrel=barrel, star=star_geo, flat=flat, welded=weld.outputs[0], bolts=sw.outputs[0])

    # ---------------- Materialien (Front über die Normale), Glätten
    mfront, mbody = _materials(mat_suffix)
    body_all = B.join([barrel, star_geo])
    setb = B.node("GeometryNodeSetMaterial")
    B.ng.links.new(body_all, setb.inputs["Geometry"])
    setb.inputs["Material"].default_value = mbody
    nrm = B.node("GeometryNodeInputNormal")
    cz = B.node("FunctionNodeCompare", data_type="FLOAT", operation="GREATER_THAN")
    nz = B.sep(nrm.outputs[0])[2]
    B.ng.links.new(nz.s, cz.inputs[0])
    cz.inputs[1].default_value = 0.3
    zn = B.node("GeometryNodeInputNamedAttribute", data_type="FLOAT")
    zn.inputs["Name"].default_value = "zone"
    cr = B.node("FunctionNodeCompare", data_type="FLOAT", operation="GREATER_THAN")
    B.ng.links.new(zn.outputs["Attribute"], cr.inputs[0])
    cr.inputs[1].default_value = 0.6
    both0 = B.node("FunctionNodeBooleanMath", operation="AND")
    B.ng.links.new(cz.outputs[0], both0.inputs[0])
    B.ng.links.new(cr.outputs[0], both0.inputs[1])
    both = B.node("FunctionNodeBooleanMath", operation="AND")
    B.ng.links.new(both0.outputs[0], both.inputs[0])
    B.ng.links.new(I("Diamond Cut").s, both.inputs[1])
    setf = B.node("GeometryNodeSetMaterial")
    B.ng.links.new(setb.outputs[0], setf.inputs["Geometry"])
    B.ng.links.new(both.outputs[0], setf.inputs["Selection"])
    setf.inputs["Material"].default_value = mfront
    sm = B.node("GeometryNodeSetShadeSmooth")
    B.ng.links.new(setf.outputs[0], sm.inputs["Mesh"])
    sm.inputs["Shade Smooth"].default_value = True
    go = B.node("NodeGroupOutput")
    B.ng.links.new(sm.outputs[0], go.inputs["Geometry"])
    return ng


def add_finish_modifiers(ob):
    """Bevel (Kanten) + Weighted Normal nach dem Node-Baum; Händisch weiter bearbeitbar oder per 'Anwenden' festschreiben."""
    import math as _m
    bv = ob.modifiers.new("Kantenfase", "BEVEL")
    bv.width, bv.segments = 0.0008, 2
    bv.limit_method, bv.angle_limit = "ANGLE", _m.radians(35)
    wn = ob.modifiers.new("Gewichtete Normalen", "WEIGHTED_NORMAL")
    wn.keep_sharp = True
    return bv, wn


def template_mesh_from_data(name, td):
    """
    Pizzastück-Mesh (Quads) aus dem Datenfeld von paramdetect.build_template: Oberseite, Unterseite, Seitenwände
    (ohne die Nähte, dort schließt der Nachbar). Attribut „zone“ = polierte Fläche (1) / Rahmen (0).
    """
    import numpy as np
    pos = np.asarray(td["pos"], np.float64)
    top = np.asarray(td["top"], np.float64)
    bot = np.asarray(td["bot"], np.float64)
    zone = np.asarray(td["zone"], np.float64)
    fl, fr = np.asarray(td["fl"], np.float64).copy(), np.asarray(td["fr"], np.float64).copy()
    R, C = top.shape
    tl, trr = fl < 0.004, fr > 0.996
    fl[tl & ~trr] = 0.008                                # einseitiger Nahtkontakt zurücknehmen (wie im Node-Baum)
    fr[trr & ~tl] = 0.992
    seam_l = (fl < 0.004)
    seam_r = (fr > 0.996)
    verts = []
    for z in (top, bot):
        for i in range(R):
            for j in range(C):
                verts.append((pos[i, j, 0], pos[i, j, 1], z[i, j]))
    nT = R * C
    faces = []

    def tp(i, j): return i * C + j

    def bt(i, j): return nT + i * C + j
    for i in range(R - 1):
        for j in range(C - 1):
            faces.append((tp(i, j), tp(i + 1, j), tp(i + 1, j + 1), tp(i, j + 1)))
            faces.append((bt(i, j + 1), bt(i + 1, j + 1), bt(i + 1, j), bt(i, j)))

    def wall(a, b, outward):
        q = [tp(*a), tp(*b), bt(*b), bt(*a)]
        p0, p1, p3 = np.array(verts[q[0]]), np.array(verts[q[1]]), np.array(verts[q[3]])
        n = np.cross(p1 - p0, p3 - p0)
        if n[0] * outward[0] + n[1] * outward[1] < 0:
            q = q[::-1]
        faces.append(tuple(q))
    for i in range(R - 1):
        if not (seam_l[i] and seam_l[i + 1]):
            wall((i, 0), (i + 1, 0), pos[i, 0] - pos[i, 1])
        if not (seam_r[i] and seam_r[i + 1]):
            wall((i, C - 1), (i + 1, C - 1), pos[i, C - 1] - pos[i, C - 2])
    for j in range(C - 1):
        wall((0, j), (0, j + 1), pos[0, j] - pos[1, j])
        wall((R - 1, j), (R - 1, j + 1), pos[R - 1, j] - pos[R - 2, j])
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(float(c) for c in v) for v in verts], [], faces)
    me.update()
    attr = me.attributes.new("zone", "FLOAT", "POINT")
    vals = [float(v) for v in zone.ravel()] * 2
    attr.data.foreach_set("value", vals)
    for p in me.polygons:
        p.use_smooth = True
    return me


def make_object(name, collection, group=None, hub_x=0.34, tdata=None):
    """
    Felge mit Muster: legt das Muster-Objekt („<name> Speiche“, sichtbar, im Edit Mode bearbeitbar) und das Felgen-Objekt an;
    die Felge liest das Muster per Object Info. Mit tdata (aus dem KI-Mesh abgeleitet) ist das Muster direkt ein Mesh,
    sonst entsteht es aus dem parametrischen Node-Baum. Gibt (Felge, Muster, Felgen-Modifier) zurück.
    """
    t_md = None
    if tdata is not None:
        t_me = template_mesh_from_data(name + " Speiche", tdata)
        t_ob = bpy.data.objects.new(name + " Speiche", t_me)
        collection.objects.link(t_ob)
    else:
        t_ng = build_slice_group(name + " Speiche")
        t_me = bpy.data.meshes.new(name + " Speiche")
        t_ob = bpy.data.objects.new(name + " Speiche", t_me)
        collection.objects.link(t_ob)
        t_md = t_ob.modifiers.new("Musterspeiche", "NODES")
        t_md.node_group = t_ng
    ng = build_group(name=name, hub_x=hub_x, mat_suffix=" " + name, template=t_ob)
    me = bpy.data.meshes.new(name)
    ob = bpy.data.objects.new(name, me)
    collection.objects.link(ob)
    md = ob.modifiers.new("Parametrische Felge", "NODES")
    md.node_group = ng
    add_finish_modifiers(ob)
    t_ob.display_type = "WIRE"                 # sichtbar und wählbar, stört aber die Felge nicht
    t_ob.hide_render = True
    return ob, t_ob, md


def socket_ids(ng):
    """Name -> Identifier der Eingänge der Node-Group."""
    return {i.name: i.identifier for i in ng.interface.items_tree if getattr(i, "in_out", "") == "INPUT"}


def _input_struct(md, ident):
    props = getattr(md, "properties", None)          # Blender 5.x: md.properties.inputs.Socket_N.value
    if props is not None and hasattr(props, "inputs") and hasattr(props.inputs, ident):
        return getattr(props.inputs, ident)
    return None


def set_param(md, name, value):
    ident = socket_ids(md.node_group)[name]
    st = _input_struct(md, ident)
    if st is not None:
        st.value = value
    else:
        md[ident] = value
    md.id_data.update_tag()


def get_param(md, name):
    ident = socket_ids(md.node_group)[name]
    st = _input_struct(md, ident)
    return st.value if st is not None else md[ident]


def curve_node(md, name=CURVE_SECTION):
    return md.node_group.nodes[name]


def apply_all(context, ob):
    """Modifier-Stack festschreiben (Node-Baum, Bevel, Weighted Normal) -> normales Mesh zum Nacharbeiten."""
    dg = context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=dg)
    old = ob.data
    ob.modifiers.clear()
    ob.data = me
    me.name = ob.name
    if old.users == 0:
        bpy.data.meshes.remove(old)
    return me
