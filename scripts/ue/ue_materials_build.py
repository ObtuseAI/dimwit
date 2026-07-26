"""Dimwit MATERIALS/SHADERS UE driver (canonical). Authors the WANE master shading layer:

  1) MF_Wane  — a Material *Function* at /Game/Wanefall/Dimwit/Materials that implements the WANE
     decay-force identity treatment:
        - de-chrome default (satin metallic, low) so armor reads as matter, not a chrome mirror,
        - a teal/blue energy SEAM emissive driven by a Fresnel * AO mask ("saturation = truth": the
          rim/cavity seams glow with the WANE energy color, in HDR-safe range ~1.0),
        - a saturation control on base color (decay desaturates; truth re-saturates).
     Exposed outputs: BaseColor, Metallic, Roughness, EmissiveColor.
  2) M_WaneSurface — a master Material at the same folder that calls MF_Wane and wires its outputs to
     the corresponding material properties, then compiles + saves.
  3) (optional) retarget character MICs MetallicFactor -> satin, when assets=... is supplied.

Honest, metric-based result -> artifacts/materials_build_result.json (verify via the FILE, not exit code).

Run headless:
  UnrealEditor-Cmd <uproject> -ExecutePythonScript="scripts/ue/ue_materials_build.py [seam_r=0.0 seam_g=0.8 seam_b=1.0 metallic=0.35 saturation=1.15 assets=SM_Char_02_ekris,SM_Char_01_Vorlax]"
"""
import unreal, json, sys, traceback
from pathlib import Path

ART = Path(r"C:/Users/developer/Documents/Dimwit/artifacts")
RESULT = ART / "materials_build_result.json"
MAT_DIR = "/Game/Wanefall/Dimwit/Materials"
CHARS = "/Game/Wanefall/Dimwit/Characters"

MF_NAME = "MF_Wane"
M_NAME = "M_WaneSurface"
MF_PATH = f"{MAT_DIR}/{MF_NAME}"
M_PATH = f"{MAT_DIR}/{M_NAME}"

tools = unreal.AssetToolsHelpers.get_asset_tools()
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary


def _argmap():
    return {a.split("=", 1)[0]: a.split("=", 1)[1] for a in sys.argv if "=" in a}


def _f(args, k, d):
    try:
        return float(args.get(k, d))
    except (TypeError, ValueError):
        return d


def build_mf(seam_rgb, metallic, saturation):
    """Create (or replace) MF_Wane. Returns a record of what was authored."""
    rec = {"path": MF_PATH, "ok": False, "expr": 0, "outputs": []}
    if eal.does_asset_exist(MF_PATH):
        eal.delete_asset(MF_PATH)
    mf = tools.create_asset(MF_NAME, MAT_DIR, unreal.MaterialFunction, unreal.MaterialFunctionFactoryNew())
    if not isinstance(mf, unreal.MaterialFunction):
        rec["error"] = "could not create MaterialFunction"
        return rec
    n = 0

    def add(cls, x, y):
        nonlocal n
        e = mel.create_material_expression_in_function(mf, cls, x, y)
        n += 1
        return e

    # --- inputs (so the function is reusable as a node) ---
    in_base = add(unreal.MaterialExpressionFunctionInput, -900, -200)
    in_base.set_editor_property("input_name", "BaseColor")
    in_base.set_editor_property("input_type", unreal.FunctionInputType.FUNCTION_INPUT_VECTOR3)
    # use_preview_value_as_default=True lets the input default cleanly when unconnected (so the master
    # compiles); per-asset material instances supply the real base color. Skip preview_value (Vector4f is
    # not positionally constructible in this UE python build, and the default is sufficient for a template).
    in_base.set_editor_property("use_preview_value_as_default", True)

    # --- saturation control on base color (decay desaturates; truth re-saturates) ---
    lum = add(unreal.MaterialExpressionDotProduct, -650, -120)
    lum_const = add(unreal.MaterialExpressionConstant3Vector, -850, -60)
    lum_const.set_editor_property("constant", unreal.LinearColor(0.299, 0.587, 0.114, 1.0))
    mel.connect_material_expressions(in_base, "", lum, "A")
    mel.connect_material_expressions(lum_const, "", lum, "B")
    sat = add(unreal.MaterialExpressionLinearInterpolate, -420, -200)  # lerp(lum, base, satAmt)
    sat_amt = add(unreal.MaterialExpressionConstant, -650, -20)
    sat_amt.set_editor_property("r", float(saturation))
    mel.connect_material_expressions(lum, "", sat, "A")
    mel.connect_material_expressions(in_base, "", sat, "B")
    mel.connect_material_expressions(sat_amt, "", sat, "Alpha")
    out_base = add(unreal.MaterialExpressionFunctionOutput, 250, -200)
    out_base.set_editor_property("output_name", "BaseColor")
    mel.connect_material_expressions(sat, "", out_base, "")
    rec["outputs"].append("BaseColor")

    # --- de-chrome: satin metallic constant ---
    met = add(unreal.MaterialExpressionConstant, -200, 20)
    met.set_editor_property("r", float(metallic))
    out_met = add(unreal.MaterialExpressionFunctionOutput, 250, 20)
    out_met.set_editor_property("output_name", "Metallic")
    mel.connect_material_expressions(met, "", out_met, "")
    rec["outputs"].append("Metallic")

    # --- roughness (satin, not glossy) ---
    rough = add(unreal.MaterialExpressionConstant, -200, 120)
    rough.set_editor_property("r", 0.55)
    out_rough = add(unreal.MaterialExpressionFunctionOutput, 250, 120)
    out_rough.set_editor_property("output_name", "Roughness")
    mel.connect_material_expressions(rough, "", out_rough, "")
    rec["outputs"].append("Roughness")

    # --- WANE energy SEAM emissive: Fresnel rim-glow * teal-blue color, HDR-safe (~1.0) ---
    # (Fresnel alone = reliable edge/silhouette energy seams; no lightmap-dependent AO node.)
    fres = add(unreal.MaterialExpressionFresnel, -650, 320)
    fres.set_editor_property("exponent", 4.0)
    fres.set_editor_property("base_reflect_fraction", 0.02)
    seam_col = add(unreal.MaterialExpressionConstant3Vector, -420, 480)
    seam_col.set_editor_property("constant",
                                 unreal.LinearColor(seam_rgb[0], seam_rgb[1], seam_rgb[2], 1.0))
    emissive = add(unreal.MaterialExpressionMultiply, -150, 400)
    mel.connect_material_expressions(fres, "", emissive, "A")
    mel.connect_material_expressions(seam_col, "", emissive, "B")
    out_em = add(unreal.MaterialExpressionFunctionOutput, 250, 400)
    out_em.set_editor_property("output_name", "EmissiveColor")
    mel.connect_material_expressions(emissive, "", out_em, "")
    rec["outputs"].append("EmissiveColor")

    eal.save_asset(MF_PATH)
    rec["expr"] = n
    rec["exists"] = eal.does_asset_exist(MF_PATH)
    rec["ok"] = rec["exists"] and len(rec["outputs"]) == 4
    return rec


