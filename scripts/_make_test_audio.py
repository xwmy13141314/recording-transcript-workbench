"""生成一段本机中文 TTS 测试音频，仅用于验证流水线是否跑通。

用法：
    python scripts/_make_test_audio.py

依赖 Windows 自带的 SAPI 语音（pyttsx3）。生成的音频落在
`会议记录/待处理/测试会议.wav`，再运行 process.py 即可走完整流程。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pyttsx3  # noqa: E402

from config import INBOX, ensure_dirs  # noqa: E402

TEXT = (
    "各位同事，今天我们讨论下个季度的预算。"
    "张三说，市场推广需要二十万元。"
    "李四认为，应该先把合同确定下来。"
    "我们决定本周五之前提交方案。"
    "还有一个问题，客户那边的报价谁来跟进？"
)


def main() -> None:
    ensure_dirs()
    engine = pyttsx3.init()
    zh = [v for v in engine.getProperty("voices") if "ZH-CN" in v.id]
    if zh:
        engine.setProperty("voice", zh[0].id)
    engine.setProperty("rate", 170)
    out = INBOX / "测试会议.wav"
    engine.save_to_file(TEXT, str(out))
    engine.runAndWait()
    print(out)


if __name__ == "__main__":
    main()
