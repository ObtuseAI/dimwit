import bpy, sys, glob, os
SRC = os.path.abspath(sys.argv[sys.argv.index("--")+1])
DST = os.path.abspath(sys.argv[sys.argv.index("--")+2])
os.makedirs(DST, exist_ok=True)
# category -> (UE prefix, target tris)
CAT = {"vehicles":("SM_Veh_",60000), "guns":("SM_Wpn_Gun_",18000), "melee":("SM_Wpn_Melee_",18000)}
def decimate(src, out, target):
    for o in list(bpy.data.objects): bpy.data.objects.remove(o, do_unlink=True)
    bpy.ops.import_scene.gltf(filepath=src)
    ms=[o for o in bpy.context.scene.objects if o.type=='MESH']
    if not ms: return False
    for o in ms: o.select_set(True)
    bpy.context.view_layer.objects.active=ms[0]
    if len(ms)>1: bpy.ops.object.join()
    ob=bpy.context.view_layer.objects.active
    tris=sum(len(p.vertices)-2 for p in ob.data.polygons)
    if tris>target:
        m=ob.modifiers.new("d","DECIMATE"); m.decimate_type='COLLAPSE'; m.ratio=target/max(tris,1)
        bpy.ops.object.modifier_apply(modifier="d")
    bpy.ops.export_scene.gltf(filepath=out, export_format='GLB', use_selection=False)
    return True
done=0
for g in sorted(glob.glob(os.path.join(SRC,"*.glb"))):
    base=os.path.basename(g)
    cat=base.split("__")[0]; name=base.split("__")[1].replace(".glb","")
    if cat not in CAT: continue
    pref,tgt=CAT[cat]
    out=os.path.join(DST, f"{pref}{name}.glb")
    if decimate(g,out,tgt): done+=1; print(f"STAGED {pref}{name}")
print(f"PROP_DECIMATE_DONE {done}")