def build_master():
    """Create (or replace) M_WaneSurface calling MF_Wane and wiring its outputs to properties."""
    rec = {"path": M_PATH, "ok": False, "connected": []}
    mf = unreal.load_asset(MF_PATH)
    if not isinstance(mf, unreal.MaterialFunction):
        rec["error"] = "MF_Wane missing; cannot build master"
        return rec
    if eal.does_asset_exist(M_PATH):
        eal.delete_asset(M_PATH)
    mat = tools.create_asset(M_NAME, MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())
    if not isinstance(mat, unreal.Material):
        rec["error"] = "could not create Material"
        return rec
    call = mel.create_material_expression(mat, unreal.MaterialExpressionMaterialFunctionCall, -350, 0)
    call.set_editor_property("material_function", mf)
    prop_map = [
        ("BaseColor", unreal.MaterialProperty.MP_BASE_COLOR),
        ("Metallic", unreal.MaterialProperty.MP_METALLIC),
        ("Roughness", unreal.MaterialProperty.MP_ROUGHNESS),
        ("EmissiveColor", unreal.MaterialProperty.MP_EMISSIVE_COLOR),
    ]
    for out_name, prop in prop_map:
        try:
            ok = mel.connect_material_property(call, out_name, prop)
            if ok:
                rec["connected"].append(out_name)
        except Exception as e:
            rec.setdefault("connect_err", {})[out_name] = str(e)
    try:
        mel.recompile_material(mat)
        rec["compiled"] = True
    except Exception as e:
        rec["compiled"] = False
        rec["compile_err"] = str(e)
    eal.save_asset(M_PATH)
    rec["exists"] = eal.does_asset_exist(M_PATH)
    rec["ok"] = rec["exists"] and len(rec["connected"]) == 4 and rec.get("compiled", False)
    return rec


def retreat_assets(asset_names, metallic):
    """Optional: satin the MetallicFactor on listed character MICs (consistent de-chrome)."""
    out = []
    for asset in asset_names:
        rec = {"asset": asset, "ok": False}
        mic_path = f"{CHARS}/{asset}/Materials/pbr_material"
        mic = unreal.load_asset(mic_path)
        if not isinstance(mic, unreal.MaterialInstanceConstant):
            rec["skip"] = "no MIC at " + mic_path
            out.append(rec)
            continue
        base = mic.get_base_material()
        applied = False
        if base:
            for nme in mel.get_scalar_parameter_names(base):
                if str(nme).lower() == "metallicfactor":
                    mel.set_material_instance_scalar_parameter_value(mic, str(nme), float(metallic))
                    rec["metallic_set"] = float(metallic)
                    applied = True
        try:
            mel.update_material_instance(mic)
        except Exception:
            pass
        eal.save_asset(mic_path)
        rec["ok"] = applied
        out.append(rec)
    return out


def main():
    args = _argmap()
    seam = (_f(args, "seam_r", 0.0), _f(args, "seam_g", 0.8), _f(args, "seam_b", 1.0))
    metallic = _f(args, "metallic", 0.35)
    saturation = _f(args, "saturation", 1.15)
    assets = [a for a in args.get("assets", "").split(",") if a.strip()]
    out = {"ok": False}
    try:
        if not eal.does_directory_exist(MAT_DIR):
            eal.make_directory(MAT_DIR)
        out["mf"] = build_mf(seam, metallic, saturation)
        out["master"] = build_master()
        out["retreated"] = retreat_assets(assets, metallic) if assets else []
        out["retreated_ok"] = sum(1 for r in out["retreated"] if r.get("ok"))
        out["retreated_total"] = len(out["retreated"])
        out["params"] = {"seam": seam, "metallic": metallic, "saturation": saturation}
        out["ok"] = out["mf"].get("ok") and out["master"].get("ok")
    except Exception:
        out["error"] = traceback.format_exc()
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    unreal.log("DIMWIT_MATERIALS_BUILD_DONE ok=" + str(out.get("ok")))


main()
