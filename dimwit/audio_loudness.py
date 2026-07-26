"""ITU-R BS.1770 loudness + true-peak analysis for WAV assets — stdlib only.

Fail-closed measurement backing the AUDIO_FOUNDATION_V1 loudness gates. No numpy dependency; reads
PCM WAV via stdlib `wave`. Computes:
  - integrated (gated) loudness in LUFS via BS.1770 K-weighting (short assets fall back to an
    ungated momentary mean, flagged, since integrated gating is unstable under ~0.4 s);
  - true-peak estimate in dBTP via 4x linear oversampling (approx; conservative enough to gate a
    -1 dBTP ceiling);
  - sample-peak + RMS (for the digital-silence floor).

The K-weighting coefficients are the BS.1770 reference values specified at 48 kHz. For other sample
rates the filter is skipped and loudness is reported as unweighted RMS-dBFS with `kweighted=False`
recorded, so a gate can decide whether to trust it — never a silent wrong-weighting PASS.
"""
from __future__ import annotations

import math
import wave
from pathlib import Path

# BS.1770 K-weighting @ 48 kHz: stage 1 = high-shelf (+4 dB), stage 2 = high-pass (~38 Hz).
_PRE_B = (1.53512485958697, -2.69169618940638, 1.19839281085285)
_PRE_A = (1.0, -1.69065929318241, 0.73248077421585)
_HPF_B = (1.0, -2.0, 1.0)
_HPF_A = (1.0, -1.99004745483398, 0.99007225036621)
_ABS_GATE_LUFS = -70.0   # BS.1770 absolute gate
_SILENCE_FLOOR_DBFS = -60.0  # below this integrated level a WAV is treated as digital silence


def _biquad(x: list[float], b, a) -> list[float]:
    """Direct-form-I biquad. a[0] assumed 1.0."""
    y = [0.0] * len(x)
    x1 = x2 = y1 = y2 = 0.0
    b0, b1, b2 = b
    _, a1, a2 = a
    for i, xn in enumerate(x):
        yn = b0 * xn + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        y[i] = yn
        x2, x1 = x1, xn
        y2, y1 = y1, yn
    return y


def read_wav_mono(path: Path):
    """Return (samples[-1..1] mono float, sample_rate). Raises on unreadable / unsupported."""
    with wave.open(str(path), "rb") as w:
        n_ch = w.getnchannels()
        sw = w.getsampwidth()
        sr = w.getframerate()
        n = w.getnframes()
        raw = w.readframes(n)
    if sw == 2:
        import array
        a = array.array("h")
        a.frombytes(raw)
        norm = 32768.0
        data = [v / norm for v in a]
    elif sw == 1:
        data = [(b - 128) / 128.0 for b in raw]  # 8-bit unsigned
    elif sw == 4:
        import array
        a = array.array("i")
        a.frombytes(raw)
        data = [v / 2147483648.0 for v in a]
    else:
        raise ValueError(f"unsupported sample width {sw*8}-bit")
    if n_ch > 1:  # downmix to mono
        data = [sum(data[i:i + n_ch]) / n_ch for i in range(0, len(data), n_ch)]
    return data, sr


def _true_peak_dbtp(samples: list[float]) -> float:
    """4x linear-interpolation oversample -> max abs -> dBTP. Empty/silent -> -inf handled by caller."""
    peak = 0.0
    prev = samples[0] if samples else 0.0
    for s in samples:
        for k in range(1, 5):
            v = abs(prev + (s - prev) * (k / 4.0))
            if v > peak:
                peak = v
        prev = s
    return 20.0 * math.log10(peak) if peak > 0 else -math.inf


def analyze_wav(path: Path) -> dict:
    """Full measurement of one WAV. Never raises for musical content; raises only on unreadable file."""
    samples, sr = read_wav_mono(Path(path))
    if not samples:
        return {"ok": True, "lufs": -math.inf, "true_peak_dbtp": -math.inf, "sample_peak": 0.0,
                "rms_dbfs": -math.inf, "silent": True, "kweighted": False, "duration_s": 0.0,
                "gated": False}
    duration = len(samples) / float(sr) if sr else 0.0
    sample_peak = max(abs(s) for s in samples)

    kweighted = (sr == 48000)
    if kweighted:
        pre = _biquad(samples, _PRE_B, _PRE_A)
        filt = _biquad(pre, _HPF_B, _HPF_A)
    else:
        filt = samples  # unweighted fallback (flagged)

    # Mean square over 400 ms blocks (75% overlap) for gating; integrated = gated mean loudness.
    block = max(1, int(0.4 * sr))
    hop = max(1, block // 4)
    powers: list[float] = []
    i = 0
    while i + block <= len(filt):
        seg = filt[i:i + block]
        ms = sum(v * v for v in seg) / block
        powers.append(ms)
        i += hop
    gated = len(powers) >= 4  # need a few blocks for the relative gate to mean anything
    if not powers:  # asset shorter than one block: ungated whole-signal mean square
        ms = sum(v * v for v in filt) / len(filt)
        powers = [ms]

    def _loud(ms):  # BS.1770 loudness of a mean-square value
        return -0.691 + 10.0 * math.log10(ms) if ms > 0 else -math.inf

    block_lufs = [_loud(p) for p in powers]
    # absolute gate
    kept = [p for p, l in zip(powers, block_lufs) if l > _ABS_GATE_LUFS]
    if gated and kept:
        prelim = _loud(sum(kept) / len(kept))
        rel_gate = prelim - 10.0
        kept2 = [p for p, l in zip(powers, block_lufs) if l > _ABS_GATE_LUFS and l > rel_gate]
        integ = _loud(sum(kept2) / len(kept2)) if kept2 else prelim
    else:
        integ = _loud(sum(powers) / len(powers))

    rms = math.sqrt(sum(s * s for s in samples) / len(samples))
    rms_db = 20.0 * math.log10(rms) if rms > 0 else -math.inf
    return {
        "ok": True,
        "lufs": integ,
        "true_peak_dbtp": _true_peak_dbtp(samples),
        "sample_peak": sample_peak,
        "rms_dbfs": rms_db,
        "silent": (integ < _SILENCE_FLOOR_DBFS) or (sample_peak < 1e-4),
        "kweighted": kweighted,
        "gated": gated,
        "duration_s": duration,
        "sample_rate": sr,
    }
