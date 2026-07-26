"""Regenerate the SYNTHETIC optics goldens from the real known-good capture (H1B2).

Ground truth by construction: each bad golden is the known-good render pushed through one
production regression class, so its expected verdict is unambiguous — unlike borderline real
captures (see manifest notes on bad_e0_emissive_washed), which flip judges and destabilize
calibration. Run from the repo root: python dimwit/goldens/optics/make_synthetic_goldens.py
"""
import numpy as np
from PIL import Image
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "good_rig_ship_production.png"


def _hsv(im):
    return np.asarray(im.convert("HSV"), dtype=np.float32)


def _save(hsv_arr, path):
    Image.fromarray(hsv_arr.clip(0, 255).astype(np.uint8), "HSV").convert("RGB").save(path)
    print("wrote", path.name)


def main():
    base = _hsv(Image.open(SRC))

    # PASS: mild exposure lift — same material identity, seams and saturation intact.
    lift = base.copy()
    lift[..., 2] = np.clip(lift[..., 2] * 1.12, 0, 255)
    _save(lift, HERE / "good_exposure_lift.png")

    # FAIL: flat-silver desaturation (the classic washed-material regression).
    desat = base.copy()
    desat[..., 1] = desat[..., 1] * 0.12
    _save(desat, HERE / "bad_desaturated_silver.png")

    # FAIL: value flattened toward bright + softened saturation (emissive/glow washout class):
    # dark seams collapse toward the plate brightness, exactly what killed panel articulation.
    flat = base.copy()
    v = flat[..., 2] / 255.0
    flat[..., 2] = (0.85 - (0.85 - v) * 0.35) * 255.0
    flat[..., 1] = flat[..., 1] * 0.6
    _save(flat, HERE / "bad_value_flattened.png")


if __name__ == "__main__":
    main()
