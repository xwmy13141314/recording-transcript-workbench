"""云端改写式总结 + 说话人推断（ siliconflow，OpenAI 兼容接口）。

只把「转写后的文字」发去做总结；音频仍全程本机。
API Key 来自本机设置文件，不写日志、不写入总结文件。
失败时回退到本地规则摘要，不影响主流程。

v1.1：分段 Map-Reduce。长会议先按约 2500 字切块逐段提取详细要点，
再汇总成 2000-4000 字纪要，避免 7B 小模型「抓头丢尾」。
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from config import DATA, INDEX
from settings import load_settings

CHUNK_SIZE = 2500          # 每块目标字数（逐段提取）

# ---------- 阶段一：逐段提取详细要点 ----------
MAP_SYSTEM = """你是一名会议速记员。你会收到一段会议逐字稿的片段（每行 [时间] 内容）。
请把这一段里讨论的所有事项**详尽**提取出来，供后续汇总成完整纪要。

要求：
1. 忠实原文：只写这段里确实出现的内容，不补充、不猜测、不编造人名或数字。
2. 每条要点必须是一个**完整的书面句子**，采用「要点小标题：完整论述」格式，例如
   "供应商选择失误：当前方案由甲公司主导，实际用的是乙公司的旧平台，甲公司做手机成熟但不专业"。
   **禁止**只写"增加一轮验证""王工负责模块""定V3版"这种碎片关键词或短语。
3. 详尽：把这段里所有实质信息都提取成要点（通常 5-12 条），每条要能独立看懂。
4. 口语转书面：删掉语气词、重复、闲聊，但保留所有数字、产品名、公司名、对比对象。
5. 数字必须带含义，例如"增加500到1000台小批量样机"，禁止只写"500到1000台"。
6. 人名只写原文明确出现的称呼（如"王总""陈工"），**禁止**把"我/他/张三/李四"等代词或虚构人名当说话人。
7. 保留时间：行动项、决定、关键数字尽量带上原文里出现的时间戳（如 00:12:30）。

严格只输出以下 JSON（不要 markdown 代码块、不要任何解释）：
{
  "topic": "这一段最主要的议题名（10 字以内）",
  "points": ["要点1", "要点2"],
  "decisions": ["本段明确拍板的事项"],
  "actions": [{"task": "任务", "owner": "负责人或空", "due": "时间或空", "ref": "原话时间"}],
  "numbers": ["关键数字及其含义"],
  "open_questions": ["尚未确定需后续确认的问题"],
  "speakers": [{"name": "人名", "hint": "依据，如：文中出现『张三说』"}]
}
没有内容的字段给空数组。"""

MAP_PROMPT = """会议逐字稿片段：
{transcript}

请按上述要求详尽提取这一段的所有要点，输出 JSON。"""

# ---------- 阶段二：汇总成完整纪要 ----------
REDUCE_SYSTEM = """你是一名资深会议纪要撰写人。你会收到一份长会议的「分段要点提取结果」（JSON 数组），
请把它们整合成一份**可以直接发给同事阅读**的详尽中文会议纪要。

写作原则：
1. 完整覆盖：所有分段里的要点都要保留，按主题合并同类项，**绝不遗漏**重要信息。
2. 归纳分组：把讨论同一件事的内容合并成一个主题，每个主题下分条列出具体要点。
3. 改写而非摘抄：口语转书面语，但保留所有具体的数字、产品名、公司名、对比对象、人名和结论。
4. 忠实：只写材料里确实出现的信息，不补充、不猜测、不编造。
5. **每条要点必须是完整通顺的书面句子**，采用「要点小标题：完整论述」格式，例如
   "供应商选择失误：当前方案由甲公司主导，实际用的是乙公司的旧平台，甲公司做手机成熟但不专业"。
   绝对禁止罗列"人员固定""定V3版""王工负责模块""增加一轮验证"这类碎片关键词。
6. **关键数字必须写成带语境的完整句**，例如"小批量样机数量从二三十台增加到500到1000台"，禁止只写"500到1000台""30万"。
7. **说话人只保留原文明确出现的真实称呼**（如"王总""陈工"），禁止把"我/他/张三/李四"等人称代词或虚构人名当说话人。
8. 行动项的 owner/due 找不到就填空字符串""，禁止填"负责人""空""未指定""时间或空"这类占位符。
9. 篇幅：全文（不含标题）控制在 **2000-4000 字**。信息多就写到 4000 字左右，信息少不少于 2000 字。不要写成几百字的极简摘要，要详实。

