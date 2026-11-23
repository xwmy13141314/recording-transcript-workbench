"""本地规则摘要：不调用任何大模型、不联网，从转写文本里抽取要点。

输出的是"抽取式摘要"（原文句子），不是改写式总结；好处是完全本地、可追溯，
每句话都能点时间戳回到原音。日后若要更自然的总结，可再接本机 ollama。
"""
from __future__ import annotations

import re
from pathlib import Path

from config import fmt_ts

DECISION = re.compile(r"决定|确定|结论|通过|一致|同意|最终|确认|方案是|定为")
ACTION = re.compile(r"下一步|接下来|需要|要|应该|负责|跟进|提交|发送|发|安排|准备|记得|别忘|截止|之前|完成|落实|推进")
NUMBER = re.compile(r"\d+(?:\.\d+)?\s*(?:元|万|亿|%|％|天|周|个月|月|日|号|点|分|小时|人|个|次|条|页|版)")
QUESTION = re.compile(r"[?？]|吗|呢|是否|怎么|如何|为什么|能不能|可不可以")
FILLER = re.compile(r"嗯|啊|那个|就是说|然后呢|对吧")


def clean(text: str) -> str:
    text = re.sub(r"\s+", "", text)
    return text.strip("，。,.!！?？:：;； ")


def score_sentence(text: str) -> int:
    s = 0
    if DECISION.search(text):
        s += 4
    if ACTION.search(text):
        s += 3
    if NUMBER.search(text):
        s += 2
    if QUESTION.search(text):
        s += 1
    if len(text) >= 12:
        s += 1
    if FILLER.search(text):
        s -= 1
    return s


def summarize(segs, title: str, transcript_rel: str, max_points: int = 8) -> str:
    """segs: list[Segment]（含 start/end/text）。"""
    sentences = [(s.start, clean(s.text)) for s in segs]
    sentences = [(t, x) for t, x in sentences if len(x) >= 4]
    ranked = sorted(((score_sentence(x), t, x) for t, x in sentences),
                    key=lambda z: (-z[0], z[1]))
    picked: list[tuple[int, float, str]] = []
    seen: set[str] = set()
    for sc, t, x in ranked:
        key = x[:16]
        if key in seen:
            continue
        seen.add(key)
        picked.append((sc, t, x))
        if len(picked) >= max_points:
            break
    picked.sort(key=lambda z: z[1])

    actions = [(t, x) for t, x in sentences if ACTION.search(x) or DECISION.search(x)]
    numbers = [(t, x) for t, x in sentences if NUMBER.search(x)]
    questions = [(t, x) for t, x in sentences if QUESTION.search(x)]

    def bullets(items, limit: int) -> list[str]:
        out = []
        for t, x in items[:limit]:
            out.append(f"- [{fmt_ts(t)}] {x}")
        return out or ["- (无)"]

    lines = [
        f"# 会议总结: {title}",
        "",
        "> 本文件由本机规则从逐字稿抽取，未调用云端大模型。每句前面的时间是录音内位置。",
        "",
        "## 一句话摘要",
        "",
        (picked[0][2] if picked else "(无内容)"),
        "",
        "## 关键要点",
        "",
        *bullets([(t, x) for _, t, x in picked], max_points),
        "",
        "## 行动项 / 决定",
        "",
        *bullets(actions, 10),
        "",
        "## 关键数字",
        "",
        *bullets(numbers, 10),
        "",
        "## 待确认 / 疑问",
        "",
        *bullets(questions, 10),
        "",
        "## 原文",
        "",
        f"- [逐字稿](../转写/{Path(transcript_rel).name})",
        "",
    ]
    return "\n".join(lines)
