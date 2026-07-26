"""Audit the clean stage actors and dump their types + available attributes for diagnosis."""
import unreal, json
from pathlib import Path

MAP = "/Game/Wanefall/Maps/Wanefall_CleanStage_01"
OUT = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/clean_stage_audit.json")

les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
les.load_level(MAP)
world = ues.get_editor_world()
actors = list(unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor.static_class()))

result = []
for a in actors:
    try:
        lbl = a.get_actor_label()
    except Exception:
        lbl = "?"
    info = {"label": lbl, "class": type(a).__name__, "loc": str(a.get_actor_location())}
    # Try to find the light component
    for attr in ["light_component", "sky_light_component", "directional_light_component",
                 "point_light_component", "spot_light_component"]:
        if hasattr(a, attr):
            comp = getattr(a, attr, None)
            if comp is not None:
                info["light_attr"] = attr
                info["light_type"] = type(comp).__name__
                try:
                    info["intensity"] = comp.get_editor_property("intensity")
                except Exception:
                    info["intensity"] = "?"
                break
    # Try get_component_by_class for common light components
    for ctype in [unreal.SkyLightComponent, unreal.DirectionalLightComponent,
                  unreal.PointLightComponent, unreal.SpotLightComponent]:
        try:
            comp = a.get_component_by_class(ctype)
            if comp:
                info["component_by_class"] = type(comp).__name__
                try:
                    info["comp_intensity"] = comp.get_editor_property("intensity")
                except Exception:
                    info["comp_intensity"] = "?"
                break
        except Exception:
            pass
    result.append(info)

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
print(f"DIMWIT_AUDIT_DONE: {len(result)} actors")
unreal.log(f"DIMWIT_AUDIT_DONE: {len(result)} actors")
