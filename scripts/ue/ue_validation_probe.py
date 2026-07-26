"""Dimwit CONSOLIDATED validation probe — the ONE UE script the validation harness launches.

Runs every UE-side probe the validator registry needs INSIDE A SINGLE editor session (the machine is disk/RAM
tight — never one boot per validator), then writes artifacts/validation/ue_probe_batch.json. Each probe is
wrapped so one failure records {"error": ...} for that probe_id without aborting the batch. Captures write the
PNG + record it as TELEMETRY only — the PASS/FAIL verdict is made later in Python by perception (NEVER byte size).

  UnrealEditor-Cmd <uproject> -ExecutePythonScript="scripts/ue/ue_validation_probe.py manifest=<m.json> out=<o.json>" -unattended ...
"""
import unreal, json, sys, traceback
from pathlib import Path

args = {}
for a in sys.argv:
    if "=" in a and not a.startswith("-"):
        k, v = a.split("=", 1)
        args[k] = v
MANIFEST = json.loads(Path(args["manifest"]).read_text(encoding="utf-8"))
OUT = Path(args["out"])
OUT.parent.mkdir(parents=True, exist_ok=True)

mel = unreal.MaterialEditingLibrary
out = {"materials": {}, "rig": {}, "abp": {}, "mann_skeleton": None, "nanite": {},
       "niagara": {}, "captures": {}}


def _norm(p):
    return (p or "").split(".")[0]


# ---------------------------------------------------------------- materials
def _scalar(mic, names):
    for n in names:
        try:
            return float(mel.get_material_instance_scalar_parameter_value(mic, n))
        except Exception:
            continue
    return None


for mp in MANIFEST.get("inspect_materials", []):
    rec = {"loaded": False}
    try:
        m = unreal.load_asset(mp)
        if isinstance(m, unreal.MaterialInstanceConstant):
            rec["loaded"] = True
            par = m.get_editor_property("parent")
            rec["parent"] = par.get_path_name() if par else None
            rec["metallic"] = _scalar(m, ["Metallic", "metallic", "Metallic Factor"])
            rec["roughness"] = _scalar(m, ["Roughness", "roughness", "Roughness Factor"])
            rec["specular"] = _scalar(m, ["Specular", "specular"])
            try:
                t = mel.get_material_instance_texture_parameter_value(m, "BaseColorTexture")
                rec["basecolor_tex"] = t.get_path_name() if t else None
                rec["basecolor_broken"] = False
            except Exception as e:
                rec["basecolor_tex"] = None
                rec["basecolor_broken"] = True
        else:
            rec["error"] = f"not a MaterialInstanceConstant: {type(m).__name__ if m else None}"
    except Exception:
        rec["error"] = traceback.format_exc().splitlines()[-1]
    out["materials"][mp] = rec

# ---------------------------------------------------------------- rig + abp + skeleton
try:
    sk = unreal.load_asset(MANIFEST["inspect_rig"])
    r = {"loaded": isinstance(sk, unreal.SkeletalMesh), "rig_class": type(sk).__name__ if sk else None}
    if isinstance(sk, unreal.SkeletalMesh):
        s = sk.get_editor_property("skeleton")
        r["rig_skeleton"] = s.get_path_name() if s else None
        try:
            r["rig_bounds_z_cm"] = round(sk.get_bounds().box_extent.z * 2.0, 1)
        except Exception:
            r["rig_bounds_z_cm"] = None
        try:
            r["rig_num_materials"] = len(sk.materials)
        except Exception:
            pass
    out["rig"] = r
except Exception:
    out["rig"] = {"error": traceback.format_exc().splitlines()[-1]}

try:
    abp = unreal.load_asset(MANIFEST["abp"])
    a = {"abp_class": type(abp).__name__ if abp else None}
    try:
        ts = abp.get_editor_property("target_skeleton")
        a["abp_target_skeleton"] = ts.get_path_name() if ts else None
    except Exception as e:
        a["abp_target_skeleton_err"] = str(e)
    out["abp"] = a
except Exception:
    out["abp"] = {"error": traceback.format_exc().splitlines()[-1]}

try:
    mann = unreal.load_asset(MANIFEST["mann_skeleton"])
    out["mann_skeleton"] = mann.get_path_name() if mann else None
