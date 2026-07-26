"""Reconstruct a mesh from a pre-generated Zero123++ six-view grid using InstantMesh's NeRF model.

Run with the InstantMesh checkout as the working directory so its ``src`` and ``configs`` packages resolve.
The script is Dimwit-owned instead of being an untracked mutation inside the upstream submodule.
"""
from __future__ import annotations

import sys

import torch
import torchvision.transforms.functional as TF
from einops import rearrange
from omegaconf import OmegaConf
from PIL import Image

from src.utils.camera_util import get_zero123plus_input_cameras
from src.utils.mesh_util import save_obj
from src.utils.train_util import instantiate_from_config


grid_path, out_obj = sys.argv[1], sys.argv[2]
cfg = OmegaConf.load("configs/instant-nerf-large.yaml")
device = torch.device("cuda")
model = instantiate_from_config(cfg.model_config)
state = torch.load("ckpts/instant_nerf_large.ckpt", map_location="cpu")["state_dict"]
state = {key[14:]: value for key, value in state.items() if key.startswith("lrm_generator.")}
model.load_state_dict(state, strict=True)
model = model.to(device).eval()
print("RECON_MODEL_LOADED")

grid = Image.open(grid_path).convert("RGB")
tensor = TF.to_tensor(grid)
images = rearrange(tensor, "c (n h) (m w) -> (n m) c h w", n=3, m=2)
images = TF.resize(images.unsqueeze(0).to(device), 320, antialias=True).clamp(0, 1)
cameras = get_zero123plus_input_cameras(batch_size=1, radius=4.0).to(device)
with torch.no_grad():
    planes = model.forward_planes(images, cameras)
    vertices, faces, colors = model.extract_mesh(
        planes,
        use_texture_map=False,
        mesh_resolution=int(sys.argv[3]) if len(sys.argv) > 3 else 512,
        mesh_threshold=10.0,
    )
save_obj(vertices, faces, colors, out_obj)
print("RECON_OK", out_obj, "verts", len(vertices), "faces", len(faces))
