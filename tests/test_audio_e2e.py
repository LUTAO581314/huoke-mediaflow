"""端到端：真的跑 ffmpeg，测响度归一 + qc 读数（CI 上也有 ffmpeg）。"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import mf  # noqa: E402

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="没有 ffmpeg")


def _tone(path, gain="0.1"):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                    "-i", f"sine=frequency=440:duration=3", "-af", f"volume={gain}",
                    "-c:a", "aac", "-b:a", "192k", str(path)], check=True)
    return path


def test_loudnorm_hits_minus14(tmp_path):
    src = _tone(tmp_path / "tone.m4a")
    out = tmp_path / "norm.m4a"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-af",
                    "loudnorm=I=-14:TP=-1.5:LRA=11:linear=true", "-c:a", "aac", "-b:a", "192k", str(out)], check=True)
    rep = mf.qc(str(out))
    assert rep["LUFS"] is not None, rep
    assert abs(rep["LUFS"] - (-14)) <= 1.0, rep
    assert rep["ok"] is True, rep


def test_qc_sees_quiet_audio_as_offtarget(tmp_path):
    src = _tone(tmp_path / "quiet.m4a", gain="0.01")
    rep = mf.qc(str(src))
    assert rep["LUFS"] < -20, rep
    assert rep["ok"] is False, rep
