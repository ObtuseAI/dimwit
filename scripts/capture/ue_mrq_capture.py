"""scripts/capture/ue_mrq_capture.py — MovieRenderQueue animated-capture harness (BLOCKER-Z2 unlock).

THE UNLOCK (proven 2026-06-27): every prior capture method (offscreen SceneCapture2D, PoseableMesh,
leader-pose, PIE+AlwaysTickPose, Sequencer-scrub) rendered the FROZEN BIND POSE. MovieRenderQueue renders
through the real movie pipeline (PIE-backed), which forces skinned render-state refresh, so it captures
GENUINELY ADVANCING animated frames. Verified by own eyes (leg/shadow positions change across the run cycle)
+ structured per-frame pixel delta.

Prereq: the `MovieRenderPipeline` plugin must be enabled in the .uproject (it is, as of this work) and the
editor restarted once. Drive via the Dimwit 8222 bridge. The editor window must be FOREGROUNDED + not
minimized for the PIE render to produce frames (see scratchpad/foreground_editor.ps1) — same lesson as the
HighResShot still-capture unlock.

Pipeline:
  build_capture_sequence()  -> LevelSequence: spawnable mesh (+AnimBP) + skeletal-anim track + framed camera
                               + a key light, all SPAWNABLES (self-contained; renders against any map).
  render_sequence()         -> MoviePipelinePIEExecutor renders a PNG sequence to out_dir (async; poll dir).
  motion_proof()            -> asserts the frames advance (defeats the frozen trap).

CAVEAT (open polish, NOT a blocker for the unlock): exposure/lighting is STAGE-DEPENDENT. The jail-cell map's
PostProcess crushes the body to shadow regardless of camera-PP / console-var / spawnable-light overrides
(its key light is overhead -> floor + character-top lit, vertical body shadowed to a horizontal camera).
For QA-grade (well-lit, judge-able) captures, render against a CLEAN STAGE with a manual-exposure PPV
(cf. Wanefall_CleanStage_01 / the memory's clean-baseline recipe), not the jail cell. The capture MECHANISM
is map-independent and proven; only the stage lighting needs to be the clean one.

  python scripts/capture/ue_mrq_capture.py            # build + render the Ekris MM_Run_Fwd proof
"""
from __future__ import annotations
import sys, json, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from ue_mcp.ue_client import call

DEFAULT_MESH = "/Game/Wanefall/Dimwit/CharactersRigged/SM_Char_02_ekris_Rig"
DEFAULT_ABP  = "/Game/Mannequins/Animations/ABP_Manny"
DEFAULT_ANIM = "/Game/Mannequins/Animations/Manny/MM_Run_Fwd"
DEFAULT_MAP  = "/Game/Wanefall/Maps/Wanefall_CleanStage_01"   # studio: Sun + SkyLight fill + ExposureLock PPV
SEQ_PATH = "/Game/Wanefall/Dimwit/MRQ"
SEQ_NAME = "MRQ_EkrisRun_Proof"


