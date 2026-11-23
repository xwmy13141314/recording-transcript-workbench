"""处理待处理目录里的手机录音：本机转写 → 本地摘要 → Markdown 存档 → 更新索引。

用法：
    python scripts/process.py            # 处理一次待处理目录里的所有新文件
    python scripts/process.py --watch    # 常驻，每 20 秒检查一次新文件
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import tempfile
import time
from datetime import datetime
from pathlib import Path

from settings import mutate_index  # noqa: E402

from config import (AUDIO, AUDIO_EXTS, DATA, INDEX, INBOX, SUMMARIES,
                    TRANSCRIPTS, fmt_ts, ensure_dirs)
from summarize import summarize
from transcribe import Transcriber, audio_seconds, to_markdown, to_wav


def safe_name(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip() or "未命名"


def load_index() -> dict:
    if INDEX.exists():
        try:
            return json.loads(INDEX.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print("索引文件损坏，重建空索引。")
    return {"version": 1, "meetings": []}


def save_index(idx: dict) -> None:
    tmp = INDEX.with_suffix(".tmp")
    tmp.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(INDEX)


def process_one(src: Path, transcriber: Transcriber, idx: dict) -> bool:
    st = src.stat()
    for m in idx["meetings"]:
        if m["source"] == src.name and m["size"] == st.st_size:
            print(f"跳过已处理: {src.name}")
            return False

    mtime = datetime.fromtimestamp(st.st_mtime)
    day = mtime.strftime("%Y-%m-%d")
    stamp = mtime.strftime("%Y%m%d_%H%M%S")
    title = safe_name(src.stem)
    base = f"{day}_{stamp}_{title}"

    print(f"\n处理: {src.name} ({st.st_size / 1e6:.1f} MB)")
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "audio.wav"
        to_wav(src, wav)
        duration = audio_seconds(wav) or audio_seconds(src)
        print(f"  时长 {fmt_ts(duration)}，开始本机转写...")
        t0 = time.time()
        last = [0.0]

        def progress(done: int, total: int) -> None:
            now = time.time()
            if now - last[0] > 5:
                last[0] = now
                print(f"  转写 {done * 100 // max(total, 1)}%", flush=True)

        segs = transcriber.segments(wav, progress)
        print(f"  转写完成：{len(segs)} 句，耗时 {time.time() - t0:.0f} 秒")

    meta = {
        "日期": day,
        "时长": fmt_ts(duration),
        "原文件": src.name,
        "转写方式": "本机 SenseVoice，未上传音频",
    }
    transcript_name = base + ".md"
    transcript = TRANSCRIPTS / transcript_name
    transcript.write_text(to_markdown(title, segs, meta), encoding="utf-8")

    summary_name = base + ".md"
    summary = SUMMARIES / summary_name
    summary.write_text(summarize(segs, title, transcript_name), encoding="utf-8")

    archive_dir = AUDIO / day
    archive_dir.mkdir(parents=True, exist_ok=True)
    archived = archive_dir / src.name
    if archived.exists():
        archived = archive_dir / f"{stamp}_{src.name}"
    shutil.move(str(src), str(archived))

    entry = {
        "id": base,
        "title": title,
        "date": day,
        "time": mtime.strftime("%H:%M:%S"),
        "duration": round(duration, 1),
        "size": st.st_size,
        "source": src.name,
        "audio": str(archived.relative_to(DATA)),
        "transcript": str(transcript.relative_to(DATA)),
        "summary": str(summary.relative_to(DATA)),
        "segments": [{"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text} for s in segs],
    }

    def _merge(latest: dict):
        ids = {m.get("id") for m in latest.get("meetings", [])}
        if base not in ids:
            latest.setdefault("meetings", []).append(entry)

    mutate_index(_merge)
    if entry not in idx["meetings"]:
        idx["meetings"].append(entry)
    print(f"  已存档: {transcript.name} / {summary.name}")
    return True


def scan_once(transcriber: Transcriber, idx: dict) -> int:
    ensure_dirs()
    files = sorted(p for p in INBOX.iterdir()
                   if p.is_file() and p.suffix.lower() in AUDIO_EXTS)
    if not files:
        return 0
    n = 0
    for f in files:
        try:
            if process_one(f, transcriber, idx):
                n += 1
        except Exception as exc:  # noqa: BLE001 — 单个文件失败不影响其他
            print(f"  处理失败 {f.name}: {exc}")
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description="本机处理会议录音")
    ap.add_argument("--watch", action="store_true", help="常驻监控待处理目录")
    args = ap.parse_args()
    ensure_dirs()
    idx = load_index()
    print("加载本机转写模型...")
    transcriber = Transcriber()
    while True:
        n = scan_once(transcriber, idx)
        print(f"本轮处理 {n} 个新录音。")
        if not args.watch:
            break
        time.sleep(20)


if __name__ == "__main__":
    main()
