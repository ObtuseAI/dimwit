"""Shared authentication and path policy for the in-editor Unreal bridge."""

from __future__ import annotations

import hmac
import os
from pathlib import Path

TOKEN_ENV = "DIMWIT_UE_BRIDGE_TOKEN"
MAX_REQUEST_BYTES = 1_000_000
MAX_EXEC_CHARS = 256_000
MAX_SCREENSHOT_DIMENSION = 4096


def bridge_token() -> str:
    token = os.environ.get(TOKEN_ENV, "")
    if len(token) < 32:
        raise RuntimeError(f"{TOKEN_ENV} must contain a random token of at least 32 characters")
    return token


def authenticated(supplied: object, expected: str) -> bool:
    return isinstance(supplied, str) and hmac.compare_digest(supplied, expected)


def confined_screenshot_path(value: object, roots: tuple[Path, ...]) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("screenshot path must be a non-empty string")
    path = Path(value).expanduser().resolve(strict=False)
    approved = tuple(Path(root).resolve() for root in roots)
    if not any(path.is_relative_to(root) for root in approved):
        raise ValueError("screenshot path is outside approved Dimwit capture roots")
    if path.suffix.lower() != ".png":
        raise ValueError("screenshot path must use the .png extension")
    if not path.parent.is_dir():
        raise ValueError("screenshot parent directory does not exist")
    return path


def screenshot_resolution(value: object) -> tuple[int, int]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError("screenshot resolution must contain width and height")
    width, height = (int(value[0]), int(value[1]))
    if not (1 <= width <= MAX_SCREENSHOT_DIMENSION and 1 <= height <= MAX_SCREENSHOT_DIMENSION):
        raise ValueError("screenshot resolution is outside the supported range")
    return width, height
