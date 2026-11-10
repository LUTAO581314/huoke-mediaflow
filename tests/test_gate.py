"""导出闸门：时间线里有违规就必须拒绝（--force 才放行）。"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import mf  # noqa: E402


def _proj(tmp_path, pid="p-test"):
    proj = tmp_path / "20261111-测试"
    proj.mkdir()
    (proj / ".djian.json").write_text(json.dumps({"id": pid, "name": proj.name, "canvas": {}}), encoding="utf-8")
    return proj


def _timeline(overlay_text):
    return {"timeline": {"meta": {}, "videoTracks": [{"clips": []}], "overlays": [{"type": "subtitle", "text": overlay_text}]}}


def test_dirty_timeline_blocks_export(tmp_path, monkeypatch):
    proj = _proj(tmp_path)
    monkeypatch.setattr(mf, "dj_api", lambda *a, **k: _timeline("加微信 abc12345 报价"))
    with pytest.raises(SystemExit):
        mf.lint_gate(proj)


def test_force_lets_it_through(tmp_path, monkeypatch, capsys):
    proj = _proj(tmp_path)
    monkeypatch.setattr(mf, "dj_api", lambda *a, **k: _timeline("全国最好"))
    mf.lint_gate(proj, force=True)          # 不抛异常
    assert "force" in capsys.readouterr().err


def test_clean_timeline_passes_silently(tmp_path, monkeypatch, capsys):
    proj = _proj(tmp_path)
    monkeypatch.setattr(mf, "dj_api", lambda *a, **k: _timeline("检测精度 0.05mm"))
    mf.lint_gate(proj)
    assert capsys.readouterr().err == ""


def test_engine_down_does_not_block_plain_transcode(tmp_path, monkeypatch):
    proj = _proj(tmp_path)
    def boom(*a, **k):
        raise SystemExit(1)     # dj_api 连不上时是 die()
    monkeypatch.setattr(mf, "dj_api", boom)
    mf.lint_gate(proj)           # 引擎不在就放行，交给 mf dj check
