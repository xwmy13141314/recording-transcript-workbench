"""本机设置与录音目录扫描：全部读写本机文件，不联网。"""
from __future__ import annotations

import json
import time
from contextlib import contextmanager
from pathlib import Path

from config import AUDIO_EXTS, DATA, INDEX, SCAN_STATE, SETTINGS, ensure_dirs

_INDEX_LOCK = DATA / "索引.lock"


@contextmanager
def index_lock(timeout: float = 30.0):
    """本机文件锁：串行化索引写入，避免并发处理丢失数据。"""
    deadline = time.time() + timeout
    while True:
        try:
            _INDEX_LOCK.mkdir(exist_ok=False)
            break
        except FileExistsError:
            if time.time() > deadline:
                raise TimeoutError("索引被其他任务占用超时")
            time.sleep(0.1)
    try:
        yield
    finally:
        try:
            _INDEX_LOCK.rmdir()
        except OSError:
            pass


def mutate_index(fn) -> dict:
    """在文件锁内读取-修改-写入索引，保证并发安全。"""
    with index_lock():
        idx = {"version": 1, "meetings": []}
        if INDEX.exists():
            try:
                idx = json.loads(INDEX.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        result = fn(idx)
        tmp = INDEX.with_suffix(".tmp")
        tmp.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(INDEX)
        return result if result is not None else idx

DEFAULTS = {
    "record_dir": "",          # 用户选择的录音目录；空则用默认待处理目录
    "auto_scan": True,
    "scan_interval": 5,        # 分钟
    "on_new": "prompt",        # prompt=提示手动处理 / auto=自动处理
    "scan_subdirs": True,
    "theme": "light",          # light / dark / system
    "font_scale": 1.0,
    "cloud_enabled": False,    # 云端总结开关（默认关，本地规则回退）
    "cloud_provider": "siliconflow",
    "cloud_api_key": "",
    "cloud_model": "Qwen/Qwen2.5-7B-Instruct",
    "cloud_base": "https://api.siliconflow.cn/v1",
}

# 扫描间隔可选项（分钟）
SCAN_INTERVALS = [1, 5, 10, 30, 60]


def load_settings() -> dict:
    ensure_dirs()
    cfg = dict(DEFAULTS)
    if SETTINGS.exists():
        try:
            cfg.update(json.loads(SETTINGS.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass
    return cfg


def public_settings(cfg: dict | None = None) -> dict:
    """脱敏后的设置：绝不回传 API Key，只告知「是否已配置」。

    界面、内嵌 HTML、日志都只应使用这一份，避免密钥被写进可分享的文件。
    """
    out = dict(cfg or load_settings())
    key = (out.pop("cloud_api_key", "") or "").strip()
    out["cloud_key_set"] = bool(key)
    out["cloud_api_key"] = ""
    return out


def save_settings(cfg: dict) -> dict:
    """保存设置。cloud_api_key 传空表示「不修改」，传 clear_cloud_key 才真正清除。"""
    ensure_dirs()
    incoming = dict(cfg or {})
    current = load_settings()
    if incoming.pop("clear_cloud_key", False):
        incoming["cloud_api_key"] = ""
    elif not (incoming.get("cloud_api_key") or "").strip():
        incoming["cloud_api_key"] = current.get("cloud_api_key", "")
    incoming.pop("cloud_key_set", None)
    merged = dict(DEFAULTS)
    merged.update(current)          # 保留未提交的字段，避免部分保存把设置清空
    merged.update(incoming)
    tmp = SETTINGS.with_suffix(".tmp")
    tmp.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(SETTINGS)
    return public_settings(merged)


def record_dir_path(cfg: dict | None = None) -> Path:
    cfg = cfg or load_settings()
    raw = (cfg.get("record_dir") or "").strip()
    if raw and Path(raw).exists():
        return Path(raw)
    return DATA / "待处理"


def load_scan_state() -> dict:
    if SCAN_STATE.exists():
        try:
            return json.loads(SCAN_STATE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"files": {}}


def save_scan_state(state: dict) -> None:
    ensure_dirs()
    tmp = SCAN_STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(SCAN_STATE)


def _is_audio(p: Path) -> bool:
    return p.is_file() and p.suffix.lower() in AUDIO_EXTS


def scan_recordings(cfg: dict | None = None) -> dict:
    """扫描录音目录，返回新录音列表（按路径+大小去重）。"""
    cfg = cfg or load_settings()
    root = record_dir_path(cfg)
    state = load_scan_state()
    known = state.get("files", {})
    found = []
    if root.exists():
        it = root.rglob("*") if cfg.get("scan_subdirs") else root.glob("*")
        for p in it:
            if not _is_audio(p):
                continue
            key = f"{p}|{p.stat().st_size}"
            if key in known:
                continue
            found.append({
                "key": key,
                "name": p.name,
                "path": str(p),
                "size": p.stat().st_size,
                "mtime": p.stat().st_mtime,
            })
    found.sort(key=lambda x: x["mtime"], reverse=True)
    return {
        "dir": str(root),
        "record_dir": cfg.get("record_dir") or "",
        "new": found,
        "new_count": len(found),
        "last_scan": state.get("last_scan", ""),
        "auto_scan": cfg.get("auto_scan", True),
        "scan_interval": cfg.get("scan_interval", 5),
        "on_new": cfg.get("on_new", "prompt"),
        "scan_subdirs": cfg.get("scan_subdirs", True),
    }


def mark_scanned(keys: list[str]) -> None:
    state = load_scan_state()
    from datetime import datetime
    for k in keys:
        state.setdefault("files", {})[k] = {"at": datetime.now().isoformat(timespec="seconds")}
    state["last_scan"] = datetime.now().isoformat(timespec="seconds")
    save_scan_state(state)


def clear_state() -> None:
    save_scan_state({"files": {}, "last_scan": ""})