严格只输出以下 JSON（不要 markdown 代码块、不要任何解释）：
{
  "title": "一句话会议标题（15 字以内）",
  "recording_info": {
    "duration": "会议时长，如：约 1 小时 17 分钟（材料没给就填空）",
    "participants": "参与人数，如：约 5 人（材料没给就填空）",
    "type": "内容类型，如：工作会议（产品复盘与规划）"
  },
  "summary": "一段式总述：4-8 句话，说清会议目的、核心结论、主要方向。200-350 字，不分点。",
  "highlights": [
    {"topic": "主题名", "points": ["该主题下的一条具体要点", "另一条要点"], "conclusion": "该主题讨论出的结论（没有就空字符串）"}
  ],
  "decisions": ["会议层面正式拍板的事项"],
  "actions": [
    {"task": "具体可执行的任务", "owner": "负责人或空", "due": "时间或空", "ref": "原话时间"}
  ],
  "numbers": ["关键数字及含义，例如：新版本冷启动目标 2 秒；当前版本冷启动 3.2 秒"],
  "open_questions": ["尚未解决需后续确认的问题"],
  "speakers": [{"name": "人名", "hint": "依据"}]
}

字段要求：
- highlights 是主体：通常 5-10 个主题，每个主题 3-15 条要点，**务必覆盖所有分段的内容**；主题按讨论顺序或重要性排列。
- 每条要点要能独立看懂，带上对象、数值或条件，不要只写「讨论了某某问题」。
- 每个主题的 conclusion 只写这个主题自己的结论，不要和 decisions 重复。
- decisions 只放正式拍板事项；actions 的 task 不能为空，owner/due/ref 找不到填空字符串。
- numbers 必须带「这个数字是什么」的解释；speakers 只填材料里出现明确称呼的。
- 没有内容的字段给空数组（title/summary/recording_info 除外）。"""

REDUCE_PROMPT = """会议名称：{title}
会议时长（秒）：{duration}
分段要点提取结果（共 {n} 段）：
{material}

