"""Zero123++ multiview: 1 front image -> 6 surround views (incl. the BACK). Open-source (sudo-ai, Apache-2).
Generates the 'backside image' so reconstruction isn't single-view-blind."""
import sys, torch
from pathlib import Path
from PIL import Image
from diffusers import DiffusionPipeline, EulerAncestralDiscreteScheduler

ZERO123_MODEL_REVISION = "2da07e89919e1a130c9b5add1584c70c7aa065fd"
ZERO123_PIPELINE_REVISION = "983e66d28a3637ddd8e3e2fd8165cdff32230872"

src, outdir = sys.argv[1], Path(sys.argv[2]); outdir.mkdir(parents=True, exist_ok=True)
# white-bg RGB of the subject
im = Image.open(src).convert("RGBA")
bg = Image.new("RGBA", im.size, (255,255,255,255)); bg.alpha_composite(im); im = bg.convert("RGB")

pipe = DiffusionPipeline.from_pretrained(
    "sudo-ai/zero123plus-v1.2", custom_pipeline="sudo-ai/zero123plus-pipeline",
    revision=ZERO123_MODEL_REVISION, custom_revision=ZERO123_PIPELINE_REVISION,
    torch_dtype=torch.float16, trust_remote_code=True)
pipe.scheduler = EulerAncestralDiscreteScheduler.from_config(pipe.scheduler.config, timestep_spacing='trailing')
pipe.to("cuda")
print("MODEL_LOADED")
result = pipe(im, num_inference_steps=75).images[0]   # 640x960 grid: 3 rows x 2 cols = 6 views
result.save(str(outdir/"grid.png"))
# split the 3x2 grid into 6 tiles (azimuth 30,90,150,210,270,330 ; the 150/210 tiles ~= the back)
w,h = result.size; tw,th = w//2, h//3
names = ["az030","az090","az150","az210","az270","az330"]
k=0
for r in range(3):
    for c in range(2):
        result.crop((c*tw, r*th, (c+1)*tw, (r+1)*th)).save(str(outdir/f"view_{names[k]}.png")); k+=1
print("MULTIVIEW_OK", result.size)