def build_capture_sequence(mesh=DEFAULT_MESH, abp=DEFAULT_ABP, anim=DEFAULT_ANIM,
                           seq_path=SEQ_PATH, seq_name=SEQ_NAME, fps=30,
                           spawn=(400.0, 0.0, 0.0),    # offset from CleanStage's Manny@origin
                           exposure_bias=1.0):
    """exposure_bias: camera post-process MANUAL exposure compensation. MRQ is a real ticking
    render (unlike tick-less probe SceneCaptures where PP overrides are inert), so the camera
    exposure IS authoritative here — auto-exposure metered the white stage and crushed the
    dark-violet zythan body to a black blob (H1B3, judged unanimously too_dark by the quorum)."""
    code = r'''
import unreal, json
res = {"steps": []}
def step(n, fn):
    try: v = fn(); res["steps"].append([n, "ok"]); return v
    except Exception as e: res["steps"].append([n, "ERR:"+str(e)[:140]]); return None
tools = unreal.AssetToolsHelpers.get_asset_tools(); eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
mesh = unreal.load_asset("__MESH__"); abp = unreal.load_asset("__ABP__"); anim = unreal.load_asset("__ANIM__")
gen = abp.generated_class() if abp else None
alen = anim.get_play_length() if anim else 1.9; nframes = int(alen*__FPS__)
# A rendered sequence stays IN-MEMORY pinned after MRQ (no on-disk referencers; delete_asset
# returns False and a same-name create_asset hangs the game thread on the collision). Never
# fight the pin: walk a small name pool and use the first name that is free or deletable.
seq_name = None
for cand in ["__SEQN__", "__SEQN___b", "__SEQN___c", "__SEQN___d"]:
    full = "__SEQP__/" + cand
    if not unreal.EditorAssetLibrary.does_asset_exist(full):
        seq_name = cand; break
    a = unreal.load_asset(full)
    if a:
        try: unreal.get_editor_subsystem(unreal.AssetEditorSubsystem).close_all_editors_for_asset(a)
        except Exception: pass
    if unreal.EditorAssetLibrary.delete_asset(full):
        seq_name = cand; break
if seq_name is None:
    raise RuntimeError("no usable sequence name (all pool names pinned) - restart the editor")
res["steps"].append(["pick_name", seq_name])
seq = step("create", lambda: tools.create_asset(seq_name, "__SEQP__", unreal.LevelSequence, unreal.LevelSequenceFactoryNew()))
step("rate", lambda: seq.set_display_rate(unreal.FrameRate(__FPS__,1)))
step("p_start", lambda: seq.set_playback_start_seconds(0.0)); step("p_end", lambda: seq.set_playback_end_seconds(float(alen)))
sx,sy,sz = __SPAWN__
tmp = eas.spawn_actor_from_class(unreal.SkeletalMeshActor, unreal.Vector(sx,sy,sz), unreal.Rotator(0,0,0))
c = tmp.skeletal_mesh_component
try: c.set_skeletal_mesh_asset(mesh)
except Exception: c.set_editor_property("skeletal_mesh_asset", mesh)
if gen:
    try: c.set_anim_instance_class(gen)
    except Exception: pass
ek = step("spawnable_mesh", lambda: seq.add_spawnable_from_instance(tmp)); step("destroy_tmp", lambda: eas.destroy_actor(tmp))
atrk = step("anim_track", lambda: ek.add_track(unreal.MovieSceneSkeletalAnimationTrack))
asec = step("anim_section", lambda: atrk.add_section())
def set_anim():
    p = asec.get_editor_property("params"); p.set_editor_property("animation", anim)
    asec.set_editor_property("params", p); asec.set_range(0, nframes); return 1
step("anim_params", set_anim)
cam_loc = unreal.Vector(sx, sy+430.0, sz+95.0); look = unreal.Vector(sx, sy, sz+95.0)
cam_rot = unreal.MathLibrary.find_look_at_rotation(cam_loc, look)
tcam = eas.spawn_actor_from_class(unreal.CameraActor, cam_loc, cam_rot)
try: tcam.camera_component.set_field_of_view(50.0)
except Exception: pass
def lock_exposure():
    bias = __BIAS__
    if bias is None:
        return "skipped (scene auto exposure)"
    pp = tcam.camera_component.post_process_settings
    pp.set_editor_property("override_auto_exposure_method", True)
    pp.set_editor_property("auto_exposure_method", unreal.AutoExposureMethod.AEM_MANUAL)
    pp.set_editor_property("override_auto_exposure_bias", True)
    pp.set_editor_property("auto_exposure_bias", float(bias))
    # do NOT disable apply_physical_camera_exposure: with it off this engine pins exposure at a
    # fixed 1.0 and IGNORES the bias (probe-proven: bias 5 vs 14.5 rendered pixel-identical).
    tcam.camera_component.set_editor_property("post_process_settings", pp)
    return 1
step("lock_exposure", lock_exposure)
cam = step("spawnable_cam", lambda: seq.add_spawnable_from_instance(tcam)); step("destroy_cam", lambda: eas.destroy_actor(tcam))
# no harness key light: render against a CLEAN STAGE (Sun + SkyLight ambient fill + ExposureLock PPV) for
# QA-grade exposure. (A self-spawned directional light could not beat the jail-cell PostProcess crush.)
def cut():
    try: ct = seq.add_master_track(unreal.MovieSceneCameraCutTrack)
    except Exception: ct = seq.add_track(unreal.MovieSceneCameraCutTrack)
    cs = ct.add_section(); cs.set_range(0, nframes)
    try: cs.set_camera_binding_id(cam.get_binding_id())
    except Exception: cs.set_camera_binding_id(unreal.MovieSceneSequenceExtensions.get_binding_id(seq, cam))
    return 1
step("camera_cut", cut)
step("save", lambda: unreal.EditorAssetLibrary.save_asset("__SEQP__/" + seq_name))
res["seq"]="__SEQP__/" + seq_name; res["nframes"]=nframes; result=json.dumps(res)
'''
    for k, v in {"__MESH__": mesh, "__ABP__": abp, "__ANIM__": anim, "__SEQP__": seq_path,
                 "__SEQN__": seq_name, "__FPS__": str(fps), "__SPAWN__": str(tuple(spawn)),
                 "__BIAS__": ("None" if exposure_bias is None else str(float(exposure_bias)))}.items():
        code = code.replace(k, v)
    return call("exec", {"code": code})


