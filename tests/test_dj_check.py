"""`mf dj check` 开剪前体检：注册回归 —— 这里曾经必抛 NameError。

历史缺陷：cmd_dj() 里写的是 lint_timeline(tl, r)，而 r 只在 cmd_lint() 里有，
cmd_dj() 作用域内没有 r = rules()。结果这条"开剪前体检"每次走到底都崩，
56 条既有测试全绿（test_gate 只覆盖 lint_gate，没人调 cmd_dj）。
"""
import json
from argparse import Namespace

import pytest

import mf


def _proj(tmp_path, pid="p-check", brand="品硕"):
    proj = tmp_path / "20261111-体检"
    proj.mkdir()
    (proj / ".djian.json").write_text(
        json.dumps({"id": pid, "name": proj.name, "canvas": {"width": 1080, "height": 1920, "fps": 30}}),
        encoding="utf-8",
    )
    (proj / ".brand").write_text(brand, encoding="utf-8")
    return proj


def _args(proj):
    return Namespace(action="check", project=str(proj), files=[], session=None, yes=False, platform="dy")


def _fake_api(overlay_text):
    timeline = {"timeline": {"meta": {"width": 1080, "height": 1920, "fps": 30},
                             "videoTracks": [{"clips": []}], "overlays": []}}
    if overlay_text is not None:
        timeline["timeline"]["overlays"] = [{"type": "subtitle", "text": overlay_text}]

    def api(method, path, payload=None):
        assert method == "GET"
        if path.endswith("/timeline"):
            return timeline
        if path.endswith("/assets"):
            return {"assets": [{"id": "a1"}]}
        raise AssertionError(f"未预期的接口请求 {path}")

    return api


def test_check_clean_timeline_passes(tmp_path, monkeypatch, rules_file, capsys):
    """干净时间线要能走到底。修复前这里抛 NameError: name 'r' is not defined。"""
    proj = _proj(tmp_path)
    monkeypatch.setattr(mf, "dj_api", _fake_api("检测精度 0.05mm，发样品照片免费评估方案"))
    mf.cmd_dj(_args(proj))                     # 不抛异常即通过
    out = capsys.readouterr().out
    assert "合规检查：通过" in out
    assert "视频片段 0 条" in out


def test_check_dirty_timeline_blocks(tmp_path, monkeypatch, rules_file, capsys):
    """时间线里留手机号必须拦下并退 1（规范 §4 不联系方式）。"""
    proj = _proj(tmp_path)
    monkeypatch.setattr(mf, "dj_api", _fake_api("有问题打 13800138000"))
    with pytest.raises(SystemExit) as e:
        mf.cmd_dj(_args(proj))
    assert e.value.code == 1
    out = capsys.readouterr().out
    assert "合规检查不通过" in out
    assert "13800138000" in out


def test_check_absolute_claim_blocks(tmp_path, monkeypatch, rules_file, capsys):
    """绝对化用语同样拦下，且指出违规落在哪个字段。"""
    proj = _proj(tmp_path)
    monkeypatch.setattr(mf, "dj_api", _fake_api("全国最好"))
    with pytest.raises(SystemExit) as e:
        mf.cmd_dj(_args(proj))
    assert e.value.code == 1
    assert "overlays[0].text" in capsys.readouterr().out


def test_check_uses_rules_not_undefined_name(tmp_path, monkeypatch, rules_file):
    """禁用词来自剪辑规范 §9 而非硬编码：换一份规则，判定要跟着变。"""
    proj = _proj(tmp_path)
    monkeypatch.setattr(mf, "dj_api", _fake_api("顺德产区直供"))
    mf.cmd_dj(_args(proj))                     # 默认规则里没有"顺德"，放行

    r = json.loads(json.dumps(mf.rules()))     # 复制一份再改，别污染缓存
    r["banned_regex"] = [*r["banned_regex"], "顺德"]
    monkeypatch.setattr(mf, "_rules_cache", r)
    with pytest.raises(SystemExit) as e:
        mf.cmd_dj(_args(proj))
    assert e.value.code == 1


def test_check_without_project_arg_infers_cwd(tmp_path, monkeypatch, rules_file, capsys):
    """不给 -p 但在工程目录里：走真实的 project_dir(None) 按 cwd 推断。

    修复前 proj 停在 None，dj_state(None) 走 None / ".djian.json"
    抛 TypeError——这正是文档里「cd 到工程目录直接跑」的那条路径。
    """
    lib = tmp_path / "媒体库"
    proj = lib / "工程" / "20261111-体检"
    proj.mkdir(parents=True)
    (proj / ".djian.json").write_text(
        json.dumps({"id": "p-check", "name": proj.name, "canvas": {}}), encoding="utf-8")
    (proj / ".brand").write_text("品硕", encoding="utf-8")
    monkeypatch.setattr(mf, "LIB", lib)
    monkeypatch.setattr(mf, "dj_api", _fake_api("正常文案"))
    monkeypatch.chdir(proj)                                 # 真实 cwd 推断，不打桩 project_dir

    assert mf.project_dir(None) == proj                     # 先确认推断本身成立
    mf.cmd_dj(Namespace(action="check", project=None, files=[], session=None, yes=False, platform="dy"))
    assert "合规检查：通过" in capsys.readouterr().out
