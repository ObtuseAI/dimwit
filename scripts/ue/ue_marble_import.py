"""Dimwit Marble ingest — Stage 3 (UE 5.8 headless via Interchange).

Invoked by dimwit/pipelines/marble_ingest.py via:
    UnrealEditor-Cmd <uproject> -ExecutePythonScript="scripts/ue/ue_marble_import.py src=<glb> dest=/Game/... asset=<name>
        level=/Game/Maps/... result=<json> nanite=1 collision=complexassimple" -unattended -nosplash -nopause -stdout

Takes the cleaned/scaled/triangulated glTF the Blender stage produced (artifacts/marble_staging/<asset>.glb) and makes it
a usable WANEFALL environment:

  1. Interchange-import the GLB as a StaticMesh under <dest>.
  2. Read the SOURCE triangle count BEFORE enabling Nanite (the verified gotcha: get_num_triangles on a Nanite mesh
     returns the low-poly FALLBACK, not the source — so QA's V8 would be judged against the wrong number).
  3. Enable Nanite (+ a usable fallback %) so a 600k-1M-tri Marble world renders without melting the GPU.
  4. Force Collision Complexity = UseComplexAsSimple so the backdrop is solid/walkable (Marble gives no simple hulls).
  5. Build a neutral test map: the mesh at origin + a PlayerStart + DirectionalLight + SkyLight + a manual-exposure
     PostProcessVolume (so a dark Marble world isn't crushed to black, mirroring the per-camera exposure fix) +
     a GameModeBase override. Save the level.
  6. Write the proof JSON to <result> (artifacts/marble_ue_result.json). QA reads the FILE, never the exit code:
     source_tris / nanite_enabled / collision_complexity / level_saved / player_starts / level.

Everything is fail-soft: a missing sub-step is recorded (not crashed) so the pipeline's QA can judge honestly. A
validator may FAIL but NEVER silently PASS — if the import produced no StaticMesh, source_tris stays 0 and V8 fails.
"""
import json
import os
import sys

import unreal


# ---- argv parsing (key=val after the script path) ------------------------------------------------
def _args():
    out = {}
    for a in sys.argv:
        if "=" in a and not a.lower().endswith(".py"):
            k, _, v = a.partition("=")
            out[k.strip()] = v.strip()
    return out


ARGS = _args()
SRC = ARGS.get("src", "")                                   # staged GLB from the Blender stage
DEST = ARGS.get("dest", "/Game/Wanefall/Imported/Marble")   # content folder for the imported mesh
ASSET = ARGS.get("asset", "SM_Marble_Env")
LEVEL = ARGS.get("level", "/Game/Wanefall/Maps/Wanefall_Marble_Env")
RESULT_PATH = ARGS.get("result", "")
WANT_NANITE = ARGS.get("nanite", "1") not in ("0", "false", "False", "")
COLLISION = ARGS.get("collision", "complexassimple").lower()

if not RESULT_PATH:
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    RESULT_PATH = os.path.join(here, "artifacts", "marble_ue_result.json")

rec = {
    "src": SRC, "dest": DEST, "asset": ASSET, "level": LEVEL,
    "imported_path": None, "imported_object_paths": [],
    "source_tris": 0, "fallback_tris": 0,
    "nanite_requested": WANT_NANITE, "nanite_enabled": False,
    "collision_requested": COLLISION, "collision_complexity": None,
    "bbox_unreal": None,
    "lighting": {"directional": False, "sky": False, "ppv_manual_exposure": False, "game_mode": False},
    "actor_placed": False, "player_starts": 0,
    "level_saved": False, "warnings": [], "error": None,
}


def _find_static_mesh(imported_paths):
    """Return the imported StaticMesh. Interchange glTF can nest as <dest>/<Asset>/StaticMeshes/<Asset>, so trust the
    task's reported object paths first, then fall back to scanning the dest folder."""
    eal = unreal.EditorAssetLibrary
    # 1) whatever the import task reported
    for p in imported_paths or []:
        try:
            obj = eal.load_asset(p)
            if isinstance(obj, unreal.StaticMesh):
                return obj, p
        except Exception:
            pass
    # 2) scan the destination tree for the first StaticMesh
    try:
        for ap in eal.list_assets(DEST, recursive=True, include_folder=False):
            obj = eal.load_asset(ap)
            if isinstance(obj, unreal.StaticMesh):
                return obj, ap
    except Exception as e:
        rec["warnings"].append(f"dest scan failed: {e}")
    return None, None


