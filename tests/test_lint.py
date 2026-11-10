"""合规硬拦截：绝对化 / 联系方式 / 报价 / 禁用词。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import huoke_lint as L  # noqa: E402


def kinds(text, rules=None):
    return sorted({v["kind"] for v in L.lint_text(text, rules)})


def test_clean_industrial_copy_passes():
    assert L.lint_text("检测精度 0.05mm，节拍 1200pcs/h，8 工位，20261111 上线") == []


def test_cta_passes():
    assert L.lint_text("发样品照片或图纸，厂家工程师按样品评估方案") == []


def test_phone_blocked():
    assert "contact" in kinds("欢迎致电 13812345678")


def test_landline_blocked():
    assert "contact" in kinds("电话 0769-88886666")


def test_wechat_blocked():
    assert "contact" in kinds("加微信 pinson2026 详聊")


def test_url_blocked():
    assert "contact" in kinds("详见 www.pinsontec.com")


def test_email_blocked():
    assert "contact" in kinds("mail: sales@pinsontec.com")


def test_price_blocked():
    assert "price" in kinds("这台机 30 万元")


def test_price_word_blocked():
    assert "price" in kinds("报价请联系")


def test_superlative_blocked():
    assert "absolute" in kinds("行业内最好的检测方案")


def test_exclusive_blocked():
    assert "absolute" in kinds("国内唯一一家能做到")


def test_banned_regex_from_rules():
    vs = L.lint_text("零误判", {"banned_regex": ["零误判"]})
    assert any(v["kind"] == "banned" for v in vs)


def test_timeline_scan_finds_overlay_text():
    tl = {"overlays": [
        {"type": "subtitle", "text": "加微信 abc12345"},
        {"type": "title", "text": "检测节拍 1200pcs/h"},
    ]}
    vs = L.lint_timeline(tl, {"banned_regex": []})
    assert len(vs) == 1 and vs[0]["where"].endswith("text")


def test_format_violations_is_readable():
    vs = L.lint_text("最先进，加微信 abc12345")
    out = L.format_violations(vs)
    assert "绝对化" in out and "联系方式" in out
