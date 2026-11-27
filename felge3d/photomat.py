# SPDX-License-Identifier: GPL-3.0-or-later
"""
Farbe aus dem Foto für eine Meshy-Felge: Das Foto wird von vorn (entlang der Achse) auf die nach außen zeigenden Flächen projiziert;
Form und Rückseite behalten das Meshy-Material. So stimmen Farbe, Glanzlichter und Schrift der Vorderseite mit dem Foto überein.
Die Projektion läuft im Shader (Object-Koordinaten); je Material eine Kopie, die Meshy-Textur bleibt erhalten.
"""
import bpy


def _principled(mat):
    return next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)


def _mix_color(nt):
    """Mix-Knoten für Farben (Blender 3.4+: ShaderNodeMix mit data_type RGBA; sonst MixRGB). Gibt (Knoten, Faktor, A, B, Ergebnis) zurück."""
    try:
        n = nt.nodes.new("ShaderNodeMix")
        n.data_type = "RGBA"
        a = next(s for s in n.inputs if s.name == "A" and s.type == "RGBA")
        b = next(s for s in n.inputs if s.name == "B" and s.type == "RGBA")
        res = next(s for s in n.outputs if s.type == "RGBA")
        return n, n.inputs[0], a, b, res
    except (RuntimeError, StopIteration):
        n = nt.nodes.new("ShaderNodeMixRGB")
        return n, n.inputs["Fac"], n.inputs["Color1"], n.inputs["Color2"], n.outputs["Color"]


