"""云端改写式总结 + 说话人推断（ siliconflow，OpenAI 兼容接口）。

只把「转写后的文字」发去做总结；音频仍全程本机。
API Key 来自本机设置文件，不写日志、不写入总结文件。
失败时回退到本地规则摘要，不影响主流程。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from config import DATA, INDEX
from settings import load_settings

SUMMARY_SYSTEM = """你是一名资深会议纪要撰写人。你会收到一份口语化的会议逐字稿（每行 [时间] 内容），
请把它整理成一份**可以直接发给同事阅读**的中文会议纪要。

写作原则：
1. 改写而非摘抄：把口语转成书面语，删掉重复、语气词、跑题闲聊；不要照搬原句，也不要截断句子。
2. 归纳而非罗列：把讨论同一件事的段落合并成一个议题，说清楚「讨论什么 → 结论是什么」。
3. 忠实：只写逐字稿里确实出现的信息，不补充、不猜测、不编造人名、数字或结论。
4. 具体：每条要点要能独立看懂，避免「性能问题」「沟通一下」这种空洞短语；带上关键对象、数值或条件。

严格只输出以下 JSON（不要输出任何解释、不要用 markdown 代码块）：
{
  "title": "一句话会议标题，概括这次会议在谈什么（15 字以内）",
  "summary": "一段式高管摘要：3-5 句话，说清会议目的、主要讨论、达成的结论。不要分点。",
  "highlights": [
    {"topic": "议题名", "points": ["围绕该议题的关键论点或信息1", "关键论点2"], "conclusion": "这个议题讨论出的结论（没有就留空字符串）"}
  ],
  "decisions": ["明确达成的决定，写清楚决定了什么、范围/条件"],
  "actions": [
    {"task": "具体要做什么（必须写清任务本身）", "owner": "负责人，文本没提到就填空字符串", "due": "时间/截止，没提到就填空字符串", "ref": "对应原话的起始时间，如 00:12:30"}
  ],
  "numbers": ["关键数字及其含义，必须带语境，例如：本季度服务器预算 20 万元；灰度覆盖 10% 用户"],
  "open_questions": ["尚未解决、需要后续确认的问题"],
  "speakers": [{"name": "推断出的人名", "hint": "依据，如：文中出现『张三说』"}]
}

字段要求：
- highlights 是重点：**长会议要拆成多个议题**（通常 3-8 个，按讨论顺序或重要性），不要把所有内容塞进一个议题；每个议题 2-4 条具体论点，points 要写清「谁/什么/多少/为什么」，不要只写议题名。
- 每个议题的 conclusion 只写「这个议题的结论」，不要把同一句话再放进 decisions。
- decisions 只放**会议层面正式拍板的事项**（谁定了什么），与各议题 conclusion 不重复；没有就空数组。
- actions 的 task 不能为空且必须具体可执行；owner/due/ref 找不到就填空字符串，不要编。
- numbers 必须带「这个数字是什么」的解释，不能只写「10%」。
- speakers 只在文本里出现明确称呼时才填，否则给空数组。
- 没有内容的字段给空数组 []（summary/title 除外）。"""

PROMPT = """会议逐字稿（每行 [时间] 内容）：
{transcript}

