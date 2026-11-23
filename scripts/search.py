"""搜索本地会议记录：按关键词找到对应原话、时间戳和音频位置。

用法：
    python scripts/search.py 预算 报价              # 同时包含两个词
    python scripts/search.py 张三 预算 --any         # 包含任一个词
    python scripts/search.py --list                  # 列出所有会议
    python scripts/search.py 合同 --limit 5 --context 1
    python scripts/search.py 合同 --json             # 给程序/AI 读
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from config import DATA, INDEX, fmt_ts


def load_index() -> dict:
    if not INDEX.exists():
        return {"version": 1, "meetings": []}
    return json.loads(INDEX.read_text(encoding="utf-8"))


def all_text(m: dict) -> str:
    parts = [m["title"], m.get("date", "")]
    for s in m.get("segments", []):
        parts.append(s["text"])
    for key in ("summary", "transcript"):
        p = DATA / m.get(key, "")
        if p.exists():
            parts.append(p.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser(description="搜索本地会议记录")
    ap.add_argument("terms", nargs="*", help="关键词，空格分开")
    ap.add_argument("--any", action="store_true", help="任一关键词命中即可（默认全部命中）")
    ap.add_argument("--limit", type=int, default=10, help="最多显示几场会议")
    ap.add_argument("--context", type=int, default=1, help="命中前后各带几句")
    ap.add_argument("--list", action="store_true", help="列出所有会议")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    idx = load_index()
    meetings = idx.get("meetings", [])

    if args.list:
        if args.json:
            print(json.dumps([{k: m[k] for k in ("id", "title", "date", "duration", "summary")}
                              for m in meetings], ensure_ascii=False, indent=2))
        else:
            print(f"共 {len(meetings)} 场会议：\n")
            for m in reversed(meetings):
                print(f"  {m['date']} {m.get('time', '')}  {m['title']}  ({fmt_ts(m.get('duration', 0))})")
        return

    if not args.terms:
        ap.error("请给出关键词，或用 --list")

    terms = [t.lower() for t in args.terms if t.strip()]
    results = []
    for m in meetings:
        segs = m.get("segments", [])
        hits = []
        for i, s in enumerate(segs):
            text = s["text"].lower()
            matched = [t for t in terms if t in text]
            if (args.any and matched) or (not args.any and len(matched) == len(terms)):
                hits.append((i, matched))
        if not hits and len(terms) > 1:
            body = all_text(m).lower()
            matched_all = [t for t in terms if t in body]
            if len(matched_all) == len(terms):
                for i, s in enumerate(segs):
                    matched = [t for t in terms if t in s["text"].lower()]
                    if matched:
                        hits.append((i, matched))
                if not hits:
                    hits = [(-1, matched_all)]
        if not hits:
            continue

        hit_items = []
        for i, matched in hits[:8]:
            if i >= 0:
                lo, hi = max(0, i - args.context), min(len(segs), i + args.context + 1)
                ctx = [{"time": fmt_ts(segs[j]["start"]), "text": segs[j]["text"],
                        "hit": j == i} for j in range(lo, hi)]
                at = fmt_ts(segs[i]["start"])
            else:
                ctx, at = [], ""
            hit_items.append({"at": at, "matched": matched, "context": ctx})
        results.append({
            "id": m["id"], "title": m["title"], "date": m["date"],
            "duration": m.get("duration", 0),
            "audio": str(DATA / m.get("audio", "")),
            "transcript": str(DATA / m.get("transcript", "")),
            "summary": str(DATA / m.get("summary", "")),
            "hits": hit_items,
        })

    results.sort(key=lambda r: (r["date"], len(r["hits"])), reverse=True)
    results = results[:args.limit]

    if args.json:
        print(json.dumps({"query": args.terms, "any": args.any, "count": len(results),
                          "results": results}, ensure_ascii=False, indent=2))
        return

    if not results:
        print(f"没找到同时包含 {args.terms} 的记录。可以试试 --any 或更短的关键词。")
        return
    print(f"找到 {len(results)} 场会议命中：\n")
    for r in results:
        print(f"=== {r['date']}  {r['title']}  时长 {fmt_ts(r['duration'])}")
        print(f"    逐字稿: {r['transcript']}")
        print(f"    音频:   {r['audio']}")
        for h in r["hits"]:
            if h["context"]:
                for c in h["context"]:
                    mark = ">>" if c["hit"] else "  "
                    print(f"    {mark} [{c['time']}] {c['text']}")
            else:
                print(f"    >> [摘要/标题命中]")
            print()


if __name__ == "__main__":
    main()
