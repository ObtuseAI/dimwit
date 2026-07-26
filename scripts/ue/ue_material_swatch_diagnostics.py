"""Render WANE material swatches in ModeShell lighting to isolate white-material root cause."""
import json
import traceback
from pathlib import Path

import unreal


ROOT = Path(r"C:/Users/developer/Documents/Dimwit")
OUT_DIR = ROOT / "artifacts" / "material_swatch_diagnostics"
OUT = OUT_DIR / "swatches.json"
PNG = OUT_DIR / "swatches.png"
PROJECT_MAP = "/Game/Wanefall/Maps/Wanefall_ModeShell_Prototype_01"
SWATCHES = [
    ("dark_body_4", "/Game/Wanefall/Materials/M_WaneEnemyDarkBody4"),
    ("dark_body_1", "/Game/Wanefall/Materials/M_WaneEnemyDarkBody"),
    ("wane_surface", "/Game/Wanefall/Dimwit/Materials/M_WaneSurface"),
    ("kit_lit", "/Game/Wanefall/Dimwit/MapKit/M_KitLit"),
    ("rig_pbr", "/Game/Wanefall/Dimwit/CharactersRigged/pbr_material"),
]


def path_name(obj):
    try:
        return obj.get_path_name() if obj else None
    except Exception:
        return None


def flush_compilation(result):
    rec = {"attempted": True}
    try:
        manager = unreal.AssetCompilingManager.get()
        manager.finish_all_compilation()
        rec["asset_compiling_manager"] = "finish_all_compilation"
    except Exception as exc:
        rec["asset_compiling_manager_error"] = str(exc)
    try:
        unreal.SystemLibrary.execute_console_command(None, "r.ShaderPipelineCache.SaveUserCache 1")
        rec["shader_cache_save_command"] = True
    except Exception as exc:
        rec["shader_cache_save_error"] = str(exc)
    result["compile_flush"] = rec


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    result = {"ok": False, "map": PROJECT_MAP, "png": str(PNG), "swatches": []}
    spawned = []
    try:
        unreal.EditorLoadingAndSavingUtils.load_map(PROJECT_MAP)
        world = unreal.EditorLevelLibrary.get_editor_world()
        cube = unreal.load_asset("/Engine/BasicShapes/Cube")
        base = unreal.Vector(0, 0, 120)
        for actor in unreal.EditorLevelLibrary.get_all_level_actors():
            if isinstance(actor, unreal.PlayerStart):
                loc = actor.get_actor_location()
                base = unreal.Vector(loc.x, loc.y, loc.z + 120)
                break

        for idx, (label, mat_path) in enumerate(SWATCHES):
            mat = unreal.load_asset(mat_path)
            y = (idx - (len(SWATCHES) - 1) / 2.0) * 135.0
            loc = unreal.Vector(base.x, base.y + y, base.z)
            actor = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, loc)
            spawned.append(actor)
            actor.set_actor_label(f"MaterialSwatch_{label}")
            comp = actor.static_mesh_component
            comp.set_static_mesh(cube)
            comp.set_world_scale3d(unreal.Vector(0.8, 0.8, 1.4))
            if mat:
                comp.set_material(0, mat)
            result["swatches"].append({
                "label": label,
                "material": mat_path,
                "loaded": bool(mat),
                "material_path": path_name(mat),
                "location": {"x": loc.x, "y": loc.y, "z": loc.z},
            })

        flush_compilation(result)
        cam = unreal.Vector(base.x + 470.0, base.y, base.z + 55.0)
        rot = unreal.MathLibrary.find_look_at_rotation(cam, unreal.Vector(base.x, base.y, base.z + 15.0))
        capactor = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.SceneCapture2D, cam, rot)
        spawned.append(capactor)
        rt = unreal.RenderingLibrary.create_render_target2d(world, 1400, 700, unreal.TextureRenderTargetFormat.RTF_RGBA8)
        cc = capactor.capture_component2d
        cc.set_editor_property("capture_source", unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
        cc.set_editor_property("texture_target", rt)
        cc.set_editor_property("fov_angle", 45.0)
        cc.set_editor_property("capture_every_frame", False)
        cc.capture_scene()
        unreal.RenderingLibrary.export_render_target(world, rt, str(OUT_DIR), PNG.name)
        result["ok"] = PNG.exists() and PNG.stat().st_size > 0
        result["png_bytes"] = PNG.stat().st_size if PNG.exists() else 0
    except Exception:
        result["error"] = traceback.format_exc()
    finally:
        for actor in reversed(spawned):
            try:
                unreal.EditorLevelLibrary.destroy_actor(actor)
            except Exception:
                pass
    OUT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"DIMWIT_MATERIAL_SWATCH_DIAGNOSTICS ok={result['ok']} png={PNG}")


main()