def render_sequence(out_dir, seq=f"{SEQ_PATH}/{SEQ_NAME}", map_path=DEFAULT_MAP, res=(1280, 720)):
    os.makedirs(out_dir, exist_ok=True)
    code = r'''
import unreal, json
res = {"steps": []}
def step(n, fn):
    try: v = fn(); res["steps"].append([n,"ok"]); return v
    except Exception as e: res["steps"].append([n,"ERR:"+str(e)[:140]]); return None
ss = unreal.get_editor_subsystem(unreal.MoviePipelineQueueSubsystem); q = ss.get_queue()
for j in list(q.get_jobs()): q.delete_job(j)
job = q.allocate_new_job(unreal.MoviePipelineExecutorJob); job.job_name = "MRQCapture"
job.map = unreal.SoftObjectPath("__MAP__"); job.sequence = unreal.SoftObjectPath("__SEQ__")
cfg = job.get_configuration()
cfg.find_or_add_setting_by_class(unreal.MoviePipelineDeferredPassBase)
cfg.find_or_add_setting_by_class(unreal.MoviePipelineImageSequenceOutput_PNG)
def qa_cvars():
    # QA frames must show the MATERIAL, not cinematography: motion blur smears limbs into
    # "disfigured", bloom halos bury the seam evidence, vignette fakes an exposure falloff.
    cv = cfg.find_or_add_setting_by_class(unreal.MoviePipelineConsoleVariableSetting)
    wanted = {"r.MotionBlurQuality": 0, "r.BloomQuality": 0, "r.Tonemapper.Quality": 2}
    try:
        for k, v in wanted.items():
            cv.add_or_update_console_variable(k, v)
    except Exception:
        cvars = dict(cv.get_editor_property("console_variables") or {})
        cvars.update(wanted)
        cv.set_editor_property("console_variables", cvars)
    return 1
step("qa_cvars", qa_cvars)
outs = cfg.find_or_add_setting_by_class(unreal.MoviePipelineOutputSetting)
outs.output_directory = unreal.DirectoryPath("__OUT__"); outs.output_resolution = unreal.IntPoint(__RX__, __RY__)
outs.file_name_format = "frame.{frame_number}"
try: outs.set_editor_property("flush_disk_writes_per_shot", True)
except Exception: pass
ex = unreal.MoviePipelinePIEExecutor(); ss.render_queue_with_executor_instance(ex)
res["out"]="__OUT__"; result=json.dumps(res)
'''
    for k, v in {"__MAP__": map_path, "__SEQ__": seq, "__OUT__": out_dir.replace("\\", "/"),
                 "__RX__": str(res[0]), "__RY__": str(res[1])}.items():
        code = code.replace(k, v)
    return call("exec", {"code": code}, timeout=240.0)


def motion_proof(frame_dir, prefix="frame", n=56):
    """Return advancing-motion metrics. Defeats the frozen-bind trap: avg consecutive delta must be > 0."""
    from PIL import Image
    import numpy as np
    def load(i):
        return np.asarray(Image.open(os.path.join(frame_dir, f"{prefix}.{i:04d}.png")).convert("RGB"), np.int16)
    f0 = load(0); prev = f0; total = 0.0; maxc = 0.0
    for i in range(1, n):
        fi = load(i); c = float(np.abs(fi - prev).mean()); total += c; maxc = max(maxc, c); prev = fi
    return {"avg_consecutive_delta": total / (n - 1), "max_consecutive_delta": maxc,
            "advancing": (total / (n - 1)) > 0.1}


DEFORM_KEY_JOINTS = ("thigh_l", "thigh_r", "calf_l", "calf_r",
                     "upperarm_l", "upperarm_r", "lowerarm_l", "lowerarm_r",
                     "spine_03", "neck_01", "hand_l", "hand_r", "foot_l", "foot_r")


