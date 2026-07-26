"""Generate InstantMesh-compatible 6 views: my working Zero123++ load + InstantMesh's custom white-bg UNet."""
import sys, torch
from pathlib import Path
from PIL import Image
from diffusers import DiffusionPipeline, EulerAncestralDiscreteScheduler
from huggingface_hub import hf_hub_download

ZERO123_MODEL_REVISION = "2da07e89919e1a130c9b5add1584c70c7aa065fd"
ZERO123_PIPELINE_REVISION = "983e66d28a3637ddd8e3e2fd8165cdff32230872"
INSTANTMESH_MODEL_REVISION = "b785b4ecfb6636ef34a08c748f96f6a5686244d0"

src, out = sys.argv[1], Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
im = Image.open(src).convert("RGBA")
# ROOMY FRAMING FIX: Zero123++ hunches full-body figures (tucks the head into the shoulders) when the
# subject fills the frame. Re-pad the alpha-cropped figure into a square at ~0.60 height with transparent
# margin so the model keeps the figure UPRIGHT with a distinct head/neck. (Optional 3rd arg overrides frac.)
frac = float(sys.argv[3]) if len(sys.argv) > 3 else 0.60
import numpy as _np
_a = _np.array(im)[..., 3]
_ys, _xs = _np.where(_a > 20)
if len(_xs):
    x0, x1, y0, y1 = _xs.min(), _xs.max(), _ys.min(), _ys.max()
    im = im.crop((x0, y0, x1 + 1, y1 + 1))
w, h = im.size
side = int(max(w, h) / frac)
sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
sq.alpha_composite(im, ((side - w) // 2, (side - h) // 2))
im = sq
bg = Image.new("RGBA", im.size, (255,255,255,255)); bg.alpha_composite(im); im = bg.convert("RGB")
pipe = DiffusionPipeline.from_pretrained("sudo-ai/zero123plus-v1.2", custom_pipeline="sudo-ai/zero123plus-pipeline",
                                         revision=ZERO123_MODEL_REVISION,
                                         custom_revision=ZERO123_PIPELINE_REVISION,
                                         torch_dtype=torch.float16, trust_remote_code=True)
pipe.scheduler = EulerAncestralDiscreteScheduler.from_config(pipe.scheduler.config, timestep_spacing='trailing')
# load InstantMesh custom white-bg UNet
unet_ckpt = hf_hub_download(repo_id="TencentARC/InstantMesh", filename="diffusion_pytorch_model.bin",
                            repo_type="model", revision=INSTANTMESH_MODEL_REVISION)
pipe.unet.load_state_dict(torch.load(unet_ckpt, map_location="cpu", weights_only=True), strict=True)
pipe.to("cuda"); print("PIPE_READY_WITH_IM_UNET")
g = pipe(im, num_inference_steps=75).images[0]
g.save(str(out/"grid_im.png")); print("VIEWS_OK", g.size)
