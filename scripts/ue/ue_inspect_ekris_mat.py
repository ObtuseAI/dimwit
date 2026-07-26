"""Quick inspector: dump ekris_mat parameter values to verify BaseColorTexture is wired."""
import unreal, json
from pathlib import Path

OUT = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/ekris_mat_inspect.json")
MAT = "/Game/Wanefall/Dimwit/CharactersRigged/ekris_mat"
VORLAX = "/Game/Wanefall/Dimwit/CharactersRigged/vorlax_mat"

def dump_mic(path):
    m = unreal.load_asset(path)
    if not m:
        return {"err": "not found"}
    if not isinstance(m, unreal.MaterialInstanceConstant):
        return {"err": f"not MIC: {type(m).__name__}"}
    par = m.get_editor_property("parent")
    return {
        "parent": par.get_path_name() if par else None,
        "textures": [(str(t.get_editor_property("parameter_info").get_editor_property("name")),
                      t.get_editor_property("parameter_value").get_path_name()
                      if t.get_editor_property("parameter_value") else None)
                     for t in m.get_editor_property("texture_parameter_values")],
        "scalars": [(str(s.get_editor_property("parameter_info").get_editor_property("name")),
                     float(s.get_editor_property("parameter_value")))
                    for s in m.get_editor_property("scalar_parameter_values")],
    }

out = {"ekris_mat": dump_mic(MAT), "vorlax_mat": dump_mic(VORLAX)}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
unreal.log("RM_INSPECT_DONE " + str(OUT))
