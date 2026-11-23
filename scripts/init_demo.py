"""把示例数据导入本机 `会议记录/`，方便第一次打开应用时就有内容可看。

用法：
    python scripts/init_demo.py

幂等：示例会议已存在时不会重复导入；不会覆盖你已有的会议。
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import DATA, INDEX, TRANSCRIPTS, SUMMARIES, ensure_dirs  # noqa: E402
from settings import mutate_index  # noqa: E402

DEMO = Path(__file__).resolve().parent.parent / "示例数据"


def main() -> None:
    if not DEMO.exists():
        print(f"找不到示例数据目录: {DEMO}")
        return
    ensure_dirs()
    demo_index = json.loads((DEMO / "索引.json").read_text(encoding="utf-8"))
    demo_meetings = demo_index.get("meetings", [])

    for sub in ("转写", "总结"):
        src_dir = DEMO / sub
        dst_dir = TRANSCRIPTS if sub == "转写" else SUMMARIES
        if not src_dir.exists():
            continue
        for f in src_dir.glob("*.md"):
            dst = dst_dir / f.name
            if not dst.exists():
                shutil.copy2(f, dst)

    def _merge(idx: dict) -> dict:
        have = {m.get("id") for m in idx.get("meetings", [])}
        added = [m for m in demo_meetings if m.get("id") not in have]
        idx.setdefault("meetings", []).extend(added)
        return {"added": len(added)}

    result = mutate_index(_merge)
    added = result.get("added", 0) if isinstance(result, dict) else 0
    print(f"示例数据就绪：新增 {added} 场示例会议，数据目录 {DATA}")
    if added == 0:
        print("示例会议已存在，未重复导入。")


if __name__ == "__main__":
    main()
