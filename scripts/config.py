"""本地会议录音资料库的路径与配置。全部数据留在本机工作区。"""
from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent
else:
    ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "会议记录"
INBOX = DATA / "待处理"
AUDIO = DATA / "原始音频"
TRANSCRIPTS = DATA / "转写"
SUMMARIES = DATA / "总结"
INDEX = DATA / "索引.json"
SETTINGS = DATA / "设置.json"
SCAN_STATE = DATA / "扫描状态.json"

MODELS = ROOT / "模型"
SV_DIR = MODELS / "sensevoice"
SV_MODEL = SV_DIR / "model.int8.onnx"
SV_TOKENS = SV_DIR / "tokens.txt"
VAD_MODEL = MODELS / "silero_vad.onnx"

CORRECTIONS = ROOT / "同音纠错.txt"

LANGUAGE = "zh"
THREADS = 4
AUDIO_EXTS = {".m4a", ".mp3", ".wav", ".aac", ".ogg", ".opus", ".flac", ".wma", ".aiff"}


def ensure_dirs() -> None:
    for p in (INBOX, AUDIO, TRANSCRIPTS, SUMMARIES, MODELS, SV_DIR):
        p.mkdir(parents=True, exist_ok=True)


def fmt_ts(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"
