"""Render the ACTUAL in-game meshes (decimated GLBs that were imported to UE) for operator verification.
Keeps each GLB's PBR material; balanced studio + grey environment so dark metallic armor reads (no silver wash).
  blender --background --python scripts/blender/render_ingame.py -- <glb_dir> <out_dir> [front|threequarter]
Renders one clean image per GLB named <stem>.png.
"""
import bpy, sys, math, glob, os, mathutils
A = sys.argv[sys.argv.index("--")+1:]
glb_dir, out_dir = os.path.abspath(A[0]), os.path.abspath(A[1])
view = A[2] if len(A) > 2 else "threequarter"
os.makedirs(out_dir, exist_ok=True)

def clear():
    for o in list(bpy.data.objects): bpy.data.objects.remove(o, do_unlink=True)

scene = bpy.context.scene
scene.render.engine = 'CYCLES'
try: scene.cycles.device = 'CPU'; scene.cycles.samples = 48; scene.cycles.use_denoising = True
except Exception: pass
scene.render.resolution_x = 900; scene.render.resolution_y = 900
scene.render.film_transparent = False
scene.render.image_settings.file_format = 'PNG'

def world_env():
    w = bpy.data.worlds.get('World') or bpy.data.worlds.new('World')
    scene.world = w; w.use_nodes = True
    bg = w.node_tree.nodes.get('Background')
    bg.inputs[0].default_value = (0.012, 0.013, 0.016, 1)  # near-black env -> dark metal reflects dark (not chrome)
    bg.inputs[1].default_value = 1.0

def add_light(name, loc, energy, color, size):
    ld = bpy.data.lights.new(name, 'AREA'); ld.energy = energy; ld.color = color; ld.size = size
    lo = bpy.data.objects.new(name, ld); lo.location = loc; scene.collection.objects.link(lo)
    d = mathutils.Vector((0,0,1.0)) - mathutils.Vector(loc)
    lo.rotation_euler = d.to_track_quat('-Z','Y').to_euler()

def render_one(glb, out_png):
    clear()
    bpy.ops.import_scene.gltf(filepath=glb)
    ms = [o for o in scene.objects if o.type == 'MESH']
    if not ms: return False
    for o in ms: o.select_set(True)
    bpy.context.view_layer.objects.active = ms[0]
    if len(ms) > 1: bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    for p in ob.data.polygons: p.use_smooth = True
    # normalize: height -> 2.0, stand on floor, center
    bb = [ob.matrix_world @ mathutils.Vector(c) for c in ob.bound_box]
    mn = mathutils.Vector((min(v.x for v in bb), min(v.y for v in bb), min(v.z for v in bb)))
    mx = mathutils.Vector((max(v.x for v in bb), max(v.y for v in bb), max(v.z for v in bb)))
    size = mx - mn; h = max(size.z, 1e-4); s = 2.0 / h
    ob.scale = (s, s, s); bpy.ops.object.transform_apply(scale=True)
    bb = [ob.matrix_world @ mathutils.Vector(c) for c in ob.bound_box]
    cx = (min(v.x for v in bb)+max(v.x for v in bb))/2; cy = (min(v.y for v in bb)+max(v.y for v in bb))/2
    zmn = min(v.z for v in bb)
    ob.location = (ob.location.x-cx, ob.location.y-cy, ob.location.z-zmn)
    bpy.ops.object.transform_apply(location=True)
    # floor + backdrop (dark)
    bpy.ops.mesh.primitive_plane_add(size=20, location=(0,0,0)); bpy.context.active_object.data.materials.clear()
    world_env()
    add_light("key",(2.6,-3.0,3.0),320,(1.0,0.97,0.92),4.5)   # soft front-top key (moderate -> no chrome blowout)
    add_light("fill",(-2.2,-2.6,1.5),110,(0.6,0.75,1.0),4.5)  # cool fill
    add_light("rimL",(-2.6,1.8,2.6),520,(0.45,0.7,1.0),1.6)   # blue edge rims define the silhouette
    add_light("rimR",(2.6,1.6,2.4),360,(0.5,0.75,1.0),1.6)
    cam_d = bpy.data.cameras.new("cam"); cam = bpy.data.objects.new("cam", cam_d)
    scene.collection.objects.link(cam); scene.camera = cam; cam_d.lens = 70
    look = mathutils.Vector((0,0,1.05))
    loc = {"front":(5.2,0,1.15), "threequarter":(4.2,-3.2,1.35), "side":(0.2,-5.2,1.1)}[view]
    cam.location = loc; d = look - mathutils.Vector(loc); cam.rotation_euler = d.to_track_quat('-Z','Y').to_euler()
    scene.render.filepath = out_png; bpy.ops.render.render(write_still=True)
    return True

glbs = sorted(glob.glob(os.path.join(glb_dir, "*.glb")))
ok = 0
for g in glbs:
    stem = os.path.splitext(os.path.basename(g))[0]
    if render_one(g, os.path.join(out_dir, stem + ".png")): ok += 1
    print(f"RENDERED {stem}")
print(f"INGAME_RENDER_DONE {ok}/{len(glbs)}")