def project_photo_material(src, img, cx, cy, rad_u, rad_v, r_max, frame="wheel", name=None, metallic=0.15, roughness=0.5, gain=1.45):
    """
    Kopie von `src` mit Foto-Frontprojektion.
      img            Foto (Blender-Image), cx, cy: Mitte der Felge im Foto (Bruchteile von Breite/Höhe, y von unten wie s.center_y),
      rad_u, rad_v   Radius der Felge im Foto in UV-Einheiten (Breite bzw. Höhe),
      r_max          größter Radius des Meshes (m) = Felgenrand,
      frame          "wheel": Achse = X, Bildebene = (Y, Z) | "photo": Achse = Z, Bildebene = (X, Y).
    Mischfaktor: Normale nach außen (0,3..0,55 der Achse) und innerhalb des Felgenradius. gain: Helligkeitsfaktor der Foto-Farbe.
    """
    m = src.copy()
    m.name = name or (src.name + " Foto")
    m.use_nodes = True
    nt = m.node_tree
    bsdf = _principled(m)
    if bsdf is None:
        return m
    x0, y0 = bsdf.location.x, bsdf.location.y
    tc = nt.nodes.new("ShaderNodeTexCoord")
    tc.location = (x0 - 1500, y0 - 400)
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    sep.location = (x0 - 1300, y0 - 400)
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    nsep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nsep.location = (x0 - 1300, y0 - 650)
    nt.links.new(tc.outputs["Normal"], nsep.inputs[0])
    # Bildebene -> UV (Blender: y von unten, wie s.center_y): u = cx + a / r_max * rad_u, v = cy + b / r_max * rad_v
    a_out, b_out = (sep.outputs["Y"], sep.outputs["Z"]) if frame == "wheel" else (sep.outputs["X"], sep.outputs["Y"])
    n_axis = nsep.outputs["X"] if frame == "wheel" else nsep.outputs["Z"]
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    comb.location = (x0 - 900, y0 - 400)
    mu = nt.nodes.new("ShaderNodeMath")
    mu.operation = "MULTIPLY_ADD"
    mu.location = (x0 - 1100, y0 - 300)
    nt.links.new(a_out, mu.inputs[0])
    mu.inputs[1].default_value = rad_u / r_max
    mu.inputs[2].default_value = cx
    mv = nt.nodes.new("ShaderNodeMath")
    mv.operation = "MULTIPLY_ADD"
    mv.location = (x0 - 1100, y0 - 500)
    nt.links.new(b_out, mv.inputs[0])
    mv.inputs[1].default_value = rad_v / r_max
    mv.inputs[2].default_value = cy
    nt.links.new(mu.outputs[0], comb.inputs["X"])
    nt.links.new(mv.outputs[0], comb.inputs["Y"])
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.extension = "EXTEND"
    tex.interpolation = "Cubic"
    tex.location = (x0 - 700, y0 - 300)
    nt.links.new(comb.outputs[0], tex.inputs["Vector"])
    # Maske: nach außen zeigend UND innerhalb des Felgenradius
    face = nt.nodes.new("ShaderNodeMapRange")
    face.inputs["From Min"].default_value, face.inputs["From Max"].default_value = 0.3, 0.55
    face.clamp = True
    face.location = (x0 - 1100, y0 - 700)
    nt.links.new(n_axis, face.inputs["Value"])
    ra = nt.nodes.new("ShaderNodeMath")
    ra.operation = "POWER"
    ra.inputs[1].default_value = 2.0
    rb = nt.nodes.new("ShaderNodeMath")
    rb.operation = "POWER"
    rb.inputs[1].default_value = 2.0
    nt.links.new(a_out, ra.inputs[0])
    nt.links.new(b_out, rb.inputs[0])
    rs = nt.nodes.new("ShaderNodeMath")
    rs.operation = "ADD"
    nt.links.new(ra.outputs[0], rs.inputs[0])
    nt.links.new(rb.outputs[0], rs.inputs[1])
    rr = nt.nodes.new("ShaderNodeMath")
    rr.operation = "SQRT"
    nt.links.new(rs.outputs[0], rr.inputs[0])
    inside = nt.nodes.new("ShaderNodeMath")
    inside.operation = "LESS_THAN"
    inside.inputs[1].default_value = r_max * 0.985
    nt.links.new(rr.outputs[0], inside.inputs[0])
    fac = nt.nodes.new("ShaderNodeMath")
    fac.operation = "MULTIPLY"
    nt.links.new(face.outputs["Result"], fac.inputs[0])
    nt.links.new(inside.outputs[0], fac.inputs[1])
    for n_ in (ra, rb, rs, rr, inside, fac):
        n_.location = (x0 - 900, y0 - 700)
    node, f_in, a_in, b_in, res = _mix_color(nt)
    node.location = (x0 - 300, y0)
    base_in = bsdf.inputs["Base Color"]
    if base_in.links:                                   # vorhandene Meshy-Textur als A
        nt.links.new(base_in.links[0].from_socket, a_in)
    else:
        a_in.default_value = base_in.default_value
    hs = nt.nodes.new("ShaderNodeHueSaturation")              # Licht steckt schon im Foto: Helligkeit anheben (gain), damit es im Render nicht zu dunkel wird
    hs.inputs["Value"].default_value = gain
    hs.location = (x0 - 500, y0 - 300)
    nt.links.new(tex.outputs["Color"], hs.inputs["Color"])
    nt.links.new(hs.outputs["Color"], b_in)
    nt.links.new(fac.outputs[0], f_in)
    nt.links.new(res, base_in)
    for nm, val in (("Metallic", metallic), ("Roughness", roughness)):       # Glanzlichter stecken schon im Foto: moderates Material
        if nm in bsdf.inputs and not bsdf.inputs[nm].links:
            bsdf.inputs[nm].default_value = val
    return m


def apply_to_mesh(me, img, cx, cy, rad_u, rad_v, r_max, frame="wheel", **kw):
    """Alle Materialplätze eines Meshes durch Foto-Projektionen ersetzen (ohne Material: keine Änderung). Gibt die Zahl der Plätze zurück."""
    n = 0
    for i, mat in enumerate(list(me.materials)):
        if mat is not None and mat.use_nodes:
            me.materials[i] = project_photo_material(mat, img, cx, cy, rad_u, rad_v, r_max, frame=frame, **kw)
            n += 1
    return n


def photo_circle(s):
    """Felgenkreis im Foto als (cx, cy, rad_u, rad_v) in UV-Bruchteilen aus den Einstellungen der Szene (Breite/Höhe des Bildes)."""
    w, h = s.image.size
    rad_u = s.radius
    rad_v = s.radius * s.aspect * (w / max(h, 1))
    return s.center_x, s.center_y, rad_u, rad_v
