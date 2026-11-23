"""录音转写工作台 · 桌面应用（原生窗口，非浏览器网页）。

数据与音频全部来自本机；通过本地 API 与界面通信，不联网。
打包：见 打包exe.bat / 使用说明.md
"""
from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path

import webview

if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent
    SCRIPTS = ROOT / "scripts"
else:
    SCRIPTS = Path(__file__).resolve().parent
    ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from config import DATA, INBOX, ensure_dirs  # noqa: E402
from build_app import build_payload  # noqa: E402 — 顶层导入，确保打包进 exe
import cloud_summary  # noqa: E402,F401 — 顶层导入，确保打包进 exe
from settings import (  # noqa: E402
    load_settings, public_settings, save_settings, scan_recordings, mark_scanned,
    record_dir_path,
)

APP_NAME = "录音转写工作台"
WINDOW = None
LOG = DATA / "启动日志.txt"

PROCESS_STATE = {"running": False, "done": 0, "total": 0, "current": "", "message": ""}
PROCESS_LOCK = threading.Lock()
CLOUD_STATE = {"running": False, "done": 0, "total": 1, "current": "", "message": ""}
CLOUD_LOCK = threading.Lock()


def log(msg: str) -> None:
    try:
        ensure_dirs()
        with LOG.open("a", encoding="utf-8") as f:
            from datetime import datetime
            f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")
    except Exception:
        pass


