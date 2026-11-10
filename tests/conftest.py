import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import mf  # noqa: E402

FIXTURE_RULES = {
    "version": 1,
    "canvas": {
        "vertical": [1080, 1920, 30],
        "horizontal": [1920, 1080, 30],
        "cover_34": [1080, 1440],
    },
    "platforms": {
        "dy": {"canvas": "vertical", "duration": [30, 45]},
        "sph": {"canvas": "vertical", "duration": [30, 45]},
        "ks": {"canvas": "vertical", "duration": [30, 45]},
        "xhs": {"canvas": "vertical", "duration": [30, 45]},
        "tk": {"canvas": "vertical", "duration": [30, 45]},
        "yt": {"canvas": "horizontal", "duration": [30, 60]},
        "li": {"canvas": "horizontal", "duration": [30, 60]},
    },
    "duration": {"min": 30, "max": 45},
    "shot_seconds": [1.5, 4],
    "transitions": {"max_per_film": 1, "allowed": ["dissolve", "fadeBlack"]},
    "subtitles": {
        "engine": "djian",
        "font_size_px": [50, 56],
        "bottom_margin_px": 240,
        "stroke": True,
        "box": False,
        "max_cn_chars": 15,
    },
    "audio": {"music": [0.2, 0.3], "lufs": -14, "tolerance": 1.5, "true_peak_max": -1.5},
    "naming": {"code_pattern": "^(PS|HH)-[A-Z]+-\\d{8}-\\d{2}$"},
    "banned_regex": ["最", "第一", "唯一", "100%", "零误判", "电话", "微信", "二维码"],
}


@pytest.fixture
def rules_file(tmp_path, monkeypatch):
    """把 mf.RULES_MD 指到临时规则文件，规则内容写两份 json 块验证“取最后一块”。"""
    p = tmp_path / "剪辑规范.md"
    p.write_text(
        "# 剪辑规范\n\n旧参数：\n\n```json\n{\"version\": 0, \"platforms\": {}}\n```\n\n## §9 机器参数\n\n"
        "```json\n" + json.dumps(FIXTURE_RULES, ensure_ascii=False) + "\n```\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(mf, "RULES_MD", p)
    monkeypatch.setattr(mf, "_rules_cache", None)
    return p
