"""WANEFALL modular map kit generator (Blender, free + deterministic).
Builds a grid-snapped, game-ready environment kit in the dark-metal + Wane-accent look from the redesign bible:
two material slots per piece (M_KitMetal dark PBR + M_WaneAccent emissive teal). Pivots at base-center so pieces
sit on the floor and tile on a 4m grid. Exports one GLB per piece to artifacts/kit_out.
Run:  blender --background --python scripts/blender/build_map_kit.py
"""
import bpy, bmesh, os, math, random
random.seed(7)

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "artifacts", "kit_out")
os.makedirs(OUT, exist_ok=True)

# ---- materials -------------------------------------------------------------
def mk_metal():
    m = bpy.data.materials.new("M_KitMetal"); m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (0.045, 0.05, 0.06, 1.0)
    b.inputs["Metallic"].default_value = 0.85
    b.inputs["Roughness"].default_value = 0.45
    return m

def mk_accent():
    m = bpy.data.materials.new("M_WaneAccent"); m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (0.02, 0.05, 0.06, 1.0)
    b.inputs["Roughness"].default_value = 0.3
    b.inputs["Emission Color"].default_value = (0.12, 0.86, 1.0, 1.0)   # Wane teal (saturation = truth)
    b.inputs["Emission Strength"].default_value = 4.0
    return m

METAL = mk_metal()
ACCENT = mk_accent()

# ---- helpers ---------------------------------------------------------------
def add_box(dims, loc, mat):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc)
    o = bpy.context.active_object
    o.dimensions = (dims[0], dims[1], dims[2])
    bpy.ops.object.transform_apply(scale=True)
    o.data.materials.clear(); o.data.materials.append(mat)
    return o

def finalize(parts, name, bevel=0.02):
    """Join parts (metal first so slot 0 = metal, slot 1 = accent), bevel, base-center pivot, smooth-ish."""
    for o in bpy.data.objects:
        o.select_set(o in parts)
    bpy.context.view_layer.objects.active = parts[0]
    if len(parts) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    obj.name = name
    # Parts already carry the shared METAL/ACCENT datablocks as their single slot; join dedupes them into the
    # correct 2 slots with valid polygon indices. (Do NOT clear+re-append here — that scrambles the mapping and
    # glTF then drops the unused accent material, killing the Wane glow.)
    if bevel > 0:
        md = obj.modifiers.new("bev", "BEVEL"); md.width = bevel; md.segments = 2; md.limit_method = 'ANGLE'
        bpy.ops.object.modifier_apply(modifier="bev")
    bpy.context.scene.cursor.location = (0, 0, 0)
    bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
    for p in obj.data.polygons: p.use_smooth = False
    return obj

def assign_slot(obj, slot):
    pass  # no-op: each part already carries the correct material (METAL or ACCENT) as its single slot

def export(obj, name):
    for o in bpy.data.objects: o.select_set(o == obj)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, name + ".glb"),
                              export_format='GLB', use_selection=True)

def clear():
    for o in list(bpy.data.objects): bpy.data.objects.remove(o, do_unlink=True)

# Each builder returns (parts_list). Metal parts get METAL, accent parts get ACCENT; finalize reorders slots.
def part(dims, loc, mat):
    o = add_box(dims, loc, mat)
    return o

# ---- pieces ----------------------------------------------------------------
def floor():       # 4x4 tile, recessed Wane cross-seam
    body = part((4.0, 4.0, 0.2), (0, 0, 0.1), METAL)
    seam1 = part((4.0, 0.06, 0.205), (0, 0, 0.1), ACCENT)
    seam2 = part((0.06, 4.0, 0.205), (0, 0, 0.1), ACCENT)
    assign_slot(body, 0); assign_slot(seam1, 1); assign_slot(seam2, 1)
    return finalize([body, seam1, seam2], "SM_Kit_Floor", bevel=0.0)

def wall():        # 4 wide x 3 tall, vertical center Wane-seam groove
    body = part((4.0, 0.3, 3.0), (0, 0, 1.5), METAL)
    seam = part((0.10, 0.32, 3.0), (0, 0, 1.5), ACCENT)
    assign_slot(body, 0); assign_slot(seam, 1)
    return finalize([body, seam], "SM_Kit_Wall")