def _import_glb():
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", SRC)
    task.set_editor_property("destination_path", DEST)
    task.set_editor_property("destination_name", ASSET)
    task.set_editor_property("automated", True)
    task.set_editor_property("save", True)
    task.set_editor_property("replace_existing", True)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    try:
        paths = list(task.get_editor_property("imported_object_paths"))
    except Exception:
        paths = []
    rec["imported_object_paths"] = [str(p) for p in paths]
    return paths


def _enable_nanite(sm):
    """Set Nanite enabled + a usable fallback %, then rebuild so the flag and fallback render data are real. Verify by
    reading the flag back (never trust the request — V8 wants the actual state)."""
    try:
        ns = sm.get_editor_property("nanite_settings")
        ns.set_editor_property("enabled", True)
        # A small fallback mesh keeps memory sane while still giving complex-collision something to trace against.
        for prop, val in (("fallback_percent_triangles", 1.0), ("fallback_relative_error", 0.0)):
            try:
                ns.set_editor_property(prop, val)
            except Exception:
                pass
        sm.set_editor_property("nanite_settings", ns)
    except Exception as e:
        rec["warnings"].append(f"nanite set failed: {e}")
        return False
    # Rebuild so the Nanite data is actually generated (not just flagged).
    try:
        ses = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
        ses.set_nanite_enabled(sm, True)   # no-op if unavailable; raises -> caught
    except Exception:
        pass
    try:
        unreal.EditorAssetLibrary.save_loaded_asset(sm)
    except Exception as e:
        rec["warnings"].append(f"save after nanite failed: {e}")
    # read back the truth
    try:
        return bool(sm.get_editor_property("nanite_settings").get_editor_property("enabled"))
    except Exception:
        return False


