"""One-shot capture diagnostic: list windows + rects, grab the whole primary monitor, and report mean brightness
of the game-window sub-region so we know if the SCREEN is white or the capture is mis-targeted."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dimwit.desktop_eyes import DesktopEyes
import mss, mss.tools
from PIL import Image
import numpy as np

eyes = DesktopEyes()
out = ROOT / "artifacts" / "baseline"
out.mkdir(parents=True, exist_ok=True)

wins = [w for w in eyes.list_windows() if "wanefall" in w["title"].lower() or "unreal" in w["title"].lower()]
print("GAME/UE WINDOWS:")
for w in wins:
    print(f"  {w['title']!r} left={w['left']} top={w['top']} w={w['width']} h={w['height']} active={w['active']} min={w['minimized']}")

# full primary monitor
full = out / "fullscreen.png"
with mss.MSS() as sct:
    mon = sct.monitors[1]
    print(f"MONITOR[1] = {mon}")
    img = sct.grab(mon)
    mss.tools.to_png(img.rgb, img.size, output=str(full))
arr = np.asarray(Image.open(full).convert("RGB"))
print(f"FULLSCREEN saved {full} mean_brightness={arr.mean():.1f}")

w = eyes.find_window("WanefallGreybox")
if w:
    print(f"find_window WanefallGreybox -> left={w['left']} top={w['top']} w={w['width']} h={w['height']}")
