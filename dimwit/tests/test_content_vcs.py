"""CONTENT_UNDER_LFS_V1 (Horizon 2) — RED-first contract tests. Pure static parsing over synthetic
.gitattributes / .gitignore text (snapshot law); git check-attr proof exercised via an injected runner."""
from __future__ import annotations

from types import SimpleNamespace

from dimwit.pipelines.content_vcs import (
    CONTENT_PREFIX,
    LFS_TOKENS,
    REQUIRED_LFS_EXTS,
    check_assets_lfs_tracked,
    check_gitignore_carveout,
    check_lfs_attrs,
    evaluate_check_attr_output,
    evaluate_index_lfs,
    parse_lfs_exts,
    wanefall_is_ignored,
)


def _attrs(exts, tokens=LFS_TOKENS, prefix=CONTENT_PREFIX) -> str:
    lines = []
    for e in exts:
        lines.append(f"{prefix}**/*.{e} " + " ".join(tokens) + " -text")
    return "\n".join(lines)


# ---------------------------------------------------------------- 1. LFS filter contract
def test_lfs_attrs_full_contract_passes():
    r = check_lfs_attrs(_attrs(REQUIRED_LFS_EXTS))
    assert r["passed"], r["issues"]
    assert r["missing"] == []


def test_lfs_attrs_dropped_ext_fails():
    r = check_lfs_attrs(_attrs([e for e in REQUIRED_LFS_EXTS if e != "uasset"]))
    assert not r["passed"]
    assert "uasset" in r["missing"]


def test_lfs_attrs_half_filter_not_counted():
    # only filter=lfs, missing diff=lfs / merge=lfs -> not a full LFS rule
    r = check_lfs_attrs(_attrs(REQUIRED_LFS_EXTS, tokens=("filter=lfs",)))
    assert not r["passed"]
    assert set(r["missing"]) == set(REQUIRED_LFS_EXTS)


def test_lfs_attrs_wrong_scope_not_counted():
    # rule scoped to the whole Content/ tree, not the authored Content/Wanefall/ subtree
    r = check_lfs_attrs(_attrs(REQUIRED_LFS_EXTS, prefix="Content/"))
    assert not r["passed"]


def test_lfs_attrs_empty_fails_closed():
    r = check_lfs_attrs("")
    assert not r["passed"]
    assert set(r["missing"]) == set(REQUIRED_LFS_EXTS)


def test_parse_lfs_exts_ignores_comments_and_blanks():
    text = "# comment\n\n" + _attrs(["uasset", "umap"])
    assert parse_lfs_exts(text) == {"uasset", "umap"}


# ---------------------------------------------------------------- 2. ignore carve-out
def test_carveout_intact_not_ignored():
    gi = "Content/*\n!Content/Wanefall/\nSaved/\n"
    assert not wanefall_is_ignored(gi)
    assert check_gitignore_carveout(gi)["passed"]


def test_carveout_lost_is_ignored():
    gi = "Content/*\nSaved/\n"  # broad ignore, negation removed
    assert wanefall_is_ignored(gi)
    assert not check_gitignore_carveout(gi)["passed"]


def test_carveout_order_last_match_wins():
    # negation BEFORE the broad ignore -> broad ignore wins -> ignored
    gi = "!Content/Wanefall/\nContent/*\n"
    assert wanefall_is_ignored(gi)
    assert not check_gitignore_carveout(gi)["passed"]


def test_no_content_ignore_at_all_passes():
    gi = "Saved/\nIntermediate/\n"  # Content never ignored -> content tracked -> fine
    assert not wanefall_is_ignored(gi)
    assert check_gitignore_carveout(gi)["passed"]


def test_bare_content_dir_ignore_covers_wanefall():
    gi = "Content/\n"  # `Content/` (no glob) also swallows the subtree
    assert wanefall_is_ignored(gi)


# ---------------------------------------------------------------- 3. real-asset proof (git check-attr)
def test_evaluate_check_attr_all_lfs_passes():
    paths = ["Content/Wanefall/a.uasset", "Content/Wanefall/b.uasset"]
    stdout = "\n".join(f"{p}: filter: lfs" for p in paths)
    r = evaluate_check_attr_output(stdout, paths)
    assert r["passed"]
    assert r["untracked"] == []


