"""Apply the actual ekris_mat to the clean stage character + boost SkyLight.

ekris_mat = /Game/Wanefall/Dimwit/CharactersRigged/ekris_mat.ekris_mat
  → "silver armor + orange WANE accents from baked albedo"

UV mismatch makes most triangles sample dark areas. A boosted SkyLight (15.0)
provides ambient fill that washes dark UV areas to silver-grey while the correctly-
mapped orange accent triangles remain orange — matching the hi3d_02_ekris.png reference.

Run: paste into UE Python console or via Remote Python endpoint.
"""
import unreal, json, traceback
from pathlib import Path

MAP = "/Game/Wanefall/Maps/Wanefall_CleanStage_01"
EKRIS_MAT = "/Game/Wanefall/Dimwit/CharactersRigged/ekris_mat.ekris_mat"
OUT = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/clean_stage_ekris_mat_result.json")
out = {"ok": False, "log": []}

def log(msg):
    print(f"  [ekris_mat] {msg}")
    out["log"].append(msg)

try:
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)

    les.load_level(MAP)
    log("map loaded")

    # Load the actual ekris_mat
    mat = unreal.load_asset(EKRIS_MAT)
    if mat:
        log(f"ekris_mat loaded: {EKRIS_MAT}")
    else:
        log(f"WARNING: ekris_mat not found at {EKRIS_MAT} — will continue with fallback")

    world = ues.get_editor_world()
    actors = list(unreal.GameplayStatics.get_all_actors_of_class(
        world, unreal.Actor.static_class()))

    char_found = False
    for a in actors:
        try:
            lbl = a.get_actor_label()
        except Exception:
            lbl = "?"

        # Apply ekris_mat to the Ekris skeletal mesh actor
        if isinstance(a, unreal.SkeletalMeshActor) and "ekris" in lbl.lower():
            mesh_comp = a.get_component_by_class(unreal.SkeletalMeshComponent.static_class())
            if mesh_comp and mat:
                n_slots = max(1, mesh_comp.get_num_materials())
                for i in range(n_slots):
                    mesh_comp.set_material(i, mat)
                log(f"Applied ekris_mat to '{lbl}' ({n_slots} slot(s))")
                char_found = True
            elif mesh_comp:
                log(f"WARNING: ekris_mat not loaded, cannot apply to '{lbl}'")

        # Boost SkyLight: ambient fill compensates for UV-mismatch dark areas
        # 15.0 is bright enough to wash dark textures to silver-grey while
        # preserving orange accents from correctly-mapped UV areas
        if isinstance(a, unreal.SkyLight):
            try:
                a.light_component.set_intensity(15.0)
                log(f"SkyLight '{lbl}' intensity -> 15.0 (UV-mismatch ambient fill)")
            except Exception as e:
                log(f"SkyLight error: {e}")

        # Keep the floor hidden (was hidden in a prior script)
        if lbl == "Floor" and isinstance(a, unreal.StaticMeshActor):
            a.set_actor_hidden_in_game(True)
            log("Floor kept hidden_in_game=True")

    if not char_found:
        log("WARNING: No SkeletalMeshActor with 'ekris' label found — check actor labels in map")

    les.save_current_level()
    log("level saved")
    out["ok"] = True

except Exception:
    out["error"] = traceback.format_exc()

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
print(f"DIMWIT_EKRIS_MAT_DONE ok={out['ok']}")
unreal.log(f"DIMWIT_EKRIS_MAT_DONE ok={out['ok']}")