def _set_collision(sm):
    try:
        bs = sm.get_editor_property("body_setup")
        if not bs:
            # force-create a body setup by setting a collision complexity via the editor subsystem path
            rec["warnings"].append("no body_setup on imported mesh")
            return None
        bs.set_editor_property("collision_trace_flag",
                               unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
        unreal.EditorAssetLibrary.save_loaded_asset(sm)
        flag = bs.get_editor_property("collision_trace_flag")
        # Normalize to the string QA expects ("complex..." -> V9 passes).
        return "complexassimple" if flag == unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE else str(flag)
    except Exception as e:
        rec["warnings"].append(f"collision set failed: {e}")
        return None


def _neutral_ppv(eas):
    """Unbound PostProcessVolume with manual exposure locked to ~1.0 — a dark Marble world won't crush to black and a
    bright one won't blow out (same fix that rescued the dark carapace body)."""
    try:
        ppv = eas.spawn_actor_from_class(unreal.PostProcessVolume, unreal.Vector(0, 0, 0))
        ppv.set_editor_property("unbound", True)
        s = ppv.get_editor_property("settings")
        # Lock exposure neutral. Min==Max pins the auto-exposure to a constant; method=Manual makes it explicit.
        for prop, val in (
            ("override_auto_exposure_method", True),
            ("auto_exposure_method", unreal.AutoExposureMethod.AEM_MANUAL),
            ("override_auto_exposure_min_brightness", True),
            ("auto_exposure_min_brightness", 1.0),
            ("override_auto_exposure_max_brightness", True),
            ("auto_exposure_max_brightness", 1.0),
            ("override_auto_exposure_bias", True),
            ("auto_exposure_bias", 0.0),
        ):
            try:
                s.set_editor_property(prop, val)
            except Exception:
                pass
        ppv.set_editor_property("settings", s)
        return True
    except Exception as e:
        rec["warnings"].append(f"ppv failed: {e}")
        return False


def main():
    if not SRC or not os.path.exists(SRC):
        rec["error"] = f"staged GLB not found: {SRC}"
        return

    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

    # ---- import ------------------------------------------------------------------------------------
    paths = _import_glb()
    sm, ap = _find_static_mesh(paths)
    if not sm:
        rec["error"] = "Interchange import produced no StaticMesh (check the staged GLB)"
        return
    rec["imported_path"] = ap

    # ---- SOURCE tris BEFORE Nanite (gotcha: post-Nanite this returns the fallback) -----------------
    try:
        rec["source_tris"] = int(sm.get_num_triangles(0))
    except Exception as e:
        rec["warnings"].append(f"source tri read failed: {e}")
    try:
        b = sm.get_bounding_box()
        ext = b.max - b.min
        rec["bbox_unreal"] = [round(ext.x, 1), round(ext.y, 1), round(ext.z, 1)]
    except Exception:
        pass

    # ---- Nanite ------------------------------------------------------------------------------------
    if WANT_NANITE:
        rec["nanite_enabled"] = _enable_nanite(sm)
    # fallback tri count (informational; what complex-collision/non-Nanite fallback will trace)
    try:
        rec["fallback_tris"] = int(sm.get_num_triangles(0))
    except Exception:
        pass

    # ---- collision ---------------------------------------------------------------------------------
    if COLLISION.startswith("complex"):
        rec["collision_complexity"] = _set_collision(sm)

    # ---- test map ----------------------------------------------------------------------------------
    les.new_level(LEVEL)

    try:
        a = eas.spawn_actor_from_object(sm, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
        rec["actor_placed"] = a is not None
    except Exception as e:
        rec["warnings"].append(f"actor spawn failed: {e}")

    # lighting so the world is visible
    try:
        dl = eas.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0, 0, 2000),
                                        unreal.Rotator(-45, 25, 0))
        c = dl.get_component_by_class(unreal.DirectionalLightComponent)
        if c:
            c.set_intensity(3.0)
        rec["lighting"]["directional"] = True
    except Exception as e:
        rec["warnings"].append(f"dir light: {e}")
    try:
        sky = eas.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0, 0, 1500))
        sc = sky.get_component_by_class(unreal.SkyLightComponent)
        if sc:
            sc.set_intensity(1.0)
            try:
                sc.recapture_sky()
            except Exception:
                pass
        rec["lighting"]["sky"] = True
    except Exception as e:
        rec["warnings"].append(f"sky light: {e}")

    rec["lighting"]["ppv_manual_exposure"] = _neutral_ppv(eas)

    # PlayerStart so the test map is enterable; lift it above origin so a bottom-heavy Marble mesh doesn't bury it
    try:
        eas.spawn_actor_from_class(unreal.PlayerStart, unreal.Vector(0, 0, 200), unreal.Rotator(0, 0, 0))
        rec["player_starts"] = 1
    except Exception as e:
        rec["warnings"].append(f"player start: {e}")

    # GameModeBase override so PIE has a valid default game mode
    try:
        ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        world = ues.get_editor_world()
        ws = world.get_world_settings()
        ws.set_editor_property("default_game_mode", unreal.GameModeBase)
        rec["lighting"]["game_mode"] = True
    except Exception as e:
        rec["warnings"].append(f"game mode override: {e}")

    # ---- save --------------------------------------------------------------------------------------
    try:
        les.save_current_level()
        rec["level_saved"] = unreal.EditorAssetLibrary.does_asset_exist(LEVEL)
    except Exception as e:
        rec["error"] = f"save failed: {e}"

    unreal.log(f"DIMWIT_MARBLE_IMPORT_DONE asset={ASSET} source_tris={rec['source_tris']} "
               f"nanite={rec['nanite_enabled']} collision={rec['collision_complexity']} "
               f"starts={rec['player_starts']} saved={rec['level_saved']}")


try:
    main()
except Exception as e:
    rec["error"] = f"{type(e).__name__}: {e}"
    try:
        unreal.log_error(f"DIMWIT_MARBLE_IMPORT_FAIL {rec['error']}")
    except Exception:
        pass
finally:
    try:
        os.makedirs(os.path.dirname(RESULT_PATH), exist_ok=True)
        with open(RESULT_PATH, "w", encoding="utf-8") as f:
            json.dump(rec, f, indent=2)
    except Exception:
        pass
