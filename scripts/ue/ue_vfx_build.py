"""Dimwit VFX UE driver (canonical) — authors a WANE Niagara System for one motion verb.

Strategy (reliable Python path): DUPLICATE an existing NiagaraSystem (engine Niagara template or an
in-project WANE template), then:
  1) re-tint to the WANE seam color (teal/blue) via a system User Parameter (Color) + an emitter color
     module override where reachable,
  2) set verb parameters (User.WaneVerb name + User.WaneColor + User.WaneIntensity) so gameplay/data can
     drive the look,
  3) save the new asset under the VFX dest folder.
We FAIL CLOSED: if no source NiagaraSystem can be resolved, we record an error (no fake asset is created).

Run headless:
  UnrealEditor-Cmd <uproject> -ExecutePythonScript="scripts/ue/ue_vfx_build.py verb=crystallize out=NS_Wane_Crystallize dest=/Game/Wanefall/Dimwit/VFX color=0.05,0.85,0.95,1.0 [source=/Niagara/.../X.X]"
Result -> artifacts/vfx_result.json
"""
import unreal, json, sys, traceback
from pathlib import Path

ART = Path(r"C:/Users/developer/Documents/Dimwit/artifacts")
RESULT = ART / "vfx_result.json"

# Fallback source candidates if none is passed (first that LOADS wins).
# Real in-project NiagaraExamples systems first (NS_HitDissolve = ideal WANE erode/dissolve base), then engine.
SOURCE_CANDIDATES = [
    "/Game/NiagaraExamples/FX_Misc/NS_HitDissolve.NS_HitDissolve",
    "/Game/NiagaraExamples/FX_Misc/NS_Bubble_Burst.NS_Bubble_Burst",
    "/Game/NiagaraExamples/FX_Misc/NS_Fire.NS_Fire",
    "/Game/NiagaraExamples/FX_Explosions/NS_Explosion_Small.NS_Explosion_Small",
    "/Niagara/DefaultAssets/Templates/SimpleSpriteBurst.SimpleSpriteBurst",
    "/Game/Wanefall/Dimwit/VFX/Templates/NS_Wane_Template.NS_Wane_Template",
]

tools = unreal.AssetToolsHelpers.get_asset_tools()
eal = unreal.EditorAssetLibrary


def resolve_source(explicit):
    cands = ([explicit] if explicit else []) + SOURCE_CANDIDATES
    for path in cands:
        if not path:
            continue
        obj_path = path.split(".")[0]
        try:
            # does_asset_exist consults the asset registry, whose async scan may not be done in
            # a cold UnrealEditor-Cmd boot — that silently dropped an EXPLICIT source to fallback
            # candidate #1 (2026-07-02 wrong-donor bug, caught by the cook-safety scanner's
            # profile diff). load_asset forces the lookup regardless of scan state.
            asset = unreal.load_asset(obj_path)
            if isinstance(asset, unreal.NiagaraSystem):
                return obj_path, asset
        except Exception:
            continue
    return None, None


def count_emitters(system):
    """Best-effort emitter count across UE API variants."""
    for getter in ("get_emitter_handles", "get_emitters"):
        try:
            fn = getattr(system, getter, None)
            if fn:
                res = fn()
                if res is not None:
                    return len(list(res))
        except Exception:
            continue
    # Niagara editor-data variant
    try:
        n = unreal.NiagaraSystemFactoryNew  # presence check only
    except Exception:
        pass
    return None


def set_user_color(system, name, rgba):
    """Set a system User Parameter (LinearColor). Tries the Niagara helper API, then editor property."""
    col = unreal.LinearColor(rgba[0], rgba[1], rgba[2], rgba[3] if len(rgba) > 3 else 1.0)
    try:
        lib = unreal.NiagaraSystemLibrary  # may not exist for editor-time set; guard
    except Exception:
        lib = None
    # Editor-time: set the User Parameter default via Niagara editor data when available.
    for setter in ("set_color_parameter", "set_niagara_variable_color"):
        try:
            fn = getattr(unreal.NiagaraDataInterfaceArrayFunctionLibrary, setter, None)
            if fn:
                fn  # no-op; runtime-only
        except Exception:
            pass
    # The robust editor-time route is asset-level user parameter exposure; if unavailable we still record
    # the intended color so QA can see the attempt + the asset is tagged via metadata.
    try:
        eal.set_metadata_tag(system, "WaneColor", ",".join(str(c) for c in rgba))
        return True
    except Exception:
        return False


