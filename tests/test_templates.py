"""Multiplane 模板：存在、占位符能替换、不出残渣。"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import mf  # noqa: E402

TPL = Path(__file__).resolve().parent.parent / "shots"


def test_three_templates_exist():
    for n in ("title", "params", "endcard"):
        assert (TPL / f"{n}.html").is_file(), n


def test_substitution_leaves_no_placeholder():
    html = mf.tpl_html("title", {"TITLE": "视觉检测机", "KICKER": "机器视觉", "SUB": "东莞品硕"})
    assert "{{" not in html
    assert "视觉检测机" in html


def test_unknown_placeholder_is_cleared():
    html = mf.tpl_html("params", {"K1": "精度"})
    assert not re.search(r"\{\{[A-Z0-9_]+\}\}", html)


def test_endcard_cta_split_into_chars_and_accent():
    html = mf.tpl_html("endcard", {"CTA": "发图纸<br>*免费评估*"})
    assert html.count('class="ch"') == 7, html[:200]  # 发图纸 3 + 免费评估 4
    plain = re.sub(r"<[^>]+>", "", html)
    assert "免费评估" in plain
    assert 'style="color:var(--accent)"' in html


def test_templates_are_vertical_1080x1920():
    for n in ("title", "params", "endcard"):
        css = (TPL / f"{n}.html").read_text(encoding="utf-8")
        assert "width:1080px" in css and "height:1920px" in css


def test_templates_have_no_contact_or_price_words():
    import huoke_lint as L
    for n in ("title", "params", "endcard"):
        src = (TPL / f"{n}.html").read_text(encoding="utf-8")
        body = re.sub(r"<(style|script)[^>]*>.*?</\1>", " ", src, flags=re.S)   # CSS/JS 里的 100% 不算文案
        text = re.sub(r"<[^>]+>", " ", body)
        assert L.lint_text(text) == [], (n, L.lint_text(text))
