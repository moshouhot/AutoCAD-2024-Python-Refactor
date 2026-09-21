from __future__ import annotations

from pathlib import Path

from acad_portable.config import FeatureConfig
from acad_portable.textio import read_legacy_text


def test_read_utf8_and_feature_config(tmp_path: Path) -> None:
    path = tmp_path / "config.txt"
    path.write_text("安装 VBA编程=1\n桌面快捷方式=0\n", encoding="utf-8")

    text, encoding = read_legacy_text(path)
    assert "安装 VBA编程=1" in text
    assert encoding == "utf-8"

    config = FeatureConfig.load(path)
    assert config.enabled("安装 VBA编程") is True
    assert config.enabled("桌面快捷方式") is False


def test_read_gb18030_config(tmp_path: Path) -> None:
    path = tmp_path / "配置.txt"
    path.write_bytes("检测 NET安装=1\r\n安装 VBA编程=0\r\n".encode("gb18030"))

    config = FeatureConfig.load(path)
    assert config.encoding == "gb18030"
    assert config.enabled("检测 NET安装") is True
    assert config.enabled("安装 VBA编程") is False