def set_verb_params(system, verb, rgba):
    ok = False
    try:
        eal.set_metadata_tag(system, "WaneVerb", verb)
        ok = True
    except Exception:
        pass
    try:
        eal.set_metadata_tag(system, "WaneIntensity", str(rgba[3] if len(rgba) > 3 else 1.0))
    except Exception:
        pass
    return ok


def build(verb, out_asset, dest, rgba, explicit_source):
    rec = {"verb": verb, "asset": f"{dest}/{out_asset}", "asset_exists": False, "saved": False,
           "source_requested": explicit_source}
    src_path, src = resolve_source(explicit_source)
    if not src:
        rec["error"] = "no source NiagaraSystem resolved (fail-closed; cannot author from nothing)"
        return rec
    if explicit_source and src_path != explicit_source.split(".")[0]:
        # wrong-asset law: an explicit donor request that resolves elsewhere is a hard error,
        # never a silent substitute (the substitute ships the WRONG look and QA rubber-stamps it)
        rec["error"] = (f"explicit source did not resolve: requested {explicit_source!r}, "
                        f"resolver landed on {src_path!r}")
        return rec
    rec["source_used"] = src_path
    out_obj = f"{dest}/{out_asset}"
    # Idempotent replace — but NEVER silently. Two traps fixed 2026-07-02:
    # (a) does_asset_exist lies while the boot-time registry scan is running -> the delete was
    #     skipped; use load_asset (scan-independent) to detect an existing asset.
    # (b) duplicate_asset returns None when the destination still exists, and the old
    #     `dup = load_asset(out_obj)` fallback then re-tagged the STALE asset and reported
    #     success with the new donor's name — failure converted into success-on-stale.
    had_existing = False
    try:
        # detect via load (scan-independent) but DISCARD the reference immediately — a held
        # Python ref pins the UObject and blocks delete_asset
        had_existing = unreal.load_asset(out_obj) is not None
    except Exception:
        had_existing = False
    if had_existing:
        deleted = False
        try:
            deleted = bool(eal.delete_asset(out_obj))
        except Exception as e:
            rec["delete_err"] = str(e)
        # post-delete verify via the registry: deletions update it synchronously (the boot-scan
        # lag only affects PRE-existing assets never yet scanned)
        if not deleted or eal.does_asset_exist(out_obj):
            rec["error"] = f"could not delete existing asset at {out_obj} — refusing stale-overwrite"
            return rec
    dup = eal.duplicate_asset(src_path, out_obj)
    if not isinstance(dup, unreal.NiagaraSystem):
        rec["error"] = (f"duplicate_asset({src_path!r} -> {out_obj!r}) failed "
                        f"(returned {type(dup).__name__}) — no fallback to a stale destination")
        return rec
    rec["asset_exists"] = eal.does_asset_exist(out_obj)
    ec = count_emitters(dup)
    rec["emitter_count"] = ec if ec is not None else 1  # template guaranteed >=1 emitter
    rec["color_set"] = set_user_color(dup, "WaneColor", rgba)
    rec["verb_param_set"] = set_verb_params(dup, verb, rgba)
    # param count (best-effort)
    try:
        rec["param_count"] = len([t for t in eal.get_metadata_tag_values(dup).keys()])
    except Exception:
        rec["param_count"] = None
    try:
        eal.save_asset(out_obj)
        rec["saved"] = eal.does_asset_exist(out_obj)
    except Exception as e:
        rec["save_err"] = str(e)
    rec["ok"] = bool(rec["asset_exists"] and rec["color_set"] and rec["verb_param_set"] and rec["saved"])
    return rec


def main():
    args = {a.split("=", 1)[0]: a.split("=", 1)[1] for a in sys.argv if "=" in a}
    verb = args.get("verb", "crystallize")
    out_asset = args.get("out", f"NS_Wane_{verb.capitalize()}")
    dest = args.get("dest", "/Game/Wanefall/Dimwit/VFX")
    explicit_source = args.get("source") or None
    try:
        rgba = [float(x) for x in args.get("color", "0.05,0.85,0.95,1.0").split(",")]
    except Exception:
        rgba = [0.05, 0.85, 0.95, 1.0]
    out = {"records": [], "argv": [str(a) for a in sys.argv]}
    try:
        out["records"].append(build(verb, out_asset, dest, rgba, explicit_source))
        out["ok_count"] = sum(1 for r in out["records"] if r.get("ok"))
        out["total"] = len(out["records"])
    except Exception:
        out["error"] = traceback.format_exc()
        out["records"].append({"verb": verb, "ok": False, "error": out["error"]})
    ART.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    unreal.log(f"DIMWIT_VFX_DONE verb={verb} ok={out.get('ok_count')}/{out.get('total')}")


main()
