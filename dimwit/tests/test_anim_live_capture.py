from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from scripts.capture import anim_live_capture as capture


def test_launch_command_uses_arena_match_and_d_drive_ddc_flags():
    command = capture._launch_command()
    joined = " ".join(command)

    assert command[0].endswith("UnrealEditor.exe")
    assert command[1].endswith("WanefallGreybox.uproject")
    assert "/Game/Wanefall/Maps/Wanefall_Arena4v4_Prototype_01" in command[2]
    assert "WanefallMatchGameMode" in command[2]
    assert "-game" in command
    assert "-NoScreenMessages" in command
    assert "-DDC=InstalledNoZenLocalFallback" in command
    assert "-SharedDataCachePath=None" in command
    assert "-LocalDataCachePath=D:\\WanefallBuild\\DDC" in joined


def test_input_plan_deploys_before_drive_with_sendinput():
    plan = capture._input_plan(deploy_first=True)
    names = [step["name"] for step in plan]

    assert names.index("deploy_enter") < names.index("drive_forward")
    assert names.index("toggle_perspective") < names.index("drive_forward")
    assert plan[names.index("deploy_enter")]["method"] == "sendinput+postmessage"
    assert plan[names.index("toggle_perspective")]["method"] == "sendinput+postmessage"
    assert plan[names.index("drive_forward")]["method"] == "sendinput+postmessage"


def test_input_plan_can_skip_deploy_for_direct_match_map():
    plan = capture._input_plan(deploy_first=False)
    names = [step["name"] for step in plan]

    assert "deploy_enter" not in names
    assert "drive_forward" in names


def test_default_input_plan_skips_deploy_for_arena_match_runtime():
    names = [step["name"] for step in capture._input_plan()]

    assert "deploy_enter" not in names
    assert "toggle_perspective" in names
    assert "drive_forward" in names


def test_capture_backend_uses_printwindow_not_framebuffer():
    backend = capture._capture_backend()

    assert backend["tier"] == "printwindow"
    assert backend["proc"] == "UnrealEditor"
    assert backend["reason"] == "locked-desktop-safe"


def test_match_runtime_capture_is_not_character_optics_candidate_by_default():
    subject_type = capture._subject_type_for_capture(
        deploy_first=False,
        map_url="/Game/Wanefall/Maps/Wanefall_Arena4v4_Prototype_01?game=/Script/WanefallGreybox.WanefallMatchGameMode",
        toggle_perspective=False,
    )

    assert subject_type == "runtime_motion_candidate"


def test_focused_crop_is_not_ekris_or_orange_locked():
    source = Path(capture.__file__).read_text(encoding="utf-8").lower()

    assert "ekris" not in source
    assert "orange-detect" not in source
    assert "orange-pixel" not in source


def test_focused_crop_tightens_on_dark_third_person_character():
    from PIL import Image, ImageDraw
    import numpy as np

    tmp = Path(tempfile.mkdtemp(prefix="dimwit_anim_crop_"))
    src = tmp / "wide_runtime.png"
    dst = tmp / "focused.png"

    img = Image.new("RGB", (1280, 720), (176, 214, 214))
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, 1280, 155), fill=(37, 42, 50))
    draw.rectangle((30, 185, 360, 420), fill=(120, 65, 45))
    draw.text((35, 205), "DEBUG HUD TEXT SHOULD NOT DOMINATE", fill=(230, 230, 230))
    draw.rectangle((720, 210, 1040, 315), fill=(120, 190, 195))
    draw.ellipse((480, 260, 555, 335), fill=(16, 18, 22))
    draw.rectangle((495, 330, 545, 540), fill=(18, 19, 23))
    draw.rectangle((455, 345, 500, 520), fill=(20, 20, 24))
    draw.rectangle((540, 345, 585, 520), fill=(20, 20, 24))
    draw.rectangle((500, 540, 522, 685), fill=(17, 18, 22))
    draw.rectangle((524, 540, 548, 685), fill=(17, 18, 22))
    img.save(src)

    capture._write_focused_crop(str(src), str(dst), target_size=256)

    out = np.array(Image.open(dst).convert("RGB"), dtype=np.float32) / 255.0
    luminance = (0.2126 * out[:, :, 0]) + (0.7152 * out[:, :, 1]) + (0.0722 * out[:, :, 2])
    top_band_dark = float((luminance[:32, 80:176] < 0.16).mean())
    assert top_band_dark < 0.35


def test_focused_crop_prefers_center_player_over_left_neighbor_and_hud():
    from PIL import Image, ImageDraw
    import numpy as np

    tmp = Path(tempfile.mkdtemp(prefix="dimwit_anim_crop_player_"))
    src = tmp / "crowded_runtime.png"
    dst = tmp / "focused.png"

    img = Image.new("RGB", (1280, 720), (177, 216, 216))
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, 1280, 150), fill=(37, 42, 50))
    draw.rectangle((0, 585, 1280, 720), fill=(42, 46, 54))
    draw.text((20, 610), "HUD should not become the subject", fill=(235, 235, 235))
    draw.rectangle((170, 285, 330, 710), fill=(18, 19, 23))  # left neighbor, very dark and tall
    draw.ellipse((548, 245, 610, 310), fill=(191, 118, 96))
    draw.polygon([(520, 295), (640, 300), (690, 555), (468, 555)], fill=(212, 134, 112))
    draw.rectangle((545, 318, 610, 535), fill=(22, 22, 24))
    draw.rectangle((430, 350, 505, 535), fill=(210, 132, 111))
    draw.rectangle((655, 350, 745, 535), fill=(214, 137, 116))
    img.save(src)

    capture._write_focused_crop(str(src), str(dst), target_size=256)

    out = np.array(Image.open(dst).convert("RGB"), dtype=np.float32) / 255.0
    luminance = (0.2126 * out[:, :, 0]) + (0.7152 * out[:, :, 1]) + (0.0722 * out[:, :, 2])
    salmon = (out[:, :, 0] > 0.62) & (out[:, :, 1] > 0.30) & (out[:, :, 1] < 0.62) & (out[:, :, 2] < 0.56)
    center_salmon = float(salmon[:, 78:190].mean())
    left_dark_neighbor = float((luminance[:, :52] < 0.12).mean())
    bottom_text = float((luminance[218:, :] > 0.68).mean())

    assert center_salmon > 0.08
    assert left_dark_neighbor < 0.55
    assert bottom_text < 0.03


def _run() -> int:
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_") and callable(value)]
    failed = []
    for test in tests:
        try:
            test()
            print(f"  PASS  {test.__name__}")
        except Exception as exc:
            failed.append((test.__name__, exc))
            print(f"  FAIL  {test.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - len(failed)}/{len(tests)} passed")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(_run())