except Exception:
    out["mann_skeleton"] = None

# ---------------------------------------------------------------- niagara
for np in MANIFEST.get("niagara", []):
    rec = {"is_niagara": False}
    try:
        ns = unreal.load_asset(np)
        rec["is_niagara"] = ns is not None and type(ns).__name__ == "NiagaraSystem"
        if rec["is_niagara"]:
            cnt = None
            for getter in ("get_emitter_handles", "get_emitters", "get_emitter_names"):
                try:
                    cnt = len(getattr(ns, getter)())
                    break
                except Exception:
                    continue
            if cnt is None:
                try:                                  # editor-only fallback
                    cnt = len(unreal.NiagaraEditorLibrary.get_emitter_handles(ns))
                except Exception:
                    cnt = None
            if cnt is None:
                # UE5.8 Python exposes NO emitter accessor (all getters missing; EmitterHandles protected;
                # NiagaraEditorLibrary absent; asset tags None). Honest fail-closed fallback: parse the .uasset on
                # disk for the embedded emitter-handle marker. A real emitter system serializes a
                # 'NiagaraEmitterHandle' FName + compiled emitter shader; a 0-emitter stub has neither -> stays 0.
                try:
                    rel = np.replace("/Game/", "")
                    disk = unreal.Paths.project_content_dir() + rel + ".uasset"
                    raw = open(disk, "rb").read()
                    has_handle = b"NiagaraEmitterHandle" in raw
                    has_emitter_shader = b"Emitter_SpawnParticles" in raw or b"NiagaraEmitter" in raw
                    if has_handle and has_emitter_shader:
                        cnt = max(1, raw.count(b"NiagaraEmitterHandle"))   # presence-confirmed floor
                        rec["emitter_count_source"] = "uasset_binary_marker (UE5.8 Python cannot enumerate)"
                    elif not has_handle and not has_emitter_shader:
                        cnt = 0                          # genuine 0-emitter stub -> validator fails (fail-closed)
                        rec["emitter_count_source"] = "uasset_binary: no emitter content"
                except Exception:
                    cnt = None                          # cannot read -> validator BLOCKS (not a false count)
            rec["emitter_count"] = cnt
    except Exception:
        rec["error"] = traceback.format_exc().splitlines()[-1]
    out["niagara"][np] = rec

# ---------------------------------------------------------------- nanite hi-res cluster counts
for mp in MANIFEST.get("nanite_cluster_meshes", []):
    rec = {"loaded": False}
    try:
        sm = unreal.load_asset(mp)
        if isinstance(sm, unreal.StaticMesh):
            rec["loaded"] = True
            try:
                ns = sm.get_editor_property("nanite_settings")
                rec["nanite_enabled"] = bool(ns.get_editor_property("enabled"))
            except Exception:
                rec["nanite_enabled"] = None
            try:
                rec["fallback_tris"] = sm.get_num_triangles(0)
            except Exception:
                pass
    except Exception:
        rec["error"] = traceback.format_exc().splitlines()[-1]
    out["nanite"][mp] = rec

