"""scripts/blender/reskin_manny_blender.py — headless Blender re-skin of alien geometry onto the GENUINE SK_Mannequin.

WHY (2026-07-04): the roster's fragile Blender auto-rig produced a skeleton that is NOT truly the UE5 Manny
skeleton, so at runtime ABP_Manny drove mismatched bones (bizarre walk) and hand_r/hand_l sockets failed
(floating gun/grappler). The fix is NOT another auto-rig — it is to re-skin the alien GEOMETRY onto Epic's
real SK_Mannequin, inheriting Manny's proven skin weights. Then it drives ABP_Manny natively and has working
hand sockets. This produces clean deformation without any external auto-rig service (Accurig/Mixamo).

PIPELINE (per char):
  1. import the Manny FBX (SK_Mannequin armature + 48779-vert skinned reference mesh, 110 vgroups).
     Source it with scripts/ue/ue_reskin_export_manny.py (must run with FULL RHI — -nullrhi crashes FBX skeletal export).
  2. APPLY transforms to the armature + Manny mesh. UE-exported FBX carries a 0.01 object scale; if you don't
     bake it, the bound alien collapses to 1/100 scale (a tiny blob). This is the #1 gotcha.
  3. import the alien geometry FBX (Z-up, ~1.9 tall, centred at origin, A-pose, NO weights).
  4. align alien to Manny: scale to Manny mesh height, align feet to z=0, centre XY. (Both extend more toward
     -Y = they face the same way; if a future asset faces the other way pass 'flipy'.)
  5. transfer skin weights Manny -> alien: data_transfer VGROUP_WEIGHTS, POLYINTERP_NEAREST, layers ALL.
  6. bind via bpy.ops.object.parent_set(type='ARMATURE') — the OPERATOR sets the correct bind/parent-inverse.
     A hand-added Armature modifier + manual parent does NOT and collapses the rest pose.
  7. delete the Manny mesh, export alien + SK_Mannequin armature to FBX for UE.
  8. self-check: pose a few bones (arms/legs) and WORKBENCH-render, framed on the depsgraph-EVALUATED bbox
     (not the undeformed bound_box, which ignores the armature modifier). Own-eyes the PNG for collapse.

RUN:  blender --background --python scripts/blender/reskin_manny_blender.py -- <char> [flipy]
      (char = zythan|qorin|therak|ullio|kelous|nexor). Requires Blender 4.2+ (tested 5.1).
"""
import bpy, os, sys, math
from mathutils import Vector

DIMWIT = r"C:\Users\developer\Documents\Dimwit"
ALIEN_DIR = os.path.join(DIMWIT, "artifacts", "mixamo_export")            # geometry-only alien FBXs
OUT_DIR   = os.path.join(DIMWIT, "artifacts", "reskin_manny")             # outputs
MANNY_FBX = os.path.join(OUT_DIR, "manny_src", "SKM_Manny.fbx")            # from scripts/ue/ue_reskin_export_manny.py

argv = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
CHAR = argv[0] if argv else "zythan"
FLIP_Y = ("flipy" in argv)
os.makedirs(OUT_DIR, exist_ok=True)
ALIEN_FBX = os.path.join(ALIEN_DIR, CHAR + ".fbx")
OUT_FBX   = os.path.join(OUT_DIR, CHAR + "_reskin.fbx")
LOG       = os.path.join(OUT_DIR, CHAR + "_log.txt")
RENDER    = os.path.join(OUT_DIR, CHAR + ("_flipy" if FLIP_Y else "") + "_deform.png")

def w(m):
    with open(LOG, "a") as f: f.write(str(m)+"\n")
    print("RESKIN "+str(m))
open(LOG,"w").close()
bpy.ops.wm.read_factory_settings(use_empty=True)

def bbox(obj):
    cs=[obj.matrix_world @ Vector(c) for c in obj.bound_box]
    xs=[c.x for c in cs]; ys=[c.y for c in cs]; zs=[c.z for c in cs]
    return Vector((min(xs),min(ys),min(zs))), Vector((max(xs),max(ys),max(zs)))

