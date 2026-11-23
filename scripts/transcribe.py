"""本机转写：ffmpeg 转 16k 单声道 wav → silero VAD 切句 → SenseVoice 识别。

全程在本机完成，音频不上传。借鉴 xiaoer-luyinka 的分块流式读法，长录音内存占用稳定。
"""
from __future__ import annotations

import re
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from config import (CORRECTIONS, LANGUAGE, SV_MODEL, SV_TOKENS, THREADS,
                    VAD_MODEL, fmt_ts)

SR = 16000
WINDOW = 512
_TAG = re.compile(r"<\|[^|]*\|>")


@dataclass
class Segment:
    start: float
    end: float
    text: str


def load_corrections() -> dict[str, str]:
    fixes: dict[str, str] = {}
    if not CORRECTIONS.exists():
        return fixes
    for line in CORRECTIONS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "→" not in line:
            continue
        wrong, right = (x.strip() for x in line.split("→", 1))
        if wrong and right:
            fixes[wrong] = right
    return fixes


def to_wav(src: Path, wav: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(src), "-ar", str(SR),
         "-ac", "1", "-c:a", "pcm_s16le", str(wav)],
        check=True,
    )


def audio_seconds(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


class Transcriber:
    def __init__(self, threads: int = THREADS, language: str = LANGUAGE) -> None:
        import sherpa_onnx as so

        self.so = so
        for p in (SV_MODEL, SV_TOKENS, VAD_MODEL):
            if not p.exists():
                raise FileNotFoundError(f"缺模型文件: {p}（先运行 python scripts/setup_models.py）")
        self.rec = so.OfflineRecognizer.from_sense_voice(
            model=str(SV_MODEL), tokens=str(SV_TOKENS), use_itn=True,
            num_threads=threads, language=language,
        )
        self.vad_cfg = so.VadModelConfig(
            silero_vad=so.SileroVadModelConfig(
                model=str(VAD_MODEL), threshold=0.5, min_silence_duration=0.5,
                min_speech_duration=0.25, window_size=WINDOW, max_speech_duration=20,
            ),
            sample_rate=SR,
        )
        self.fixes = load_corrections()

    def _recognize(self, samples: np.ndarray) -> str:
        s = self.rec.create_stream()
        s.accept_waveform(SR, samples)
        self.rec.decode_stream(s)
        text = _TAG.sub("", s.result.text).strip()
        for wrong, right in self.fixes.items():
            text = text.replace(wrong, right)
        return text

    def segments(self, wav_path: Path, progress=None) -> list[Segment]:
        vad = self.so.VoiceActivityDetector(self.vad_cfg, buffer_size_in_seconds=120)
        out: list[Segment] = []
        with wave.open(str(wav_path), "rb") as w:
            if w.getframerate() != SR or w.getnchannels() != 1 or w.getsampwidth() != 2:
                raise ValueError("需要 16k 单声道 16bit wav")
            total = w.getnframes()
            read = 0
            pending = np.zeros(0, dtype=np.float32)
            while True:
                raw = w.readframes(SR * 30)
                eof = not raw
                if raw:
                    read += len(raw) // 2
                    chunk = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768
                    pending = np.concatenate([pending, chunk])
                    usable = len(pending) - len(pending) % WINDOW
                    for i in range(0, usable, WINDOW):
                        vad.accept_waveform(pending[i:i + WINDOW])
                    pending = pending[usable:]
                else:
                    if len(pending):
                        vad.accept_waveform(np.pad(pending, (0, WINDOW - len(pending))))
                    vad.flush()
                while not vad.empty():
                    seg = vad.front
                    start = seg.start / SR
                    samples = np.array(seg.samples, dtype=np.float32)
                    vad.pop()
                    text = self._recognize(samples)
                    if text:
                        out.append(Segment(start, start + len(samples) / SR, text))
                if progress:
                    progress(read, total)
                if eof:
                    break
        return out


def to_markdown(title: str, segs: list[Segment], meta: dict[str, str] | None = None,
                gap: float = 2.0, max_sec: float = 60, max_chars: int = 200) -> str:
    lines = [f"# {title}", ""]
    for k, v in (meta or {}).items():
        lines.append(f"- {k}: {v}")
    if meta:
        lines.append("")
    para: list[Segment] = []

    def flush() -> None:
        if para:
            lines.append(f"**[{fmt_ts(para[0].start)}]** " + "".join(s.text for s in para))
            lines.append("")
            para.clear()

    for s in segs:
        if para and (s.start - para[-1].end > gap
                     or (max_sec and s.end - para[0].start > max_sec)
                     or (max_chars and sum(len(x.text) for x in para) + len(s.text) > max_chars)):
            flush()
        para.append(s)
    flush()
    if not segs:
        lines.append("(没有识别到说话)")
    return "\n".join(lines).rstrip() + "\n"
