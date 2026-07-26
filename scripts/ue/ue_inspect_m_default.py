"""Inspect the glTF M_Default master material to find its actual exposed parameter names.
Also checks MI_Default_Opaque and the pbr_material to compare parameter lists."""
import unreal, json
from pathlib import Path

OUT = Path(r"C:/Users/developer/Documents/Dimwit/artifacts/m_default_params.json")
mel = unreal.MaterialEditingLibrary

def dump_params(path):
    m = unreal.load_asset(path)
    if not m:
        return {"err": f"not found: {path}"}
    rec = {"class": type(m).__name__, "path": m.get_path_name()}
    try:
        rec["texture_params"] = [str(n) for n in mel.get_texture_parameter_names(m)]
        rec["scalar_params"] = [str(n) for n in mel.get_scalar_parameter_names(m)]
        rec["vector_params"] = [str(n) for n in mel.get_vector_parameter_names(m)]
    except Exception as e:
        rec["err"] = str(e)
    return rec

paths = {
    "M_Default":         "/InterchangeAssets/gltf/M_Default",
    "MI_Default_Opaque": "/InterchangeAssets/gltf/MaterialInstances/MI_Default_Opaque",
    "ekris_mat":         "/Game/Wanefall/Dimwit/CharactersRigged/ekris_mat",
    "pbr_material":      "/Game/Wanefall/Dimwit/CharactersRigged/pbr_material",
}

out = {k: dump_params(v) for k, v in paths.items()}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
unreal.log("RM_M_DEFAULT_INSPECT_DONE " + str(OUT))