# 1) Manny
before=set(bpy.data.objects)
bpy.ops.import_scene.fbx(filepath=MANNY_FBX)
new=set(bpy.data.objects)-before
arm=[o for o in new if o.type=='ARMATURE'][0]
manny_mesh=max([o for o in new if o.type=='MESH'],key=lambda m:len(m.data.vertices))
# 2) bake the 0.01 import scale
bpy.ops.object.select_all(action='DESELECT')
arm.select_set(True); manny_mesh.select_set(True); bpy.context.view_layer.objects.active=arm
bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
mn0,mx0=bbox(manny_mesh)
w("manny dims=%s vgroups=%d"%(tuple(round(mx0[i]-mn0[i],3) for i in range(3)),len(manny_mesh.vertex_groups)))

# 3) alien
before=set(bpy.data.objects)
bpy.ops.import_scene.fbx(filepath=ALIEN_FBX)
alien=max([o for o in set(bpy.data.objects)-before if o.type=='MESH'],key=lambda m:len(m.data.vertices))
bpy.ops.object.select_all(action='DESELECT')
alien.select_set(True); bpy.context.view_layer.objects.active=alien
bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
an0,ax0=bbox(alien)
# 4) align: scale to Manny height, feet to z=0, centre XY
s=(mx0.z-mn0.z)/(ax0.z-an0.z)
alien.scale=(s,s,s); bpy.context.view_layer.update(); bpy.ops.object.transform_apply(scale=True)
an0,ax0=bbox(alien)
if FLIP_Y:
    alien.rotation_euler=(0,0,math.pi); bpy.context.view_layer.update(); bpy.ops.object.transform_apply(rotation=True); an0,ax0=bbox(alien)
mcen=(mn0+mx0)/2; acen=(an0+ax0)/2
alien.location=(mcen.x-acen.x, mcen.y-acen.y, mn0.z-an0.z)
bpy.context.view_layer.update(); bpy.ops.object.transform_apply(location=True)
an0,ax0=bbox(alien)
w("scale=%.4f aligned_dims=%s"%(s,tuple(round(ax0[i]-an0[i],3) for i in range(3))))

# 5) transfer weights Manny -> alien (ACTIVE = source)
bpy.ops.object.select_all(action='DESELECT')
manny_mesh.select_set(True); alien.select_set(True); bpy.context.view_layer.objects.active=manny_mesh
bpy.ops.object.data_transfer(use_reverse_transfer=False, data_type='VGROUP_WEIGHTS',
    vert_mapping='POLYINTERP_NEAREST', layers_select_src='ALL', layers_select_dst='NAME', mix_mode='REPLACE')
w("vgroups_after=%d"%len(alien.vertex_groups))

# 5b) CLEAN WEIGHTS — nearest-surface gives protruding alien geo (broad shoulders/pads) rigid single-bone
# weights that splay into flat sheets when the arm swings (the "extra arms" artifact). Limit influences,
# normalize, then spatially SMOOTH all groups (weight-paint mode required for the smooth op in headless).
bpy.ops.object.select_all(action='DESELECT')
alien.select_set(True); bpy.context.view_layer.objects.active=alien
if len(alien.vertex_groups)>0: alien.vertex_groups.active_index=0
bpy.ops.object.vertex_group_limit_total(group_select_mode='ALL', limit=8)
bpy.ops.object.vertex_group_normalize_all(group_select_mode='ALL', lock_active=False)
bpy.ops.object.mode_set(mode='WEIGHT_PAINT')
# moderate: enough to kill the shoulder-fan artifact, not so much it melts joints (14x read as "disfigured")
bpy.ops.object.vertex_group_smooth(group_select_mode='ALL', factor=0.5, repeat=5, expand=0.0)
bpy.ops.object.mode_set(mode='OBJECT')
bpy.ops.object.vertex_group_normalize_all(group_select_mode='ALL', lock_active=False)
w("weights_cleaned limit8 + smooth5@0.5")