请按上述要求输出会议纪要 JSON。"""


def _chat(messages: list[dict], cfg: dict, max_tokens: int = 2000) -> str:
    base = (cfg.get("cloud_base") or "https://api.siliconflow.cn/v1").rstrip("/")
    key = cfg.get("cloud_api_key") or ""
    if not key:
        raise RuntimeError("未配置 API Key")
    body = json.dumps({
        "model": cfg.get("cloud_model") or "Qwen/Qwen2.5-7B-Instruct",
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.3,
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        base + "/chat/completions", data=body,
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.load(r)
    return data["choices"][0]["message"]["content"]


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.lstrip().startswith("json"):
            text = text.lstrip()[4:]
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    return json.loads(text)


def summarize_remote(segments: list[dict]) -> dict:
    """segments: [{start,end,text}]，返回结构化纪要。"""
    cfg = load_settings()
    transcript = "\n".join(
        f"[{_fmt(s.get('start', 0))}] {s.get('text', '')}" for s in segments
    )
    if not transcript.strip():
        raise RuntimeError("没有可总结的内容")
    raw = _chat([
        {"role": "system", "content": SUMMARY_SYSTEM},
        {"role": "user", "content": PROMPT.format(transcript=transcript)},
    ], cfg)
    obj = _extract_json(raw)
    for k in ("summary", "title", "highlights", "decisions", "actions",
              "numbers", "open_questions", "speakers"):
        obj.setdefault(k, "" if k in ("summary", "title") else [])
    return obj


def _fmt(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def _action_text(x) -> str:
    if not isinstance(x, dict):
        return str(x)
    task = (x.get("task") or x.get("text") or x.get("action")
            or x.get("事项") or x.get("任务") or x.get("待办") or "")
    who = x.get("owner") or x.get("responsible") or x.get("who") or x.get("负责人") or ""
    due = x.get("due") or x.get("due_date") or x.get("时间") or x.get("截止") or ""
    ref = x.get("ref") or x.get("timestamp") or x.get("时间戳") or ""
    bits = [str(task)] if task else ["(未写明具体任务)"]
    meta = []
    if who:
        meta.append(f"负责人：{who}")
    if due:
        meta.append(f"时间：{due}")
    if ref:
        meta.append(f"原话：{ref}")
    if meta:
        bits.append("（" + "，".join(meta) + "）")
    return "".join(bits)


def _number_text(x) -> str:
    if isinstance(x, dict):
        num = x.get("number") or x.get("value") or x.get("数字") or ""
        meaning = x.get("meaning") or x.get("context") or x.get("含义") or x.get("说明") or ""
        if num and meaning:
            return f"{meaning}（{num}）" if str(num) not in str(meaning) else str(meaning)
        return str(num or meaning or json.dumps(x, ensure_ascii=False))
    return str(x)


def _decision_text(x) -> str:
    if isinstance(x, dict):
        return _action_text(x)
    return str(x)


def to_markdown(obj: dict, title: str, segments: list[dict]) -> str:
    head = obj.get("title") or title
    lines = [f"# {head}", "",
             "> 云端模型改写式总结（原文音频未上传，仅转写文字经云端处理）。", "",
             "## 摘要", "", obj.get("summary") or "(无)", ""]

    # 讨论要点：按议题展开
    hl = obj.get("highlights") or []
    if hl:
        lines.extend(["## 讨论要点", ""])
        for h in hl:
            if isinstance(h, dict):
                topic = h.get("topic") or h.get("议题") or "议题"
                lines.append(f"### {topic}")
                for p in (h.get("points") or h.get("要点") or []):
                    if isinstance(p, dict):
                        p = p.get("point") or p.get("text") or p.get("要点") or json.dumps(p, ensure_ascii=False)
                    lines.append(f"- {p}")
                concl = h.get("conclusion") or h.get("结论") or ""
                if concl:
                    lines.append(f"- 结论：{concl}")
                lines.append("")
            else:
                lines.append(f"- {h}")
        lines.append("")

    def sec(name: str, key: str, fmt=None) -> None:
        items = obj.get(key) or []
        lines.extend([f"## {name}", ""])
        if items:
            for x in items:
                lines.append(f"- {fmt(x) if fmt else x}")
        else:
            lines.append("- (无)")
        lines.append("")

    sec("决定", "decisions", _decision_text)
    sec("行动项", "actions", _action_text)
    sec("关键数字", "numbers", _number_text)
    sec("待确认", "open_questions")
    sp = obj.get("speakers") or []
    lines.extend(["## 推断的说话人", ""])
    if sp:
        for s in sp:
            lines.append(f"- {s.get('name', '?')}：{s.get('hint', '')}")
    else:
        lines.append("- (未能从文本推断出人名)")
    lines.append("")
    return "\n".join(lines)


def attach_speakers(segments: list[dict], obj: dict) -> list[dict]:
    """把推断出的说话人挂到对应段落（仅在文本里出现该人名时）。"""
    names = [s.get("name") for s in (obj.get("speakers") or []) if s.get("name")]
    out = []
    for s in segments:
        item = dict(s)
        hit = [n for n in names if n and n in item.get("text", "")]
        item["speaker"] = hit[0] if hit else ""
        out.append(item)
    return out