def sample_joint_articulation(anim=DEFAULT_ANIM, joints=DEFORM_KEY_JOINTS, samples=12):
    """Bone-space angular range per joint across the clip (H1B3 per-joint deformation telemetry).
    Samples the exact AnimSequence the capture rendered via the AnimPose API: for each joint the
    max quaternion angle vs the first sampled frame. A frozen or partially-evaluated clip reads 0
    for the dead joints — pixel displacement alone can't see that."""
    code = r'''
import unreal, json, math
res = {"joints": {}, "errors": []}
anim = unreal.load_asset("__ANIM__")
try:
    total = int(anim.get_editor_property("number_of_sampled_frames"))
except Exception:
    total = max(2, int(anim.get_play_length() * 30))
step = max(1, total // __SAMPLES__)
opts = unreal.AnimPoseEvaluationOptions()
names = __JOINTS__
base = {}
sampled = 0
for f in range(0, total, step):
    try:
        pose = unreal.AnimPoseExtensions.get_anim_pose_at_frame(anim, f, opts)
    except Exception as e:
        res["errors"].append("frame %d: %s" % (f, str(e)[:120])); continue
    sampled += 1
    for n in names:
        try:
            t = unreal.AnimPoseExtensions.get_bone_pose(pose, n, unreal.AnimPoseSpaces.LOCAL)
            q = t.rotation
        except Exception as e:
            res["errors"].append("%s@%d: %s" % (n, f, str(e)[:100])); continue
        if n not in base:
            base[n] = q; res["joints"][n] = 0.0
        else:
            b = base[n]
            dot = abs(b.x*q.x + b.y*q.y + b.z*q.z + b.w*q.w)
            ang = math.degrees(2.0 * math.acos(min(1.0, dot)))
            res["joints"][n] = max(res["joints"][n], round(ang, 2))
res["frames_sampled"] = sampled
res["total_frames"] = total
result = json.dumps(res)
'''
    code = code.replace("__ANIM__", anim).replace("__SAMPLES__", str(samples)) \
               .replace("__JOINTS__", json.dumps(list(joints)))
    return call("exec", {"code": code}, timeout=120.0)


def emit_capture_artifacts_v2(frame_dir, prefix="frame", n=56, *, asset_id, rig_asset,
                              anim, stage, joint_articulation, judge=True,
                              pose_picks=("bind:0", "pose_a:14", "pose_b:28", "pose_c:42")):
    """H1B3 identity-bound emitter — supersedes the schema-less v1 (whose artifacts carried no
    subject identity, letting restored ekris-era evidence keep the deformation gate green while
    zythan shipped unproven). Writes:
      artifacts/mrq_capture_result.json   -> mrq_capture_advanced
      artifacts/pose_capture_result.json  -> rig_deformation_clean + rig_deform_identity_bound
                                             + rig_deform_joints_articulated + rig_deform_silhouette_judged
    Records: subject identity + sha256 of the rig .uasset (re-import invalidates), per-joint
    articulation telemetry (sample_joint_articulation), and a calibrated-quorum silhouette
    verdict for bind + every stress pose (judge bound to the current golden manifest)."""
    import hashlib
    import shutil
    art = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "artifacts")
    poses_dir = os.path.join(art, "mrq_poses"); os.makedirs(poses_dir, exist_ok=True)
    m = motion_proof(frame_dir, prefix, n)
    json.dump({"frame_dir": frame_dir, "prefix": prefix, "frame_count": n,
               "avg_consecutive_delta": round(m["avg_consecutive_delta"], 3),
               "max_consecutive_delta": round(m["max_consecutive_delta"], 3),
               "advancing": m["advancing"], "asset": asset_id, "anim": anim, "stage": stage,
               "source": "scripts/capture/ue_mrq_capture.py"},
              open(os.path.join(art, "mrq_capture_result.json"), "w"), indent=2)
    picks = dict(p.split(":") for p in pose_picks)
    for name, idx in picks.items():
        # FLATTEN to RGB: MRQ writes RGBA with alpha≈0 everywhere but the subject, so every
        # consumer disagrees about the pixels (viewers composite over white -> ghost; PIL and
        # the vision judges read raw RGB). One truth: the raw color buffer, alpha dropped.
        from PIL import Image as _Img
        src = os.path.join(frame_dir, f"{prefix}.{int(idx):04d}.png")
        _Img.open(src).convert("RGB").save(os.path.join(poses_dir, f"{name}.png"))
    poses = {k: os.path.join(poses_dir, f"{k}.png").replace("\\", "/") for k in picks if k != "bind"}
    bind_png = os.path.join(poses_dir, "bind.png").replace("\\", "/")

    from dimwit.pipelines.validation import PROJECT
    rel = str(rig_asset).replace("/Game/", "").lstrip("/").split(".")[0]
    rig_file = PROJECT / "Content" / (rel + ".uasset")
    rig_sha = hashlib.sha256(rig_file.read_bytes()).hexdigest()

    verdicts, cal_hash = {}, None
    if judge:
        from dimwit import optics, optics_calibration
        cal_hash = optics_calibration.manifest_hash()
        for name in ["bind"] + sorted(poses.keys()):
            png = bind_png if name == "bind" else poses[name]
            v = optics.judge_character_quorum(png, reference=None, subject_only=True)
            verdicts[name] = {"passed": bool(v.get("passed")), "hard_fail": bool(v.get("hard_fail")),
                              "score": v.get("score"), "issues": (v.get("issues") or [])[:4],
                              "quorum": v.get("quorum", {})}

    import time as _time
    json.dump({"bind": bind_png, "poses": poses,
               "subject_character": asset_id, "rig_asset": rig_asset,
               "rig_uasset_sha256": rig_sha, "captured_at": _time.time(),
               "anim": anim, "stage": stage,
               "joint_articulation": joint_articulation,
               "silhouette_verdicts": verdicts,
               "judge_calibration_manifest_hash": cal_hash,
               "source": f"scripts/capture/ue_mrq_capture.py emit_capture_artifacts_v2 {anim} on {asset_id} ({stage})"},
              open(os.path.join(art, "pose_capture_result.json"), "w"), indent=2)
    return m