def cover():       # waist-high half-wall, accent trim near top
    body = part((2.0, 0.5, 1.1), (0, 0, 0.55), METAL)
    trim = part((2.05, 0.52, 0.08), (0, 0, 1.0), ACCENT)
    assign_slot(body, 0); assign_slot(trim, 1)
    return finalize([body, trim], "SM_Kit_Cover")

def ramp():        # 4 long wedge rising 2m (build box, shear top into a slope)
    o = part((4.0, 2.0, 2.0), (0, 0, 1.0), METAL)
    bm = bmesh.new(); bm.from_mesh(o.data)
    for v in bm.verts:
        if v.co.x > 0:   # front edge to floor -> wedge
            v.co.z = max(0.0, v.co.z - 1.0 - (v.co.x))
    bm.to_mesh(o.data); bm.free()
    assign_slot(o, 0)
    return finalize([o], "SM_Kit_Ramp", bevel=0.0)

def pillar():      # column with a glowing Wane core strip on all 4 faces
    body = part((0.8, 0.8, 4.0), (0, 0, 2.0), METAL)
    parts = [body]; assign_slot(body, 0)
    for (dx, dy, w, d) in [(0, 0.41, 0.16, 0.04), (0, -0.41, 0.16, 0.04),
                           (0.41, 0, 0.04, 0.16), (-0.41, 0, 0.04, 0.16)]:
        s = part((max(w, d) if dx == 0 else w, d if dx == 0 else max(w, d), 3.4), (dx, dy, 2.0), ACCENT)
        assign_slot(s, 1); parts.append(s)
    return finalize(parts, "SM_Kit_Pillar")

def vein():        # load-bearing Wane-vein conduit run (4m), emissive core in a dark housing
    house = part((4.0, 0.28, 0.28), (0, 0, 0.14), METAL)
    core = part((4.02, 0.12, 0.12), (0, 0, 0.14), ACCENT)
    assign_slot(house, 0); assign_slot(core, 1)
    return finalize([house, core], "SM_Kit_Vein")

def arch():        # portal frame: two posts + lintel, accent trim around the opening
    posts = [part((0.4, 0.4, 3.0), (-1.45, 0, 1.5), METAL), part((0.4, 0.4, 3.0), (1.45, 0, 1.5), METAL)]
    lintel = part((3.3, 0.4, 0.5), (0, 0, 3.25), METAL)
    trimL = part((0.06, 0.42, 3.0), (-1.25, 0, 1.5), ACCENT)
    trimR = part((0.06, 0.42, 3.0), (1.25, 0, 1.5), ACCENT)
    trimT = part((2.5, 0.42, 0.06), (0, 0, 3.0), ACCENT)
    for p in posts + [lintel]: assign_slot(p, 0)
    for p in (trimL, trimR, trimT): assign_slot(p, 1)
    return finalize(posts + [lintel, trimL, trimR, trimT], "SM_Kit_Arch")

def crate():       # supply crate with an accent X-brace
    body = part((1.2, 1.2, 1.2), (0, 0, 0.6), METAL)
    b1 = part((1.7, 0.05, 0.08), (0, 0.61, 0.6), ACCENT); b1.rotation_euler[1] = math.radians(45)
    bpy.ops.object.transform_apply(rotation=True)
    b2 = part((1.7, 0.05, 0.08), (0, 0.61, 0.6), ACCENT); b2.rotation_euler[1] = math.radians(-45)
    bpy.ops.object.transform_apply(rotation=True)
    assign_slot(body, 0); assign_slot(b1, 1); assign_slot(b2, 1)
    return finalize([body, b1, b2], "SM_Kit_Crate")

def debris():      # Fallen-ground rubble cluster (entropy aesthetic), a few accent-cracked slabs
    parts = []
    for i in range(7):
        sx, sy, sz = random.uniform(0.4, 1.1), random.uniform(0.3, 0.9), random.uniform(0.15, 0.6)
        x, y = random.uniform(-1.2, 1.2), random.uniform(-1.2, 1.2)
        p = part((sx, sy, sz), (x, y, sz / 2), METAL)
        p.rotation_euler[2] = random.uniform(0, math.pi); bpy.ops.object.transform_apply(rotation=True)
        assign_slot(p, 0); parts.append(p)
        if i % 3 == 0:
            c = part((sx * 0.9, 0.04, sz * 0.7), (x, y, sz / 2), ACCENT); assign_slot(c, 1); parts.append(c)
    return finalize(parts, "SM_Kit_Debris", bevel=0.0)

