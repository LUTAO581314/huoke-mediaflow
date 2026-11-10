"""规则解析、画布、平台别名、编号、品牌隔离——都不碰网络和真机。"""
import json
import re
from pathlib import Path

import pytest

import mf


def test_rules_takes_last_json_block(rules_file):
    r = mf.rules()
    assert r["version"] == 1
    assert r["canvas"]["vertical"] == [1080, 1920, 30]


def test_rules_missing_file_exits(tmp_path, monkeypatch):
    monkeypatch.setattr(mf, "RULES_MD", tmp_path / "nope.md")
    monkeypatch.setattr(mf, "_rules_cache", None)
    with pytest.raises(SystemExit):
        mf.rules()


def test_rules_without_json_block_exits(tmp_path, monkeypatch):
    p = tmp_path / "empty.md"
    p.write_text("# 剪辑规范\n\n没有机器参数块", encoding="utf-8")
    monkeypatch.setattr(mf, "RULES_MD", p)
    monkeypatch.setattr(mf, "_rules_cache", None)
    with pytest.raises(SystemExit):
        mf.rules()


@pytest.mark.parametrize(
    "raw,want",
    [("dy", "dy"), ("douyin", "dy"), ("抖音", "dy"), ("xhs", "xhs"), ("RedNote", "xhs"),
     ("tk", "tk"), ("tiktok", "tk"), ("shorts", "tk"), ("sph", "sph"), ("视频号", "sph")],
)
def test_plat_aliases(rules_file, raw, want):
    assert mf.plat(raw) == want


def test_plat_rejects_unknown(rules_file):
    with pytest.raises(SystemExit):
        mf.plat("bilibili")


def test_canvas_vertical_and_horizontal(rules_file):
    assert mf.canvas_of("dy") == {"width": 1080, "height": 1920, "fps": 30}
    assert mf.canvas_of("youtube") == {"width": 1920, "height": 1080, "fps": 30}
    assert mf.canvas_of(None)["width"] == 1080  # 默认竖屏


@pytest.mark.parametrize(
    "brand,code,ok",
    [("品硕", "PS-DY-20261111-01", True), ("晖华", "HH-DY-20261111-01", True),
     ("晖华", "PS-DY-20261111-01", False), ("品硕", "PS-dy-20261111-01", False),
     ("品硕", "PS-DY-2026111-01", False), ("品硕", "PS-DY-20261111-1", False),
     ("品硕", "", False), ("品硕", None, False)],
)
def test_code_ok(brand, code, ok):
    assert mf.code_ok(brand, code) is ok


def test_project_name_no_double_date():
    assert re.match(r"^\d{8}-联调$", mf.project_name("联调"))
    assert mf.project_name("20261111-联调") == "20261111-联调"


def test_brand_isolation(rules_file, tmp_path):
    """品硕工程里塞晖华素材必须拒绝（剪辑规范 §4.1）。"""
    proj = tmp_path / "20261111-测试"
    proj.mkdir()
    (proj / ".brand").write_text("品硕", encoding="utf-8")
    with pytest.raises(SystemExit):
        mf.check_brand(proj, Path("/素材/源片/晖华/a.mp4"))
    assert mf.check_brand(proj, Path("/素材/源片/品硕/b.mp4"))


def test_banned_words_are_in_rules(rules_file):
    """规范里的禁用词必须覆盖联系方式与绝对化用语。"""
    words = mf.rules()["banned_regex"]
    for w in ["最", "第一", "100%", "电话", "微信"]:
        assert w in words


def test_repo_rules_copy_parses():
    """仓库里的规范副本也要能解析（防止文档改坏）。"""
    p = Path(__file__).resolve().parents[1] / "docs" / "剪辑规范.md"
    if not p.exists():
        pytest.skip("仓库未带规范副本")
    blocks = re.findall(r"```json\s*(.*?)```", p.read_text(encoding="utf-8"), re.S)
    r = json.loads(blocks[-1])
    for key in ["canvas", "platforms", "shot_seconds", "subtitles", "audio", "naming"]:
        assert key in r, f"规范 §9 缺 {key}"