def _foreground_editor():
    """Restore + foreground the UnrealEditor window (the MRQ PIE render needs it not-minimized)."""
    import ctypes
    from ctypes import wintypes
    u = ctypes.windll.user32
    found = []
    proto = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        ln = u.GetWindowTextLengthW(hwnd)
        if ln:
            buf = ctypes.create_unicode_buffer(ln + 1)
            u.GetWindowTextW(hwnd, buf, ln + 1)
            if "Unreal Editor" in buf.value:
                found.append(hwnd)
        return True
    u.EnumWindows(proto(cb), 0)
    if found:
        u.ShowWindow(found[0], 9); u.SetForegroundWindow(found[0])  # SW_RESTORE
        return True
    return False


def _poll_frames(out_dir, prefix="frame", timeout_s=200):
    import time
    prev, stable, cnt, waited = -1, 0, 0, 0
    while waited < timeout_s:
        time.sleep(6); waited += 6
        cnt = len([f for f in os.listdir(out_dir) if f.startswith(prefix) and f.endswith(".png")]) if os.path.isdir(out_dir) else 0
        stable = stable + 1 if (cnt > 0 and cnt == prev) else 0
        prev = cnt
        if stable >= 2 and cnt > 0:
            break
    return cnt


def mrq_render_fn(mesh=DEFAULT_MESH, abp=DEFAULT_ABP, anim=DEFAULT_ANIM, map_path=DEFAULT_MAP, out_dir=None, rep_idx=28):
    """A render_fn(cand) for engine.recursive_mutation_loop. Each candidate REGENERATES real motion pixels via
    MRQ (build sequence -> foreground -> render -> emit artifacts) and attaches a representative frame to
    cand.evidence so score_candidate's V2 pixel-truth override measures REAL pixels instead of declared spec.
    Closes the loop's "no real pixels -> fail-closed BLOCKED -> NEEDS_RECURSION" gap for animation assets.
    (A candidate whose mutation changes spec['anim'] renders a different clip -> genuine per-candidate variation.)"""
    out_dir = out_dir or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "artifacts", "mrq_frames")
    os.makedirs(out_dir, exist_ok=True)
    def _render(cand):
        a = cand.spec.get("anim", anim)
        for f in os.listdir(out_dir):
            if f.endswith(".png"):
                try: os.remove(os.path.join(out_dir, f))
                except OSError: pass
        build_capture_sequence(mesh=mesh, abp=abp, anim=a)
        _foreground_editor()
        render_sequence(out_dir, map_path=map_path)
        n = _poll_frames(out_dir)
        if n >= 8:
            ja = _parse_joint_articulation(sample_joint_articulation(anim=str(a)))
            m = emit_capture_artifacts_v2(out_dir, prefix="frame", n=n, asset_id=cand.asset_id,
                                          rig_asset=mesh, anim=str(a),
                                          stage=map_path.rsplit("/", 1)[-1],
                                          joint_articulation=ja)
            rep = os.path.join(out_dir, f"frame.{min(rep_idx, n - 1):04d}.png")
            cand.evidence = dict(cand.evidence or {})
            cand.evidence["hero_contact_sheet"] = rep
            cand.evidence["player_camera_contact_sheet"] = rep
            cand.evidence["mrq_motion"] = m
        return cand
    return _render