def stairs():      # 6-step staircase, accent edge up the side
    parts = []
    steps, sw, sd, sh = 6, 3.0, 0.42, 0.26
    for i in range(steps):
        parts.append(part((sw, sd, sh * (i + 1)), (0, i * sd - (steps * sd) / 2 + sd / 2, sh * (i + 1) / 2), METAL))
    parts.append(part((0.08, steps * sd, sh * steps), (sw / 2 + 0.01, 0, sh * steps / 2), ACCENT))
    return finalize(parts, "SM_Kit_Stairs", bevel=0.0)

def catwalk():     # elevated walkway: deck + 2 rails + a Wane underglow strip
    deck = part((4.0, 1.6, 0.18), (0, 0, 0.09), METAL)
    railL = part((4.0, 0.08, 0.5), (0, 0.76, 0.34), METAL)
    railR = part((4.0, 0.08, 0.5), (0, -0.76, 0.34), METAL)
    glow = part((4.02, 1.3, 0.04), (0, 0, -0.01), ACCENT)
    return finalize([deck, railL, railR, glow], "SM_Kit_Catwalk")

def corner_wall(): # L-shaped corner, Wane seam on each leg
    a = part((4.0, 0.3, 3.0), (0, -1.85, 1.5), METAL)
    b = part((0.3, 4.0, 3.0), (-1.85, 0, 1.5), METAL)
    sa = part((0.10, 0.32, 3.0), (0, -1.85, 1.5), ACCENT)
    sb = part((0.32, 0.10, 3.0), (-1.85, 0, 1.5), ACCENT)
    return finalize([a, b, sa, sb], "SM_Kit_CornerWall")

def plaza():       # 8x8 open floor with a Wane cross + center medallion
    body = part((8.0, 8.0, 0.2), (0, 0, 0.1), METAL)
    c1 = part((8.0, 0.07, 0.205), (0, 0, 0.1), ACCENT)
    c2 = part((0.07, 8.0, 0.205), (0, 0, 0.1), ACCENT)
    med = part((1.4, 1.4, 0.21), (0, 0, 0.1), ACCENT)
    return finalize([body, c1, c2, med], "SM_Kit_Plaza", bevel=0.0)

def barrier():     # low Wane-lit railing for catwalk edges / ledges
    rail = part((4.0, 0.12, 0.12), (0, 0, 1.0), METAL)
    posts = [part((0.12, 0.12, 1.0), (px, 0, 0.5), METAL) for px in (-1.8, 0.0, 1.8)]
    glow = part((4.02, 0.06, 0.04), (0, 0, 1.0), ACCENT)
    return finalize([rail] + posts + [glow], "SM_Kit_Barrier")

def fallen_wall(): # the entropy aesthetic: a wall half collapsed, accent crack + rubble
    left = part((1.8, 0.3, 3.0), (-1.0, 0, 1.5), METAL)
    right = part((1.6, 0.3, 1.6), (1.1, 0, 0.8), METAL)
    crack = part((0.07, 0.32, 2.3), (-0.05, 0, 1.45), ACCENT)
    rub1 = part((0.7, 0.5, 0.45), (0.7, 0.35, 0.22), METAL)
    rub2 = part((0.5, 0.4, 0.3), (1.6, -0.2, 0.15), METAL)
    return finalize([left, right, crack, rub1, rub2], "SM_Kit_FallenWall", bevel=0.0)

def spire():       # a tall glowing Wane obelisk / objective beacon (a mini landmark)
    base = part((0.7, 0.7, 0.45), (0, 0, 0.22), METAL)
    shaft = part((0.3, 0.3, 5.0), (0, 0, 2.75), METAL)
    core = part((0.13, 0.13, 5.3), (0, 0, 2.75), ACCENT)
    tip = part((0.42, 0.42, 0.42), (0, 0, 5.4), ACCENT)
    return finalize([base, shaft, core, tip], "SM_Kit_Spire")

BUILDERS = [floor, wall, cover, ramp, pillar, vein, arch, crate, debris,
            stairs, catwalk, corner_wall, plaza, barrier, fallen_wall, spire]
done = 0
for b in BUILDERS:
    clear()
    METAL_ref = METAL  # materials persist across clears (data blocks)
    obj = b()
    export(obj, obj.name)
    print(f"KIT {obj.name} verts={len(obj.data.vertices)} faces={len(obj.data.polygons)}", flush=True)
    done += 1
print(f"MAP_KIT_DONE {done}")
