"""AUDIO_FOUNDATION_V1 leg 1 — author the UE USoundSubmix bus graph (operator UE session).

Headless editor asset op (NO cook, NO gameplay). Reads the bus manifest, creates one USoundSubmix
asset per declared bus under /Game/Wanefall/Dimwit/Audio/Submixes, wires each child's parent to
Master, saves them (capture-law: saved content), and writes artifacts/audio/bus_install_result.json
which the `audio_bus_submix_assets_present` gate reads (absent => BLOCKED).

Run (operator, from the Dimwit dir; batch with the leg-5 foreground session):
  "C:/UE_5.8/Engine/Binaries/Win64/UnrealEditor-Cmd.exe" \
     "C:/Users/developer/Documents/Unreal Projects/WanefallGreybox/WanefallGreybox.uproject" \
     -ExecutePythonScript="C:/Users/developer/Documents/Dimwit/scripts/ue/ue_audio_bus_install.py" \
     -unattended -nosplash -nopause -stdout

Self-contained: stdlib + `unreal` only (runs inside the editor interpreter; does not import dimwit).
"""
import json
import os

import unreal  # noqa: F401 — provided by the UE python interpreter

MANIFEST = r"C:/Users/developer/Documents/Unreal Projects/WanefallGreybox/Config/WANEFALL_Audio/bus_architecture.json"
RESULT = r"C:/Users/developer/Documents/Dimwit/artifacts/audio/bus_install_result.json"
DEST = "/Game/Wanefall/Dimwit/Audio/Submixes"


def _load_manifest():
    with open(MANIFEST, "r", encoding="utf-8") as f:
        return json.load(f)


def _asset_name(bus):
    return "SM_" + bus


def _create_or_load(bus):
    path = DEST + "/" + _asset_name(bus)
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        return unreal.EditorAssetLibrary.load_asset(path), path
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    factory = unreal.SoundSubmixFactory()
    asset = tools.create_asset(_asset_name(bus), DEST, unreal.SoundSubmix, factory)
    return asset, path


def main():
    manifest = _load_manifest()
    buses = manifest.get("buses") or {}
    unreal.EditorAssetLibrary.make_directory(DEST)

    created = {}
    # first pass: create/load every submix
    for bus in buses:
        asset, path = _create_or_load(bus)
        created[bus] = {"asset": asset, "path": path}

    # second pass: wire parents (child -> Master), then save
    master = created.get("Master", {}).get("asset")
    present = []
    for bus, rec in created.items():
        asset = rec["asset"]
        if asset is None:
            continue
        parent_name = (buses.get(bus) or {}).get("parent")
        if parent_name and parent_name in created and created[parent_name]["asset"] is not None:
            try:
                asset.set_editor_property("parent_submix", created[parent_name]["asset"])
            except Exception as e:
                unreal.log_warning("[AudioBus] parent wire failed for %s: %s" % (bus, e))
        unreal.EditorAssetLibrary.save_loaded_asset(asset)
        present.append(bus)

    out = {
        "dest": DEST,
        "submixes_present": sorted(present),
        "paths": {b: created[b]["path"] for b in created},
        "master_parent_is_root": True if master is not None else False,
    }
    os.makedirs(os.path.dirname(RESULT), exist_ok=True)
    with open(RESULT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    unreal.log("[AudioBus] wrote %s (%d submixes)" % (RESULT, len(present)))


main()
