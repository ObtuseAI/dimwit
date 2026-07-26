"""scripts/ue/ue_reskin_materials.py — copy each certified rig's material onto its *_ReskinManny mesh.

The reskin is the SAME geometry with the SAME UVs as the certified SM_Char_0X_*_Rig, so the rig's UV-matched
material maps 1:1. (At runtime WanefallPrototypeCharacter's ApplySpeciesProfile() overrides zythan's slot with
the readable suit M_WaneZythan_SourceReadable for player-camera optics; this asset material is the editor/thumbnail
and fallback look.) Run headless (no RHI needed).
"""
import unreal, traceback
BASE = "/Game/Wanefall/Dimwit/CharactersRigged"
MAP = {
    "Zythan": "SM_Char_03_zythan_Rig",   # -> M_ZythanRigShip
    "Qorin":  "SM_Char_04_qorin_Rig",
    "Therak": "SM_Char_05_therak_Rig",
    "Ullio":  "SM_Char_06_ullio_Rig",
    "Kelous": "SM_Char_07_kelous_Rig",
    "Nexor":  "SM_Char_08_nexor_Rig",
}
for char, src in MAP.items():
    try:
        src_asset = unreal.load_asset(BASE + "/" + src)
        tgt = unreal.load_asset(BASE + "/" + char + "_ReskinManny")
        if not src_asset or not tgt:
            unreal.log_warning("RESKIN_MAT [%s] load fail" % char); continue
        src_mats = src_asset.get_editor_property("materials")
        tgt_mats = tgt.get_editor_property("materials")
        new_mats = []
        for i in range(len(tgt_mats)):
            si = min(i, len(src_mats)-1)
            sm = tgt_mats[i]
            if len(src_mats) > 0:
                sm.material_interface = src_mats[si].material_interface
                sm.material_slot_name = src_mats[si].material_slot_name
            new_mats.append(sm)
        tgt.set_editor_property("materials", new_mats)
        unreal.EditorAssetLibrary.save_asset(BASE + "/" + char + "_ReskinManny", only_if_is_dirty=False)
        chk = unreal.load_asset(BASE + "/" + char + "_ReskinManny").get_editor_property("materials")
        unreal.log("RESKIN_MAT [%s] -> %s" % (char, [m.material_interface.get_name() if m.material_interface else None for m in chk]))
    except Exception:
        unreal.log_error("RESKIN_MAT [%s] %s" % (char, traceback.format_exc()))