请按上述要求整合成 2000-4000 字的完整会议纪要 JSON。"""


def _chat(messages: list[dict], cfg: dict, max_tokens: int = 2000, retries: int = 3) -> str:
    """调用 OpenAI 兼容接口；对限流/网络抖动做指数退避重试。"""
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
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                data = json.load(r)
            return data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise
    raise RuntimeError("云端请求失败")


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


def _fmt(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def _split_chunks(segments: list[dict], size: int = CHUNK_SIZE) -> list[list[dict]]:
    """按时间顺序切块，不切断单个段落；单段超长则自成一块。"""
    chunks: list[list[dict]] = []
    cur: list[dict] = []
    total = 0
    for s in segments:
        text = str(s.get("text", ""))
        if cur and total + len(text) > size:
            chunks.append(cur)
            cur, total = [], 0
        cur.append(s)
        total += len(text)
    if cur:
        chunks.append(cur)
    return chunks


def _list(x) -> list:
    return x if isinstance(x, list) else []


def summarize_remote(segments: list[dict], title: str = "", duration: float = 0,
                     progress=None) -> dict:
    """segments: [{start,end,text}]。返回结构化纪要（2000-4000 字规模）。

    progress: 可选回调 fn(done, total, message)，用于前端显示分段进度。
    """
    cfg = load_settings()
    if not segments:
        raise RuntimeError("没有可总结的内容")
    chunks = _split_chunks(segments)
    steps = len(chunks) + 1
    report = progress or (lambda *_: None)

    # 阶段一：逐段提取
    maps: list[dict] = []
    for i, chunk in enumerate(chunks):
        report(i, steps, f"分段提取 {i + 1}/{len(chunks)}…")
        transcript = "\n".join(
            f"[{_fmt(s.get('start', 0))}] {s.get('text', '')}" for s in chunk
        )
        raw = _chat([
            {"role": "system", "content": MAP_SYSTEM},
            {"role": "user", "content": MAP_PROMPT.format(transcript=transcript)},
        ], cfg, max_tokens=1800)
        obj = _extract_json(raw)
        for k in ("points", "decisions", "actions", "numbers", "open_questions", "speakers"):
            obj[k] = _list(obj.get(k))
        obj["topic"] = str(obj.get("topic") or f"片段{i + 1}")
        maps.append(obj)

    # 阶段二：汇总
    report(len(chunks), steps, "汇总生成完整纪要…")
    material = json.dumps([
        {
            "topic": o["topic"],
            "points": o["points"],
            "decisions": o["decisions"],
            "actions": o["actions"],
            "numbers": o["numbers"],
            "open_questions": o["open_questions"],
            "speakers": o["speakers"],
        } for o in maps
    ], ensure_ascii=False)
    raw = _chat([
        {"role": "system", "content": REDUCE_SYSTEM},
        {"role": "user", "content": REDUCE_PROMPT.format(
            title=title or "会议", duration=int(duration or 0),
            n=len(chunks), material=material)},
    ], cfg, max_tokens=6000)
    obj = _extract_json(raw)

    for k in ("summary", "title"):
        obj.setdefault(k, "")
    for k in ("highlights", "decisions", "actions", "numbers", "open_questions", "speakers"):
        obj[k] = _list(obj.get(k))

    # 录音信息：模型没给全时用本机元数据补齐，不编造
    info = obj.get("recording_info")
    info = info if isinstance(info, dict) else {}
    if duration and not str(info.get("duration") or "").strip():
        d = int(duration)
        h, m = d // 3600, d % 3600 // 60
        info["duration"] = (f"约 {h} 小时 {m} 分钟" if h else f"约 {m} 分钟")
    info.setdefault("participants", "")
    info.setdefault("type", "")
    obj["recording_info"] = info
    _sanitize(obj)
    report(steps, steps, "云端总结完成")
    return obj


PLACEHOLDER_NAMES = {"我", "他", "她", "它", "你", "张三", "李四", "王五", "某人", "某某", "空", "负责人", "大家", "对方", "他们", "我们"}
PLACEHOLDER_VALUES = {"", "空", "负责人", "未指定", "时间或空", "无", "n/a", "null", "暂无", "待定"}


def _sanitize(obj: dict) -> None:
    """清洗小模型常见的占位符/编造，避免脏数据进入纪要。"""
    # 说话人：去掉代词/虚构人名
    sp = obj.get("speakers") or []
    obj["speakers"] = [
        s for s in sp
        if isinstance(s, dict)
        and str(s.get("name") or "").strip()
        and str(s.get("name") or "").strip() not in PLACEHOLDER_NAMES
    ]
    # 行动项：清理 owner/due 占位符
    for a in obj.get("actions") or []:
        if isinstance(a, dict):
            for k in ("owner", "due"):
                if str(a.get(k) or "").strip() in PLACEHOLDER_VALUES:
                    a[k] = ""
    # 决定：同样清理
    for d in obj.get("decisions") or []:
        if isinstance(d, dict):
            for k in ("owner", "due"):
                if str(d.get(k) or "").strip() in PLACEHOLDER_VALUES:
                    d[k] = ""


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
             "> 云端分段总结（原文音频未上传，仅转写文字经云端处理）。", ""]

    info = obj.get("recording_info")
    if isinstance(info, dict) and any(str(info.get(k) or "").strip() for k in ("duration", "participants", "type")):
        lines.extend(["## 录音信息", ""])
        for key, label in (("duration", "时长"), ("participants", "参与人数"), ("type", "内容类型")):
            v = str(info.get(key) or "").strip()
            if v:
                lines.append(f"- **{label}**：{v}")
        lines.append("")

    lines.extend(["## 摘要", "", obj.get("summary") or "(无)", ""])

    # 讨论要点：按主题展开
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
    names = [s.get("name") for s in (obj.get("speakers") or []) if isinstance(s, dict) and s.get("name")]
    out = []
    for s in segments:
        item = dict(s)
        hit = [n for n in names if n and n in item.get("text", "")]
        item["speaker"] = hit[0] if hit else ""
        out.append(item)
    return out
