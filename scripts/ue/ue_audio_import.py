"""UE 5.8 headless driver — import WANEFALL "Weaponized Banter" WAVs as SoundWaves + optional MetaSound.

Invoked by dimwit/pipelines/audio.py via:
    UnrealEditor-Cmd.exe <uproject> -ExecutePythonScript="scripts/ue/ue_audio_import.py manifest=<path> dest=/Game/... metasound=1"
        -unattended -nosplash -nopause -stdout

Contract: VERIFY VIA THE RESULT FILE, not the exit code. Writes artifacts/audio_import_result.json:
    {"imported": <int>, "records": [{"wav","soundwave","ok"}...], "metasound": <path|null>, "error": <str|null>}

`import unreal` lives inside main() so this file is import-safe / lintable without the engine present.
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "artifacts"
RESULT = ART / "audio_import_result.json"


def parse_args(argv):
    kv = {}
    for tok in argv:
        if "=" in tok:
            k, v = tok.split("=", 1)
            kv[k.strip()] = v.strip()
    return kv


def write_result(rec):
    ART.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(rec, indent=2), encoding="utf-8")


def main():
    args = parse_args(sys.argv[1:])
    manifest = args.get("manifest", "")
    dest = args.get("dest", "/Game/Wanefall/Dimwit/Audio")
    make_metasound = args.get("metasound", "1") == "1"

    rec = {"imported": 0, "records": [], "metasound": None, "error": None, "dest": dest}
    try:
        import unreal  # noqa: PLC0415 — heavy import, engine-only, kept inside main()

        if not manifest or not Path(manifest).exists():
            rec["error"] = f"manifest missing: {manifest}"
            write_result(rec)
            return
        wavs = json.loads(Path(manifest).read_text(encoding="utf-8")).get("wavs", [])
        if not wavs:
            rec["error"] = "manifest contained no wavs"
            write_result(rec)
            return

        asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
        if not unreal.EditorAssetLibrary.does_directory_exist(dest):
            unreal.EditorAssetLibrary.make_directory(dest)

        # Build one AssetImportTask per WAV -> SoundWave.
        tasks = []
        planned = []
        for wav in wavs:
            wp = Path(wav)
            if not wp.exists():
                rec["records"].append({"wav": wav, "soundwave": None, "ok": False,
                                       "detail": "wav not found on disk"})
                continue
            t = unreal.AssetImportTask()
            t.filename = str(wp)
            t.destination_path = dest
            t.automated = True
            t.replace_existing = True
            t.save = True
            tasks.append(t)
            planned.append((wav, wp.stem))

        if tasks:
            asset_tools.import_asset_tasks(tasks)

        # Verify each expected SoundWave actually exists in the content browser.
        sound_paths = []
        for wav, stem in planned:
            asset_path = f"{dest}/{stem}"
            ok = unreal.EditorAssetLibrary.does_asset_exist(asset_path)
            if ok:
                rec["imported"] += 1
                sound_paths.append(asset_path)
            rec["records"].append({"wav": wav, "soundwave": asset_path, "ok": bool(ok)})

        # Optional MetaSound source scaffold (best-effort; engine plugin must be enabled).
        if make_metasound and sound_paths:
            rec["metasound"] = build_metasound(unreal, asset_tools, dest, sound_paths)

    except Exception as e:  # noqa: BLE001 — always emit a result file so QA can read the truth
        rec["error"] = f"{e}: {traceback.format_exc()[-800:]}"

    write_result(rec)


def build_metasound(unreal, asset_tools, dest, sound_paths):
    """Scaffold a MetaSoundSource asset. Returns its path or None.

    TODO: author the actual graph (random-selector node over the SoundWaves, output wiring,
    trigger/param inputs). Here we only create the asset shell when the factory is available.
    """
    try:
        factory_cls = getattr(unreal, "MetaSoundSourceFactory", None) \
            or getattr(unreal, "MetaSoundFactory", None)
        if factory_cls is None:
            return None
        ms_name = "MS_WeaponizedBanter"
        ms_path = f"{dest}/{ms_name}"
        if unreal.EditorAssetLibrary.does_asset_exist(ms_path):
            return ms_path
        factory = factory_cls()
        asset = asset_tools.create_asset(ms_name, dest, None, factory)
        if asset is not None:
            unreal.EditorAssetLibrary.save_asset(ms_path)
            return ms_path
    except Exception:
        return None
    return None


if os.environ.get("DIMWIT_AUDIO_DRIVER_SELFTEST") == "1":
    # Allows the integrator to syntax-check arg parsing without the engine.
    print(json.dumps(parse_args(sys.argv[1:])))
else:
    main()
