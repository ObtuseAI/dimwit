import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _source(name: str) -> str:
    return (ROOT / "neural3d" / name).read_text(encoding="utf-8")


def test_remote_custom_pipeline_is_commit_pinned_in_both_entrypoints():
    for name in ("gen_multiview.py", "gen_views_im.py"):
        source = _source(name)
        ast.parse(source)
        assert 'ZERO123_MODEL_REVISION = "2da07e89919e1a130c9b5add1584c70c7aa065fd"' in source
        assert 'ZERO123_PIPELINE_REVISION = "983e66d28a3637ddd8e3e2fd8165cdff32230872"' in source
        assert "revision=ZERO123_MODEL_REVISION" in source
        assert "custom_revision=ZERO123_PIPELINE_REVISION" in source


def test_instantmesh_checkpoint_is_pinned_and_weights_only():
    source = _source("gen_views_im.py")
    assert 'INSTANTMESH_MODEL_REVISION = "b785b4ecfb6636ef34a08c748f96f6a5686244d0"' in source
    assert "revision=INSTANTMESH_MODEL_REVISION" in source
    assert "weights_only=True" in source