def test_evaluate_check_attr_raw_asset_fails():
    paths = ["Content/Wanefall/a.uasset", "Content/Wanefall/raw.uasset"]
    stdout = "Content/Wanefall/a.uasset: filter: lfs\nContent/Wanefall/raw.uasset: filter: unspecified"
    r = evaluate_check_attr_output(stdout, paths)
    assert not r["passed"]
    assert r["untracked"] == ["Content/Wanefall/raw.uasset"]


def _mk_asset(tmp_path):
    content = tmp_path / "Content" / "Wanefall" / "Dimwit"
    content.mkdir(parents=True)
    (content / "SM_thing.uasset").write_bytes(b"pointerish")
    return tmp_path, tmp_path / "Content" / "Wanefall"


def test_assets_lfs_tracked_pass_with_fake_runner(tmp_path):
    root, croot = _mk_asset(tmp_path)

    def runner(project_root, rel_posix):
        return SimpleNamespace(stdout="\n".join(f"{p}: filter: lfs" for p in rel_posix),
                               stderr="", returncode=0)

    def index_reader(project_root, rel_posix):
        return {"tracked": True,
                "content": b"version https://git-lfs.github.com/spec/v1\noid sha256:abc\nsize 10\n"}

    r = check_assets_lfs_tracked(root, croot, runner=runner, index_reader=index_reader)
    assert r["passed"], r["issues"]
    assert r["checked"] == 1
    assert r["blocked"] is False


def test_assets_lfs_tracked_fail_when_raw(tmp_path):
    root, croot = _mk_asset(tmp_path)

    def runner(project_root, rel_posix):
        return SimpleNamespace(stdout="\n".join(f"{p}: filter: unspecified" for p in rel_posix),
                               stderr="", returncode=0)

    r = check_assets_lfs_tracked(root, croot, runner=runner)
    assert not r["passed"]
    assert r["blocked"] is False
    assert r["untracked"]


def test_lfs_attribute_is_not_enough_for_untracked_or_raw_index_blob(tmp_path):
    root, croot = _mk_asset(tmp_path)

    def attr_runner(project_root, rel_posix):
        return SimpleNamespace(stdout="\n".join(f"{p}: filter: lfs" for p in rel_posix),
                               stderr="", returncode=0)

    for indexed in (
        {"tracked": False, "content": b""},
        {"tracked": True, "content": b"raw uasset bytes"},
    ):
        result = check_assets_lfs_tracked(
            root, croot, runner=attr_runner,
            index_reader=lambda project_root, rel_posix, row=indexed: row,
        )
        assert not result["passed"]
        assert result["invalid_index_assets"]


def test_index_lfs_pointer_contract():
    pointer = b"version https://git-lfs.github.com/spec/v1\noid sha256:abc\nsize 1\n"
    assert evaluate_index_lfs({"a.uasset": {"tracked": True, "content": pointer}})["passed"]
    assert not evaluate_index_lfs({"a.uasset": {"tracked": True, "content": b"raw"}})["passed"]


def test_assets_lfs_tracked_no_assets_fails_closed(tmp_path):
    croot = tmp_path / "Content" / "Wanefall"
    croot.mkdir(parents=True)
    r = check_assets_lfs_tracked(tmp_path, croot, runner=lambda *a: SimpleNamespace(stdout="", returncode=0))
    assert not r["passed"]
    assert r["blocked"] is False
    assert r["checked"] == 0


def test_assets_lfs_tracked_git_missing_blocks(tmp_path):
    root, croot = _mk_asset(tmp_path)

    def runner(project_root, rel_posix):
        raise FileNotFoundError("git")

    r = check_assets_lfs_tracked(root, croot, runner=runner)
    assert not r["passed"]
    assert r["blocked"] is True  # BLOCKED, never a silent pass


def test_assets_lfs_tracked_git_error_blocks(tmp_path):
    root, croot = _mk_asset(tmp_path)

    def runner(project_root, rel_posix):
        return SimpleNamespace(stdout="", stderr="fatal: not a git repo", returncode=128)

    r = check_assets_lfs_tracked(root, croot, runner=runner)
    assert r["blocked"] is True


# ---------------------------------------------------------------- ratchet (guard the contract itself)
def test_ratchet_required_exts_cover_binary_asset_types():
    for e in ("uasset", "umap", "png", "tga", "fbx", "wav"):
        assert e in REQUIRED_LFS_EXTS, f"{e} dropped from REQUIRED_LFS_EXTS — LFS coverage weakened"
    assert LFS_TOKENS == ("filter=lfs", "diff=lfs", "merge=lfs")
    assert CONTENT_PREFIX == "Content/Wanefall/"