class Api:
    """暴露给前端的本地 API。所有方法只操作本机文件。"""

    def get_data(self) -> str:
        try:
            return json.dumps(build_payload(), ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001
            log(f"get_data 失败: {exc}")
            return json.dumps({"meetings": [], "audioBase": str(DATA), "error": str(exc)}, ensure_ascii=False)

    def get_settings(self) -> str:
        try:
            return json.dumps(public_settings(), ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc)}, ensure_ascii=False)

    def cloud_summarize(self, meeting_id: str) -> str:
        """后台线程用云端模型重写某场会议的总结，立即返回；用 cloud_status 轮询。

        与录音处理互不阻塞：两者用不同状态，索引写入由文件锁串行化。
        """
        with CLOUD_LOCK:
            if CLOUD_STATE["running"]:
                return json.dumps({"started": False, "error": "已有云端总结在进行中"}, ensure_ascii=False)
            CLOUD_STATE.update(running=True, done=0, total=1, current="", message="准备云端总结…")
        threading.Thread(target=self._cloud_worker, args=(meeting_id,), daemon=True).start()
        return json.dumps({"started": True}, ensure_ascii=False)

    def cloud_status(self) -> str:
        with CLOUD_LOCK:
            return json.dumps(dict(CLOUD_STATE), ensure_ascii=False)

    def _cloud_worker(self, meeting_id: str) -> None:
        try:
            from cloud_summary import summarize_remote, to_markdown, attach_speakers
            from config import INDEX
            from settings import mutate_index

            idx = json.loads(INDEX.read_text(encoding="utf-8")) if INDEX.exists() else {"meetings": []}
            m = next((x for x in idx.get("meetings", []) if x.get("id") == meeting_id), None)
            if not m:
                raise RuntimeError("找不到会议")
            with CLOUD_LOCK:
                CLOUD_STATE["message"] = "云端总结中（仅文字）…"
            obj = summarize_remote(m.get("segments", []))
            md = to_markdown(obj, m.get("title", ""), m.get("segments", []))
            spath = DATA / m.get("summary", "")
            spath.parent.mkdir(parents=True, exist_ok=True)
            spath.write_text(md, encoding="utf-8")
            inferred = obj.get("speakers") or []
            segs = attach_speakers(m.get("segments", []), obj)
            speaker_map = {i: s["speaker"] for i, s in enumerate(segs) if s.get("speaker")}

            def _merge(latest: dict):
                target = next((x for x in latest.get("meetings", []) if x.get("id") == meeting_id), None)
                if not target:
                    return
                target["cloud_summary"] = True
                target["speakers_inferred"] = inferred
                for i, name in speaker_map.items():
                    if i < len(target.get("segments", [])):
                        target["segments"][i]["speaker"] = name

            mutate_index(_merge)
        except Exception as exc:  # noqa: BLE001
            log(f"cloud_summarize 失败: {exc}")
            with CLOUD_LOCK:
                CLOUD_STATE["message"] = "云端总结失败：" + str(exc)[:80]
        finally:
            with CLOUD_LOCK:
                CLOUD_STATE.update(running=False, done=1)

    def save_speakers(self, meeting_id: str, mapping_json: str) -> str:
        """保存用户对说话人的手动对应：{段索引: 人名}。"""
        try:
            from settings import mutate_index
            mapping = json.loads(mapping_json) if isinstance(mapping_json, str) else mapping_json
            found = [False]

            def _merge(idx: dict):
                m = next((x for x in idx.get("meetings", []) if x.get("id") == meeting_id), None)
                if not m:
                    return
                found[0] = True
                for k, v in mapping.items():
                    i = int(k)
                    if 0 <= i < len(m.get("segments", [])):
                        m["segments"][i]["speaker"] = v
                m["speakers_confirmed"] = True

            mutate_index(_merge)
            if not found[0]:
                return json.dumps({"ok": False, "error": "找不到会议"}, ensure_ascii=False)
            return json.dumps({"ok": True}, ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)

    def save_settings(self, cfg_json: str) -> str:
        try:
            cfg = json.loads(cfg_json) if isinstance(cfg_json, str) else cfg_json
            saved = save_settings(cfg)
            return json.dumps({"ok": True, "settings": saved}, ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)

    def choose_folder(self) -> str:
        """打开系统文件夹选择框，返回选中的路径（取消返回空）。"""
        try:
            result = WINDOW.create_file_dialog(webview.FOLDER_DIALOG) if WINDOW else None
            if result:
                return str(result[0]) if isinstance(result, (list, tuple)) else str(result)
            return ""
        except Exception as exc:  # noqa: BLE001
            log(f"choose_folder 失败: {exc}")
            return ""

    def open_folder(self, which: str = "record") -> str:
        try:
            cfg = load_settings()
            target = record_dir_path(cfg) if which == "record" else DATA
            target.mkdir(parents=True, exist_ok=True)
            os.startfile(str(target))  # noqa: S606 — Windows 资源管理器
            return "ok"
        except Exception as exc:  # noqa: BLE001
            return str(exc)

    def scan(self) -> str:
        try:
            return json.dumps(scan_recordings(), ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001
            log(f"scan 失败: {exc}")
            return json.dumps({"error": str(exc), "new": [], "new_count": 0}, ensure_ascii=False)

    def process_status(self) -> str:
        """返回当前处理进度（前端轮询用）。"""
        with PROCESS_LOCK:
            return json.dumps(dict(PROCESS_STATE), ensure_ascii=False)

    def process_new(self, keys_json: str) -> str:
        """后台线程处理新录音，立即返回；用 process_status 轮询进度。"""
        keys = json.loads(keys_json) if isinstance(keys_json, str) else keys_json
        with PROCESS_LOCK:
            if PROCESS_STATE["running"]:
                return json.dumps({"started": False, "error": "已有任务在处理中"}, ensure_ascii=False)
            PROCESS_STATE.update(running=True, done=0, total=len(keys), current="", message="准备中…")
        threading.Thread(target=self._process_worker, args=(keys,), daemon=True).start()
        return json.dumps({"started": True, "total": len(keys)}, ensure_ascii=False)

    def _process_worker(self, keys) -> None:
        done, failed = [], []
        try:
            from process import load_index, process_one
            from transcribe import Transcriber
            from settings import load_scan_state, save_scan_state

            ensure_dirs()
            idx = load_index()
            with PROCESS_LOCK:
                PROCESS_STATE["message"] = "加载本机转写模型…"
            tr = Transcriber()
            state = load_scan_state()
            for i, key in enumerate(keys):
                path = key.rsplit("|", 1)[0]
                p = Path(path)
                with PROCESS_LOCK:
                    PROCESS_STATE["current"] = p.name
                    PROCESS_STATE["message"] = f"转写中 {i + 1}/{len(keys)}"
                if not p.exists():
                    failed.append(f"文件不存在: {p}")
                    continue
                try:
                    process_one(p, tr, idx)
                    state.setdefault("files", {})[key] = {"at": "processed"}
                    done.append(p.name)
                except Exception as exc:  # noqa: BLE001
                    failed.append(f"{p.name}: {exc}")
                with PROCESS_LOCK:
                    PROCESS_STATE["done"] = i + 1
            from datetime import datetime
            state["last_scan"] = datetime.now().isoformat(timespec="seconds")
            save_scan_state(state)
        except Exception as exc:  # noqa: BLE001
            log(f"process_new 失败: {exc}")
            failed.append(str(exc))
        finally:
            with PROCESS_LOCK:
                PROCESS_STATE.update(running=False, message="完成" if not failed else "部分失败",
                                     done=PROCESS_STATE["total"])
            try:
                if WINDOW:
                    WINDOW.evaluate_js(f"window.__processResult={json.dumps({'done':done,'failed':failed,'count':len(done)}, ensure_ascii=False)}; window.onProcessFinished && window.onProcessFinished(window.__processResult);")
            except Exception as exc:  # noqa: BLE001
                log(f"回调前端失败: {exc}")

    def open_audio(self, rel_path: str) -> str:
        p = DATA / rel_path
        if not p.exists():
            return f"文件不存在: {p}"
        try:
            os.startfile(str(p))  # noqa: S606
            return "ok"
        except Exception as exc:  # noqa: BLE001
            return str(exc)

    def quit(self) -> None:
        if WINDOW:
            WINDOW.destroy()


def html_path() -> Path:
    ensure_dirs()
    out = DATA / "工作台.html"
    if not out.exists():
        from build_app import main as build_main
        build_main()
    return out


def main() -> None:
    global WINDOW
    try:
        log(f"启动 ROOT={ROOT}")
        from build_app import main as build_main
        build_main()
        log("界面已重建")
        path = html_path()
        log(f"加载 {path}")
        WINDOW = webview.create_window(
            APP_NAME,
            url=path.as_uri(),
            js_api=Api(),
            width=1360,
            height=860,
            min_size=(1024, 640),
            resizable=True,
            background_color="#F5F5F7",
        )
        log("窗口已创建，进入事件循环")
        webview.start()
        log("事件循环结束")
    except Exception as exc:  # noqa: BLE001
        log(f"启动失败: {type(exc).__name__}: {exc}")
        raise


if __name__ == "__main__":
    main()