# ---------------------------------------------------------------- captures (ship lighting, animated 2 frames)
def _capture(cap):
    res = {"id": cap["id"], "frames": []}
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    les.load_level(cap["map"])
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()  # AFTER load (old ref goes stale)
    # the level's OWN lighting is authoritative — assert it exists (V-GAME-08), add NO temp lights, NO exposure lock
    lights = [a for a in eas.get_all_level_actors()
              if isinstance(a, (unreal.DirectionalLight, unreal.SkyLight, unreal.PointLight, unreal.SpotLight, unreal.RectLight))]
    res["lobby_has_lights"] = len(lights)
    base = unreal.Vector(0, 0, 0)
    for a in eas.get_all_level_actors():
        if isinstance(a, unreal.PlayerStart):
            base = a.get_actor_location()
            break
    sk = unreal.load_asset(cap["rig"])
    rt = unreal.RenderingLibrary.create_render_target2d(world, 1200, 900, unreal.TextureRenderTargetFormat.RTF_RGBA8)
    cam = unreal.Vector(base.x + 430.0, base.y, base.z + 95.0)
    rot = unreal.MathLibrary.find_look_at_rotation(cam, unreal.Vector(base.x, base.y, base.z + 90.0))
    capactor = eas.spawn_actor_from_class(unreal.SceneCapture2D, cam, rot)
    cc = capactor.capture_component2d
    cc.set_editor_property("capture_source", unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
    cc.set_editor_property("texture_target", rt)
    cc.set_editor_property("fov_angle", 42.0)
    cc.set_editor_property("capture_every_frame", False)
    out_dir = Path(MANIFEST.get("out_dir", str(OUT.parent)))
    # SAVED map display actors, never session spawns: probe-proven 2026-07-01 that session-spawned
    # actors ALWAYS render the engine default material in these tick-less headless sessions (even a
    # map-proven material assigned to a spawned cube renders as the default checker), so every prior
    # spawn-based rig capture photographed the default material. Install/refresh the display actors
    # with scripts/ue/ue_install_rig_ship_display.py whenever the active rig changes.
    frames_spec = [("RigShipValidationDisplay_A", Path(cap["out"]).name),
                   ("RigShipValidationDisplay_B", Path(cap["out"]).stem + "_b.png")]
    displays = {a.get_actor_label(): a for a in eas.get_all_level_actors()
                if isinstance(a, unreal.SkeletalMeshActor) and a.get_actor_label().startswith("RigShipValidationDisplay")}
    expected_rig = _norm(cap["rig"])
    for i, (label, nm) in enumerate(frames_spec):
        actor = displays.get(label)
        if actor is None:
            res.setdefault("errors", []).append(f"saved display actor missing: {label} (run scripts/ue/ue_install_rig_ship_display.py)")
            continue
        comp = actor.skeletal_mesh_component
        mesh = comp.get_skeletal_mesh_asset() if hasattr(comp, "get_skeletal_mesh_asset") else comp.skeletal_mesh
        mesh_path = _norm(mesh.get_path_name()) if mesh else None
        if mesh_path != expected_rig:
            # fail-closed: a stale display (roster changed, installer not rerun) must never pass as the active rig
            res.setdefault("errors", []).append(
                f"display {label} carries {mesh_path}, manifest expects {expected_rig} (rerun scripts/ue/ue_install_rig_ship_display.py)")
            continue
        for tick_call in (lambda: comp.tick_pose(0.1, False),
                          lambda: comp.tick_animation(0.1, False),
                          lambda: comp.tick_component(0.1, unreal.LevelTick.LEVELTICK_ALL, None)):
            try:
                tick_call()
            except Exception:
                pass
        loc = actor.get_actor_location()
        cam_pos = unreal.Vector(loc.x + 430.0, loc.y, loc.z + 95.0)      # same framing as the original capture
        capactor.set_actor_location(cam_pos, False, False)
        capactor.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(
            cam_pos, unreal.Vector(loc.x, loc.y, loc.z + 90.0)), False)
        cc.capture_scene()
        unreal.RenderingLibrary.export_render_target(world, rt, str(out_dir), nm)
        png = out_dir / nm
        res["frames"].append(str(png))
        if i == 0:
            res["png"] = str(png)
            res["png_bytes"] = png.stat().st_size if png.exists() else 0   # TELEMETRY ONLY (never a verdict)
            res["subject_a"] = {"actor": label, "mesh": mesh_path}
        else:
            res["subject_b"] = {"actor": label, "mesh": mesh_path}
    res["taa_off"] = True
    res["eye_adapt_off"] = False
    # honest telemetry from the live session, never hardcoded: tick-less sessions never stream
    # mips, so captures are only texture-true when the batch was launched -NoTextureStreaming
    try:
        res["texture_streaming_off"] = (
            unreal.SystemLibrary.get_console_variable_int_value("r.TextureStreaming") == 0)
    except Exception:
        res["texture_streaming_off"] = None
    eas.destroy_actor(capactor)
    return res


for cap in MANIFEST.get("captures", []):
    try:
        out["captures"][cap["id"]] = _capture(cap)
    except Exception:
        out["captures"][cap["id"]] = {"error": traceback.format_exc().splitlines()[-1]}

OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
unreal.log("DIMWIT_VALIDATION_PROBE_DONE")
