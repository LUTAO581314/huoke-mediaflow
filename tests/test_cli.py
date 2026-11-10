"""CLI 冒烟：命令能起来、参数解析正常、弃用命令还在但标注清楚。"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MF = ROOT / "mf.py"


def run(*args):
    return subprocess.run([sys.executable, str(MF), *args], capture_output=True, text=True, timeout=60)


def test_help_lists_commands():
    r = run("-h")
    assert r.returncode == 0
    for cmd in ["new", "dj", "export", "qc", "watch", "shot", "cover", "health"]:
        assert cmd in r.stdout
    assert "burn" not in r.stdout  # 烧字幕已删，字幕只在 D剪 做


def test_dj_subcommands():
    r = run("dj", "-h")
    assert r.returncode == 0
    for sub in ["check", "new", "import", "bind", "prune"]:
        assert sub in r.stdout


def test_bad_platform_fails_cleanly(tmp_path):
    proj = tmp_path / "20261111-测试"
    proj.mkdir()
    (proj / ".brand").write_text("品硕", encoding="utf-8")
    r = run("export", "/tmp/none.mp4", "-p", str(proj), "--platform", "bilibili")
    assert r.returncode != 0
    assert "平台只能是" in (r.stderr + r.stdout)
