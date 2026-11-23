"""下载本地转写模型（ SenseVoice int8 + tokens + silero VAD ），支持断点续传和镜像。

用法：
    python scripts/setup_models.py
"""
from __future__ import annotations

import time
import urllib.request
from pathlib import Path

from config import SV_DIR, SV_MODEL, SV_TOKENS, VAD_MODEL, ensure_dirs

_SV = "csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/resolve/main/"
FILES = {
    "sensevoice/model.int8.onnx": (
        239233841,
        ["https://huggingface.co/" + _SV + "model.int8.onnx",
         "https://hf-mirror.com/" + _SV + "model.int8.onnx"],
    ),
    "sensevoice/tokens.txt": (
        315894,
        ["https://huggingface.co/" + _SV + "tokens.txt",
         "https://hf-mirror.com/" + _SV + "tokens.txt"],
    ),
    "silero_vad.onnx": (
        643854,
        ["https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx",
         "https://hf-mirror.com/csukuangfj/sherpa-onnx-vad-silero/resolve/main/silero_vad.onnx"],
    ),
}
TARGETS = {
    "sensevoice/model.int8.onnx": SV_MODEL,
    "sensevoice/tokens.txt": SV_TOKENS,
    "silero_vad.onnx": VAD_MODEL,
}


def missing() -> list[str]:
    return [k for k, p in TARGETS.items()
            if not (p.exists() and p.stat().st_size == FILES[k][0])]


def _fetch(url: str, dst: Path, size: int) -> None:
    part = dst.with_name(dst.name + ".part")
    have = part.stat().st_size if part.exists() else 0
    req = urllib.request.Request(url, headers={"Range": f"bytes={have}-"} if have else {})
    with urllib.request.urlopen(req, timeout=60) as r:
        if have and r.status != 206:
            have = 0
        with open(part, "ab" if have else "wb") as f:
            last = 0.0
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                have += len(chunk)
                now = time.time()
                if now - last > 2:
                    last = now
                    print(f"  {dst.name}: {have / 1e6:.1f}/{size / 1e6:.1f} MB", flush=True)
    if part.stat().st_size != size:
        raise IOError(f"{dst.name} 大小不对: {part.stat().st_size} != {size}")
    part.replace(dst)


def main() -> None:
    ensure_dirs()
    todo = missing()
    if not todo:
        print("模型已齐全，无需下载。")
        return
    print(f"需要下载 {len(todo)} 个模型文件，合计约 {(sum(FILES[k][0] for k in todo) / 1e6):.0f} MB。")
    for key in todo:
        size, urls = FILES[key]
        dst = TARGETS[key]
        dst.parent.mkdir(parents=True, exist_ok=True)
        errors = []
        for url in urls:
            for attempt in range(3):
                try:
                    _fetch(url, dst, size)
                    break
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{url}: {exc}")
                    time.sleep(2)
            if dst.exists():
                break
        if not dst.exists():
            raise RuntimeError(f"{key} 下载失败:\n" + "\n".join(errors[-3:]))
        print(f"完成: {dst}")
    print("本地模型准备完毕，之后转写完全离线。")


if __name__ == "__main__":
    main()
