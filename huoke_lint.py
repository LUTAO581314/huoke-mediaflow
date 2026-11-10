"""剪辑合规硬拦截（剪辑规范 §4/§7 的机器执行版）。

persona 只能"提醒"，这里是"拦住"：绝对化用语、联系方式、报价、品牌串流。
用在两个地方：`mf dj check`（开剪前体检）和 `mf export`（成片前的最后一道闸）。
"""
from __future__ import annotations

import re

# 联系方式：留一个电话/微信号，平台就限流，私域也白做
CONTACT = [
    (r"1[3-9]\d{9}", "手机号"),
    (r"(?<!\d)0\d{2,3}[-\s]?\d{7,8}(?!\d)", "座机号"),
    (r"(微信|威信|卫信|V信|vx|VX|weixin|WeChat|企微|企业微信|QQ|扣扣)\s*[:：号]?\s*[A-Za-z0-9_-]{4,}", "微信/QQ"),
    (r"[\w.+-]+@[\w-]+\.[\w.]{2,}", "邮箱"),
    (r"https?://|www\.", "网址"),
    (r"二维码|扫码|扫一扫", "二维码"),
]

# 我方不报价：价格、交期、成交都归企业
PRICE = [
    (r"(报价|价格|单价|多少钱|优惠|打折|折扣|包邮|返点)", "报价/价格"),
    (r"[￥¥]\s*\d", "货币符号"),
    (r"\d+(\.\d+)?\s*(万元|元|块|RMB|人民币)", "价格数字"),
    (r"(交期|货期|工期)\s*\d+\s*(天|日|周|月)", "交期"),
]

# 绝对化用语（广告法第八条 + 平台规则）
ABSOLUTE = [
    (r"最(好|佳|优|先进|领先|低|高|快|便宜|新|强)", "最X"),
    (r"(第一|唯一|独家|顶级|顶尖|世界级|国家级|国家级|国际领先|行业领先|遥遥领先)", "排他/顶级"),
    (r"(100%|百分之百|100％)", "100%"),
    (r"(零误判|零缺陷|零漏检|绝对|保证|永久|永不|彻底杜绝)", "绝对承诺"),
]

DEFAULT_RULES = {
    "banned_regex": ["最", "第一", "唯一", "100%", "零误判", "电话", "微信", "二维码"],
}

# 时间线里算"对外文案"的字段名（其余字段是机器参数，不查）
TEXT_KEYS = {"text", "title", "subtitle", "label", "caption", "content", "tex", "name", "placeholder", "tag", "value"}


def _scan(text: str, patterns, kind: str, where: str) -> list[dict]:
    out = []
    for pat, why in patterns:
        for m in re.finditer(pat, text):
            out.append({"kind": kind, "why": why, "match": m.group(0), "where": where, "text": text[:90]})
    return out


def lint_text(text: str, rules: dict | None = None, where: str = "") -> list[dict]:
    """查一段文案。返回违规项列表（空 = 通过）。"""
    if not isinstance(text, str) or not text.strip():
        return []
    rules = rules or DEFAULT_RULES
    out = []
    out += _scan(text, CONTACT, "contact", where)
    out += _scan(text, PRICE, "price", where)
    out += _scan(text, ABSOLUTE, "absolute", where)
    for b in rules.get("banned_regex") or []:
        if b and b in text:
            out.append({"kind": "banned", "why": f"禁用词「{b}」", "match": b, "where": where, "text": text[:90]})
    return out


def iter_texts(node, path="") -> list[tuple[str, str]]:
    """把时间线 JSON 里所有对外文案抠出来（含字幕/标题/图形内文字/图表标签）。"""
    got = []
    if isinstance(node, dict):
        for k, v in node.items():
            here = f"{path}.{k}" if path else k
            if isinstance(v, str) and k in TEXT_KEYS:
                got.append((here, v))
            else:
                got += iter_texts(v, here)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            got += iter_texts(v, f"{path}[{i}]")
    return got


def lint_timeline(timeline: dict, rules: dict | None = None) -> list[dict]:
    """查整条时间线。"""
    rules = rules or DEFAULT_RULES
    out = []
    for where, text in iter_texts(timeline or {}):
        out += lint_text(text, rules, where)
    return out


def format_violations(vs: list[dict]) -> str:
    icon = {"contact": "联系方式", "price": "报价", "absolute": "绝对化", "banned": "禁用词"}
    lines = []
    for v in vs:
        lines.append(f"  [{icon.get(v['kind'], v['kind'])}] {v['why']}：{v['match']!r}  ← {v['where']}「{v['text']}」")
    return "\n".join(lines)