# 6) bind via operator
bpy.ops.object.select_all(action='DESELECT')
alien.select_set(True); arm.select_set(True); bpy.context.view_layer.objects.active=arm
bpy.ops.object.parent_set(type='ARMATURE')
# 7) delete Manny mesh
bpy.ops.object.select_all(action='DESELECT'); manny_mesh.select_set(True); bpy.ops.object.delete()
# export (bind pose)
bpy.ops.object.select_all(action='DESELECT')
alien.select_set(True); arm.select_set(True); bpy.context.view_layer.objects.active=arm
bpy.ops.export_scene.fbx(filepath=OUT_FBX, use_selection=True, add_leaf_bones=False,
    mesh_smooth_type='FACE', bake_anim=False, object_types={'ARMATURE','MESH'})
w("export=%s size=%s"%(os.path.exists(OUT_FBX), os.path.getsize(OUT_FBX) if os.path.exists(OUT_FBX) else -1))

# 8) self-check renders, framed on the EVALUATED (deformed) geometry
def eval_bbox(obj):
    dg=bpy.context.evaluated_depsgraph_get(); ev=obj.evaluated_get(dg); me=ev.to_mesh(); mw=obj.matrix_world
    xs=[];ys=[];zs=[]
    for v in me.vertices:
        c=mw@v.co; xs.append(c.x);ys.append(c.y);zs.append(c.z)
    ev.to_mesh_clear(); return Vector((min(xs),min(ys),min(zs))),Vector((max(xs),max(ys),max(zs)))
cam_d=bpy.data.cameras.new("C"); cam=bpy.data.objects.new("C",cam_d); bpy.context.collection.objects.link(cam)
cam_d.type='ORTHO'; cam.rotation_euler=(math.radians(90),0,0); bpy.context.scene.camera=cam
world=bpy.data.worlds.new("W"); bpy.context.scene.world=world; world.use_nodes=False; world.color=(0.05,0.08,0.12)
sc=bpy.context.scene; sc.render.engine='BLENDER_WORKBENCH'
sc.display.shading.light='STUDIO'; sc.display.shading.color_type='SINGLE'; sc.display.shading.single_color=(0.75,0.75,0.8); sc.display.shading.show_cavity=True
sc.render.resolution_x=400; sc.render.resolution_y=600
def render(path):
    bpy.context.view_layer.update(); lo,hi=eval_bbox(alien); c=(lo+hi)/2
    cam_d.ortho_scale=max(max(hi.z-lo.z,hi.x-lo.x)*1.3,0.1); cam.location=(c.x,c.y-5.0,c.z)
    sc.render.filepath=path; bpy.ops.render.render(write_still=True); return os.path.exists(path)
w("bind_render=%s"%render(os.path.join(OUT_DIR,CHAR+"_bind.png")))
# RUN-like pose: swing arms on Z (the natural fore/aft swing axis; X on upperarm is TWIST and misleads),
# bend elbows, stride legs — stresses the shoulder skinning where the extra-arm artifact shows.
bpy.context.view_layer.objects.active=arm; bpy.ops.object.mode_set(mode='POSE')
for bn,ax,dg in [("upperarm_r","Z",-45),("upperarm_l","Z",45),("lowerarm_r","Z",-70),("lowerarm_l","Z",70),
                 ("thigh_l","X",45),("thigh_r","X",-45),("calf_l","X",-55),("spine_02","Z",8)]:
    pb=arm.pose.bones.get(bn)
    if pb:
        pb.rotation_mode='XYZ'; r=list(pb.rotation_euler); r[{'X':0,'Y':1,'Z':2}[ax]]+=math.radians(dg); pb.rotation_euler=r
bpy.ops.object.mode_set(mode='OBJECT')
w("pose_render=%s"%render(RENDER)); w("DONE")