def _bridge_json(bridge_resp: dict) -> dict:
    """Parse the bridge exec envelope's `result` (the bridge repr()s it, so the JSON arrives
    wrapped in single quotes)."""
    raw = bridge_resp.get("result") if isinstance(bridge_resp, dict) else None
    if isinstance(raw, str) and len(raw) >= 2 and raw[0] == raw[-1] == "'":
        raw = raw[1:-1]
    try:
        return json.loads(raw) if isinstance(raw, str) else (raw or {})
    except Exception:
        return {}


def _parse_joint_articulation(bridge_resp: dict) -> dict:
    """Bridge exec envelope -> {frames_sampled, max_rot_delta_deg, errors} (fail-closed on junk)."""
    r = _bridge_json(bridge_resp)
    return {"frames_sampled": int(r.get("frames_sampled", 0)),
            "total_frames": r.get("total_frames"),
            "max_rot_delta_deg": r.get("joints") or {},
            "errors": (r.get("errors") or [])[:8]}


MODESHELL_MAP = "/Game/Wanefall/Maps/Wanefall_ModeShell_Prototype_01"
# The H1B2-calibrated display zone: PlayerStart+(x, -700, z). CleanStage at the old (400,0,0)
# spawn is un-photographable for the dark-violet rig (harsh sun, unlit backdrop: every manual-
# exposure bias either crushed the body or blew it out — probe-proven ladder 0..14.5EV). The
# ModeShell menu lighting at y-700 is the exact look the judge quorum is golden-calibrated on;
# x+250 keeps the spawnable clear of the saved RigShipValidationDisplay actors at x=0.
MODESHELL_SPAWN = (250.0, -700.0, 140.0)


def capture_active_character(anim=DEFAULT_ANIM, map_path=MODESHELL_MAP, spawn=MODESHELL_SPAWN,
                             exposure_bias=None):
    """H1B3 one-command lane: MRQ-render the ACTIVE roster character through `anim` at the proven
    ModeShell display-zone staging (scene auto exposure — MRQ ticks, so it adapts), sample
    per-joint articulation, and emit the identity-bound v2 artifacts."""
    from dimwit.pipelines.character_roster import active_humanoid_characters
    from dimwit.pipelines.validation import ROOT as RM_ROOT
    chars = active_humanoid_characters(RM_ROOT)
    if not chars:
        raise SystemExit("no active humanoid characters in the roster")
    token = chars[0].get("asset_id") or chars[0].get("asset_name")
    rig = f"/Game/Wanefall/Dimwit/CharactersRigged/{token}_Rig"
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "artifacts", "mrq_frames")
    os.makedirs(out_dir, exist_ok=True)
    for f in os.listdir(out_dir):
        if f.endswith(".png"):
            try: os.remove(os.path.join(out_dir, f))
            except OSError: pass
    print(f"[mrq] building sequence for {token} ({anim})...")
    b = build_capture_sequence(mesh=rig, abp=DEFAULT_ABP, anim=anim,
                               seq_name=f"MRQ_DeformProof_{token}",
                               spawn=spawn, exposure_bias=exposure_bias)
    built = _bridge_json(b)
    seq = built.get("seq")
    print(json.dumps(built, indent=2)[:600])
    if not seq:
        raise SystemExit(f"sequence build failed: {b}")
    _foreground_editor()
    print(f"[mrq] rendering {seq} ...")
    render_sequence(out_dir, seq=seq, map_path=map_path)
    n = _poll_frames(out_dir, timeout_s=300)
    print(f"[mrq] frames: {n}")
    if n < 8:
        raise SystemExit(f"render produced only {n} frames — is the editor foregrounded/not minimized?")
    ja = _parse_joint_articulation(sample_joint_articulation(anim=anim))
    print("[mrq] joint articulation:", json.dumps(ja, indent=2)[:500])
    m = emit_capture_artifacts_v2(out_dir, prefix="frame", n=n, asset_id=token, rig_asset=rig,
                                  anim=anim, stage=map_path.rsplit("/", 1)[-1],
                                  joint_articulation=ja)
    print(f"[mrq] motion: avg={m['avg_consecutive_delta']:.3f} max={m['max_consecutive_delta']:.3f} "
          f"advancing={m['advancing']}")
    return m


if __name__ == "__main__":
    capture_active_character()
