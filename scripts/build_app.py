"""构建桌面应用界面：把本机索引、设置、逐字稿、总结内嵌进单文件 HTML。

用法：
    python scripts/build_app.py
生成：
    会议记录/工作台.html
界面运行时通过 pywebview 本地 API 刷新数据、扫描、处理；无 API 时回退到内嵌数据。
"""
from __future__ import annotations

import json
import re

from config import DATA, INDEX
from settings import load_settings, public_settings, scan_recordings

APP_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>录音转写工作台</title>
<link rel="icon" type="image/png" href="__ICON__">
<style>
  :root {
    --scale: 1;
    --bg:#f5f5f7; --panel:#ffffff; --panel2:#fafafa; --left-bg:var(--panel2);
    --text:#1d1d1f; --muted:#86868b; --border:#e5e5ea; --accent:#0071e3;
    --accent-soft:#e8f1ff; --hover:#f0f0f5; --mark:#fff1b8; --radius:10px; --pad:1rem;
    --font:-apple-system,BlinkMacSystemFont,"SF Pro Text","PingFang SC","Microsoft YaHei",sans-serif;
  }
  html { font-size: calc(14px * var(--scale)); }
  body { margin:0; font-family:var(--font); color:var(--text); background:var(--bg); -webkit-font-smoothing:antialiased; }
  button,input,select,textarea { font-family:inherit; font-size:1rem; color:inherit; }
  .app { height:100vh; display:flex; flex-direction:column; }
  .titlebar { height:2.2rem; flex:none; display:flex; align-items:center; gap:0.4rem; padding:0 0.8rem; background:var(--panel); border-bottom:1px solid var(--border); }
  .dot { width:0.55rem; height:0.55rem; border-radius:50%; }
  .dot.r{background:#ff5f57}.dot.y{background:#febc2e}.dot.g{background:#28c840}
  .toolbar { height:2.6rem; flex:none; display:flex; align-items:center; gap:0.6rem; padding:0 0.9rem; background:var(--panel); border-bottom:1px solid var(--border); }
  .toolbar .brand { font-weight:600; margin-right:auto; font-size:1.05rem; }
  .btn { border:1px solid var(--border); background:var(--panel); border-radius:0.45rem; padding:0.3rem 0.7rem; cursor:pointer; font-size:0.85rem; }
  .btn:hover { background:var(--hover); }
  .btn.pri { background:var(--accent); color:#fff; border-color:var(--accent); }
  .layout { flex:1; min-height:0; display:grid; grid-template-columns:15.5rem minmax(0,1fr) 15rem; }
  .col { min-width:0; overflow:auto; }
  .left { background:var(--left-bg); border-right:1px solid var(--border); padding:0.8rem; display:flex; flex-direction:column; }
  .center { padding:1.1rem 1.4rem; }
  .right { background:var(--left-bg); border-left:1px solid var(--border); padding:0.8rem; }
  .search { width:100%; padding:0.5rem 0.65rem; border:1px solid var(--border); border-radius:0.5rem; background:var(--panel); outline:none; font-size:0.85rem; }
  .search:focus { border-color:var(--accent); }
  .tags { display:flex; gap:0.4rem; margin:0.7rem 0; }
  .tags span { font-size:0.75rem; padding:0.25rem 0.6rem; border-radius:1rem; color:var(--muted); cursor:pointer; }
  .tags span.on { background:var(--accent-soft); color:var(--accent); }
  .tags .cnt { margin-left:auto; font-size:0.7rem; color:var(--muted); white-space:nowrap; align-self:center; cursor:default; padding-right:0.5rem; letter-spacing:0.05rem; }
  .grp { font-size:0.75rem; color:var(--muted); margin:0.8rem 0 0.35rem; padding-left:0.2rem; }
  .grp-toggle { display:flex; align-items:center; gap:0.3rem; cursor:pointer; padding:0.3rem 0.35rem; border-radius:0.35rem; user-select:none; }
  .grp-toggle:hover { background:var(--hover); color:var(--text); }
  .grp-toggle .caret { display:inline-block; width:0.7rem; font-size:0.7rem; color:var(--muted); }
  .grp-toggle .grp-n { margin-left:auto; font-size:0.68rem; color:var(--muted); background:var(--panel); border:1px solid var(--border); border-radius:0.6rem; padding:0 0.35rem; min-width:1.1rem; text-align:center; }
  .grp-toggle.open { color:var(--text); }
  .grp-toggle.open .grp-n { background:var(--accent-soft); color:var(--accent); border-color:transparent; }
  .mi { padding:0.5rem 0.6rem; border-radius:0.5rem; cursor:pointer; margin-bottom:0.15rem; display:flex; justify-content:space-between; align-items:center; font-size:0.85rem; }
  .mi:hover { background:var(--hover); }
  .mi.on { background:var(--accent-soft); }
  .mi .sub { font-size:0.7rem; color:var(--muted); }
  .leftgear { margin-top:auto; border:1px solid var(--border); border-radius:0.5rem; padding:0.5rem 0.7rem; font-size:0.85rem; color:var(--text); background:var(--panel); text-align:center; cursor:pointer; }
  .leftgear:hover { background:var(--hover); }
  .statusbar { height:1.7rem; flex:none; border-top:1px solid var(--border); display:flex; align-items:center; padding:0 0.8rem; font-size:0.72rem; color:var(--muted); background:var(--panel); }
  .wb { border:1px solid var(--accent); background:var(--accent-soft); border-radius:var(--radius); padding:0.75rem 0.9rem; margin-bottom:0.9rem; }
  .wb h4 { margin:0; font-size:0.9rem; font-weight:600; color:var(--accent); display:flex; align-items:center; justify-content:space-between; }
  .wb .row { font-size:0.78rem; margin-top:0.4rem; display:flex; justify-content:space-between; gap:0.5rem; }
  .wb .row span:first-child { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .wb .meta { font-size:0.7rem; color:var(--muted); margin-top:0.5rem; }
  .h1 { font-size:1.35rem; font-weight:600; margin:0 0 0.25rem; }
  .meta-line { font-size:0.78rem; color:var(--muted); }
  .tabs { display:flex; gap:1.1rem; border-bottom:1px solid var(--border); margin:0.8rem 0; padding-bottom:0.4rem; }
  .tabs span { font-size:0.85rem; color:var(--muted); cursor:pointer; }
  .tabs span.on { color:var(--accent); border-bottom:2px solid var(--accent); padding-bottom:0.35rem; }
  .tabpane { display:none; } .tabpane.on { display:block; }
  .card { background:var(--panel); border:1px solid var(--border); border-radius:0.6rem; padding:0.75rem 0.9rem; margin-bottom:0.65rem; }
  .card h5 { margin:0 0 0.5rem; font-size:0.85rem; font-weight:600; }
  .pt { font-size:0.82rem; margin:0.35rem 0; line-height:1.55; }
  .pt .ts { color:var(--accent); font-family:ui-monospace,Consolas,monospace; font-size:0.72rem; margin-right:0.4rem; }
  mark { background:var(--mark); padding:0 0.1rem; border-radius:0.15rem; }
  .st { font-size:0.75rem; color:var(--muted); }
  .kv { display:flex; justify-content:space-between; font-size:0.78rem; padding:0.35rem 0; border-bottom:1px solid var(--border); }
  .kv span:first-child { color:var(--muted); }
  .tl { font-size:0.78rem; margin-top:0.4rem; }
  .tl div { padding:0.28rem 0; cursor:pointer; }
  .tl .ts { color:var(--accent); font-family:ui-monospace,Consolas,monospace; font-size:0.72rem; margin-right:0.35rem; }
  .segline { padding:0.45rem 0.6rem; border-left:2px solid var(--border); margin:0.3rem 0; line-height:1.6; border-radius:0 0.3rem 0.3rem 0; cursor:pointer; font-size:0.85rem; }
  .segline:hover{background:var(--hover)} .segline.hit { border-left-color:var(--accent); background:var(--accent-soft); }
  .player { background:var(--panel); border:1px solid var(--border); border-radius:var(--radius); padding:0.7rem 0.8rem; margin-bottom:0.7rem; }
  .player audio { width:100%; height:2rem; }
  .sumbar { display:flex; align-items:center; justify-content:space-between; margin:0 0 0.7rem; }
  .subh { font-weight:600; font-size:0.84rem; color:var(--fg); margin:0.8rem 0 0.3rem; padding-left:0.1rem; }
  .subh:first-child { margin-top:0.1rem; }
  .speaker { display:inline-block; background:var(--accent-soft); color:var(--accent); border-radius:0.3rem; padding:0 0.35rem; margin-right:0.4rem; font-size:0.75rem; cursor:pointer; }
  .speaker:hover { text-decoration:underline; }
  .res-hit { background:var(--accent-soft); border-left:2px solid var(--accent); padding:0.45rem 0.65rem; margin:0.35rem 0; font-size:0.85rem; cursor:pointer; }
  .res-src { font-size:0.7rem; color:var(--muted); margin-top:0.2rem; }
  .empty { color:var(--muted); padding:2rem 0; text-align:center; font-size:0.85rem; }
  .overlay { position:absolute; inset:0; background:rgba(0,0,0,.15); display:none; align-items:center; justify-content:center; z-index:20; }
  .overlay.on { display:flex; }
  .modal { width:34rem; max-width:92%; background:var(--panel); border:1px solid var(--border); border-radius:0.8rem; padding:1.2rem 1.4rem; box-shadow:0 10px 40px rgba(0,0,0,.18); }
  .modal h3 { margin:0 0 0.9rem; font-size:1.1rem; font-weight:600; }
  .mtabs { display:flex; gap:0.4rem; border-bottom:1px solid var(--border); padding-bottom:0.6rem; margin-bottom:1rem; flex-wrap:wrap; }
  .mtabs span { font-size:0.82rem; padding:0.35rem 0.7rem; border-radius:0.4rem; color:var(--muted); cursor:pointer; }
  .mtabs span.on { background:var(--accent-soft); color:var(--accent); }
  .field { margin-bottom:1rem; }
  .field label { display:block; font-size:0.78rem; color:var(--muted); margin-bottom:0.4rem; }
  .field .val { display:flex; gap:0.4rem; }
  .field .val input { flex:1; border:1px solid var(--border); border-radius:0.4rem; padding:0.45rem 0.6rem; font-family:ui-monospace,Consolas,monospace; font-size:0.78rem; background:var(--panel); min-width:0; }
  .switchrow { display:flex; justify-content:space-between; align-items:center; font-size:0.85rem; padding:0.55rem 0; border-bottom:1px solid var(--border); gap:0.5rem; }
  .sw { width:2rem; height:1.1rem; border-radius:0.6rem; background:var(--accent); position:relative; cursor:pointer; flex:none; }
  .sw.off { background:var(--muted); }
  .sw i { position:absolute; right:0.12rem; top:0.12rem; width:0.85rem; height:0.85rem; border-radius:50%; background:#fff; transition:.15s; }
  .sw.off i { right:auto; left:0.12rem; }
  .seg-opt { display:flex; gap:0.4rem; flex-wrap:wrap; }
  .seg-opt span { border:1px solid var(--border); border-radius:0.4rem; padding:0.3rem 0.7rem; font-size:0.78rem; cursor:pointer; }
  .seg-opt span.on { background:var(--accent); color:#fff; border-color:var(--accent); }
  .slider { flex:1; }
  .modal-foot { display:flex; justify-content:flex-end; gap:0.5rem; margin-top:1.2rem; }
  .prog { height:0.4rem; background:var(--hover); border-radius:0.2rem; overflow:hidden; margin-top:0.5rem; }
  .prog i { display:block; height:100%; background:var(--accent); }
  .cal { margin-top:0.4rem; }
  .cal-head { display:flex; align-items:center; justify-content:space-between; font-size:0.8rem; margin-bottom:0.45rem; }
  .cal-head b { font-weight:600; }
  .cal-prev,.cal-next { cursor:pointer; width:1.4rem; height:1.4rem; display:inline-flex; align-items:center; justify-content:center; border-radius:0.3rem; font-size:1.1rem; color:var(--muted); }
  .cal-prev:hover,.cal-next:hover { background:var(--hover); color:var(--text); }
  .cal-grid { display:grid; grid-template-columns:repeat(7,1fr); gap:0.1rem; }
  .cal-grid i { font-style:normal; text-align:center; }
  .cal-dow { font-size:0.68rem; color:var(--muted); margin-bottom:0.2rem; }
  .cal-cell { position:relative; height:1.7rem; line-height:1.7rem; font-size:0.76rem; border-radius:0.35rem; cursor:default; }
  .cal-cell.has { cursor:pointer; color:var(--accent); font-weight:600; }
  .cal-cell.has:hover { background:var(--hover); }
  .cal-cell.has::after { content:''; position:absolute; bottom:0.16rem; left:50%; transform:translateX(-50%); width:0.22rem; height:0.22rem; border-radius:50%; background:var(--accent); }
  .cal-cell.today { border:1px solid var(--border); }
  .cal-cell.sel { background:var(--accent); color:#fff; }
  .cal-cell.sel::after { background:#fff; }
  .cal-daytitle { font-size:0.74rem; color:var(--muted); margin:0.7rem 0 0.3rem; padding-bottom:0.3rem; border-bottom:1px solid var(--border); }
  .cal-item { display:flex; justify-content:space-between; gap:0.4rem; align-items:center; font-size:0.75rem; padding:0.35rem 0.4rem; border-radius:0.35rem; cursor:pointer; }
  .cal-item:hover { background:var(--hover); }
  .cal-item.on { background:var(--accent-soft); }
  .cal-item .st { white-space:nowrap; font-family:ui-monospace,Consolas,monospace; }
  .export-wrap { position:relative; margin-left:auto; }
  .export-menu { position:absolute; right:0; top:1.9rem; z-index:15; background:var(--panel); border:1px solid var(--border); border-radius:0.5rem; box-shadow:0 6px 24px rgba(0,0,0,.14); padding:0.3rem; min-width:11rem; display:none; }
  .export-menu.on { display:block; }
  .export-menu div { padding:0.45rem 0.7rem; font-size:0.82rem; border-radius:0.35rem; cursor:pointer; white-space:nowrap; }
  .export-menu div:hover { background:var(--hover); }
  body.dark {
    --bg:#161617; --panel:#242426; --panel2:#1d1d1f; --left-bg:#1d1d1f;
    --text:#f5f5f7; --muted:#a1a1a6; --border:#3a3a3c; --accent:#0a84ff;
    --accent-soft:#132a45; --hover:#2c2c2e; --mark:#5a4a12;
  }
</style>
</head>
<body>
<div class="app">
  <div class="titlebar"><i class="dot r"></i><i class="dot y"></i><i class="dot g"></i></div>
  <div class="toolbar">
    <span class="brand">录音转写工作台</span>
    <button class="btn" id="refresh">↻ 刷新</button>
  </div>
  <div class="layout">
    <aside class="col left">
      <input class="search" id="search" placeholder="搜索会议、逐字稿、总结…">
      <div class="tags" id="navTags"><span class="on" data-nav="all">全部会议</span><span data-nav="star">星标</span><span class="cnt">场次</span></div>
      <div id="meetingList"></div>
      <div class="leftgear" id="settingsBtn">⚙ 设置</div>
    </aside>
    <main class="col center" id="center"></main>
    <aside class="col right" id="right"></aside>
  </div>
  <div class="statusbar" id="statusbar">本机运行 · 未联网</div>
</div>

<div class="overlay" id="overlay">
  <div class="modal">
    <h3>设置</h3>
    <div class="mtabs" id="mtabs">
      <span data-tab="general">通用</span>
      <span data-tab="record" class="on">录音目录</span>
      <span data-tab="asr">转写</span>
      <span data-tab="ai">AI 总结</span>
      <span data-tab="appearance">外观</span>
    </div>
    <div id="modalBody"></div>
    <div class="modal-foot"><button class="btn" id="cancelSettings">取消</button><button class="btn pri" id="saveSettings">保存</button></div>
  </div>
</div>

<script id="data" type="application/json">__DATA__</script>
<script>
const INIT = JSON.parse(document.getElementById('data').textContent);
let DB = { meetings: INIT.meetings||[], audioBase: INIT.audioBase||'' };
let settings = Object.assign({record_dir:'',auto_scan:true,scan_interval:5,on_new:'prompt',scan_subdirs:true,theme:'light',font_scale:1}, INIT.settings||{});
let scanInfo = INIT.scan||{new:[],new_count:0,dir:'',last_scan:''};
let meetings = DB.meetings;
let current = null, terms = [], navMode = 'all', modalTab = 'record', draft = null, processing = false;
let calMonth = null, calDay = '';   // 录音日历：当前显示月份与选中日期
let openDates = null;               // 左栏展开的日期集合（null=尚未初始化）
let stars = {}; try{ stars = JSON.parse(localStorage.getItem('luyinka_stars')||'{}'); }catch(e){}
const $ = id => document.getElementById(id);
const api = (name, ...args) => (window.pywebview && window.pywebview.api && window.pywebview.api[name])
  ? window.pywebview.api[name](...args) : Promise.resolve(null);
const esc = s => String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = sec => { sec=Math.floor(Number(sec)||0); return String(Math.floor(sec/3600)).padStart(2,'0')+':'+String(Math.floor(sec%3600/60)).padStart(2,'0')+':'+String(sec%60).padStart(2,'0'); };
const marked = (text,ts) => { let h=esc(text); (ts||[]).forEach(t=>{ t=t.trim(); if(!t) return; const re=new RegExp('('+t.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+')','gi'); h=h.replace(re,'<mark>$1</mark>'); }); return h; };
const fmtSize = n => n>1048576 ? (n/1048576).toFixed(1)+' MB' : (n/1024).toFixed(0)+' KB';

function applyAppearance(){
  const t = draft ? draft.theme : settings.theme;
  const sc = draft ? draft.font_scale : settings.font_scale;
  const dark = t==='dark' || (t==='system' && matchMedia('(prefers-color-scheme:dark)').matches);
  document.body.classList.toggle('dark', dark);
  document.documentElement.style.setProperty('--scale', Number(sc)||1);
}

function groupByDate(list){ const g={}; list.forEach(m=>{ const d=m.record_date||m.date; (g[d]=g[d]||[]).push(m); }); return g; }
function dayLabel(d){
  const today=new Date(), y=new Date(today); y.setDate(y.getDate()-1);
  const f=x=>x.toISOString().slice(0,10);
  if(d===f(today)) return '今天'; if(d===f(y)) return '昨天'; return d;
}

function renderList(){
  let list = meetings.slice();
  if(navMode==='star') list = list.filter(m=>stars[m.id]);
  if(terms.length) list = list.filter(m=>{
    const all = m.title+' '+(m.segments||[]).map(s=>s.text).join(' ')+' '+(m.summary_content||'');
    return terms.every(t=>all.toLowerCase().includes(t.toLowerCase()));
  });
  const g = groupByDate(list);
  const keys = Object.keys(g).sort().reverse();
  if(openDates===null){
    openDates=new Set();
    if(current) openDates.add(meetDate(current));   // 默认展开当前会议所在日期
  }
  if(terms.length) keys.forEach(k=>openDates.add(k)); // 搜索结果自动展开
  $('meetingList').innerHTML = keys.length ? keys.map(k=>{
    const open=openDates.has(k), arr=g[k];
    return `<div class="grp grp-toggle ${open?'open':''}" data-date="${esc(k)}"><span class="caret">${open?'▾':'▸'}</span><span>${esc(dayLabel(k))}</span><span class="grp-n">${arr.length}</span></div>`+
      (open?arr.map(m=>
        `<div class="mi ${current&&current.id===m.id?'on':''}" data-id="${esc(m.id)}"><span>${stars[m.id]?'★ ':''}${esc(m.title)}</span><span class="sub">${fmt(m.duration)}</span></div>`
      ).join(''):'');
  }).join('') : '<div class="empty">没有匹配的会议</div>';
  document.querySelectorAll('.grp-toggle').forEach(el=>el.onclick=()=>{
    const d=el.dataset.date;
    if(openDates.has(d)) openDates.delete(d); else openDates.add(d);
    renderList();
  });
  document.querySelectorAll('.mi').forEach(el=>el.onclick=()=>openMeeting(el.dataset.id));
}

function timelineHtml(segs){
  return segs.map((s,i)=>`<div class="tlrow" data-i="${i}"><span class="ts">${fmt(s.start)}</span><span>${marked(s.text,terms)}</span></div>`).join('')||'<div class="st">(无)</div>';
}
function bindTimeline(){
  document.querySelectorAll('.tlrow,.segline,.res-hit').forEach(el=>{
    el.onclick=()=>{ const i=Number(el.dataset.i); if(!isNaN(i)) jump(i); };
  });
}

function renderWorkbench(){
  if(processing) return `<div class="wb"><h4><span>正在处理新录音…</span></h4><div id="procList"><div class="row"><span>正在启动本机转写…</span></div><div class="prog"><i style="width:5%"></i></div></div></div>`;
  if(!scanInfo.new_count) return `<div class="wb"><h4><span>工作台 · 无新录音</span></h4><div class="meta">来源 ${esc(scanInfo.dir||'—')} · 上次扫描 ${esc(scanInfo.last_scan||'从未')}</div></div>`;
  const opts = scanInfo.on_new==='auto'
    ? `<button class="btn pri" id="autoProcessBtn">自动处理已开启</button>`
    : `<button class="btn pri" id="processAllBtn">全部处理</button>`;
  return `<div class="wb"><h4><span>工作台 · 发现 ${scanInfo.new_count} 个新录音</span>${opts}</h4>
    ${scanInfo.new.slice(0,5).map(n=>`<div class="row"><span>${esc(n.name)}</span><span>${fmtSize(n.size)} · 待处理</span></div>`).join('')}
    <div class="meta">来源 ${esc(scanInfo.dir||'—')} · 上次扫描 ${esc(scanInfo.last_scan||'从未')} · 每 ${scanInfo.scan_interval} 分钟扫描</div></div>`;
}

function parseSummary(md){
  const out={sections:[]};
  if(!md) return out;
  const lines=md.split(/\r?\n/); let cur=null, lead=null;
  for(const raw of lines){
    const line=raw.trim();
    if(/^##\s+/.test(line)){ cur={title:line.replace(/^##\s+/,''),blocks:[]}; out.sections.push(cur); continue; }
    if(!line || line.startsWith('>')) continue;
    if(/^###\s+/.test(line)){ if(cur) cur.blocks.push({h:line.replace(/^###\s+/,'')}); continue; }
    if(line.startsWith('#')) continue;
    if(cur){
      if(/^[-*]\s+/.test(line)) cur.blocks.push({t:line.replace(/^[-*]\s+/,'')});
      else cur.blocks.push({p:line});
      continue;
    }
    if(lead===null) lead=line;
  }
  out.lead=lead||'';
  return out;
}
function renderSummaryMd(m){
  const p=parseSummary(m.summary_content);
  if(!p.sections.length) return '<div class="st">本机总结文件为空，暂用逐字稿开头。</div>';
  return p.sections.map(sec=>{
    const title=sec.title==='一句话摘要'?'摘要':sec.title;
    const parts=(sec.blocks||[]).map(b=>{
      if(b.h!==undefined) return `<div class="subh">${esc(b.h)}</div>`;
      const text = b.t!==undefined ? b.t : b.p;
      const mm=text.match(/^\[(\d\d:\d\d:\d\d)\]\s*(.*)$/);
      if(mm) return `<div class="pt"><span class="ts">${mm[1]}</span>${marked(mm[2],terms)}</div>`;
      return `<div class="pt${b.t!==undefined?'':' lead-pt'}">${marked(text,terms)}</div>`;
    });
    const body = parts.length ? parts.join('') : '<div class="st">(无)</div>';
    return `<div class="card"><h5>${esc(title)}</h5>${body}</div>`;
  }).join('');
}

function renderCenter(){
  const wb = renderWorkbench();
  if(!current){
    $('center').innerHTML = wb + '<div class="empty">选择左侧一场会议开始查看</div>';
    bindWorkbench(); return;
  }
  const m=current, segs=m.segments||[];
  const lead = terms.length ? (segs.find(s=>terms.every(t=>s.text.toLowerCase().includes(t.toLowerCase())))||{}).text||segs[0]?.text||'' : segs[0]?.text||'';
  $('center').innerHTML = `${wb}
    <div class="h1">${esc(m.title)}</div>
    <div class="meta-line">录音于 ${esc(m.record_date||m.date)} · 时长 ${fmt(m.duration)} · 本机转写</div>
    <div class="tabs" id="tabs"><span class="on" data-tab="summary">会议总结</span><span data-tab="transcript">逐字稿</span><span data-tab="audio">原音</span>
      <span class="export-wrap"><button class="btn" id="exportBtn">导出 ▾</button><div class="export-menu" id="exportMenu">
        <div data-kind="summary">⬇ 下载会议总结 (.md)</div>
        <div data-kind="transcript">⬇ 下载逐字稿 (.md)</div>
        <div data-kind="audio">⬇ 下载原音</div>
        <div data-kind="all">📦 打包下载全部 (.zip)</div>
      </div></span></div>
    <section class="tabpane on" data-pane="summary">
      <div class="sumbar"><span class="st">${m.cloud_summary?'🤖 云端改写':'📄 本机规则摘要'}</span><button class="btn" id="cloudBtn">${settings.cloud_enabled?'云端重写总结':'开启云端总结'}</button></div>
      ${m.summary_content ? renderSummaryMd(m) : `<div class="card"><h5>一句话摘要</h5><div class="pt">${marked(lead,terms)}</div></div>
      <div class="card"><h5>关键要点</h5>${segs.slice(0,8).map(s=>`<div class="pt"><span class="ts">${fmt(s.start)}</span>${marked(s.text,terms)}</div>`).join('')||'<div class="st">(无)</div>'}</div>`}
    </section>
    <section class="tabpane" data-pane="transcript">
      <div class="card"><h5>逐字稿 · 本机 SenseVoice <span class="st">（点说话人可修改）</span></h5>${segs.map((s,i)=>`<div class="segline" data-i="${i}"><span class="ts">[${fmt(s.start)}]</span><span class="speaker" data-i="${i}" title="点击修改说话人">${s.speaker?esc(s.speaker):'—'}</span>${marked(s.text,terms)}</div>`).join('')||'<div class="st">没有识别到说话</div>'}</div>
    </section>
    <section class="tabpane" data-pane="audio">
      <div class="player"><audio id="player" controls preload="none"></audio></div>
      <div class="card"><h5>时间轴</h5>${timelineHtml(segs)}</div>
    </section>`;
  document.querySelectorAll('#tabs span[data-tab]').forEach(sp=>sp.onclick=()=>{
    document.querySelectorAll('#tabs span[data-tab]').forEach(x=>x.classList.toggle('on',x===sp));
    document.querySelectorAll('.tabpane').forEach(p=>p.classList.toggle('on',p.dataset.pane===sp.dataset.tab));
    if(sp.dataset.tab==='audio') setTimeout(setAudio,0);
  });
  bindTimeline(); bindWorkbench(); setAudio();
  const cb=$('cloudBtn'); if(cb) cb.onclick=onCloudSummarize;
  bindExport();
  document.querySelectorAll('.speaker').forEach(sp=>sp.onclick=()=>{
    const i=Number(sp.dataset.i), old=current.segments[i]?.speaker||'';
    const v=prompt('这段说话人（留空清除）：', old);
    if(v===null) return;
    const map={}; map[i]=v.trim();
    api('save_speakers', current.id, JSON.stringify(map)).then(r=>{
      if(r){ const o=typeof r==='string'?JSON.parse(r):r; if(o.ok){ current.segments[i].speaker=v.trim(); renderCenter(); } else alert(o.error||'保存失败'); }
    });
  });
}

function bindExport(){
  const btn=$('exportBtn'), menu=$('exportMenu');
  if(!btn||!menu) return;
  btn.onclick=e=>{ e.stopPropagation(); menu.classList.toggle('on'); };
  if(!window.__exportOutsideBound){
    window.__exportOutsideBound=true;
    document.addEventListener('click', e=>{
      const m=$('exportMenu'); if(m && !e.target.closest('.export-wrap')) m.classList.remove('on');
    });
  }
  menu.querySelectorAll('div[data-kind]').forEach(it=>it.onclick=async e=>{
    e.stopPropagation();
    menu.classList.remove('on');
    await doExport(it.dataset.kind);
  });
}
async function doExport(kind){
  if(!current) return;
  const r=await api('export_meeting', current.id, kind);
  if(!r){ alert('导出失败：未连接到本机服务'); return; }
  const o=typeof r==='string'?JSON.parse(r):r;
  if(o.ok) alert('已保存到：\n'+o.path);
  else if(!o.cancelled) alert('导出失败：'+(o.error||'未知错误'));
}

async function onCloudSummarize(){
  if(!settings.cloud_enabled){ openSettings(); document.querySelector('#mtabs span[data-tab="ai"]')?.click(); alert('请先在「设置 → AI 总结」里开启并填写 API Key'); return; }
  const btn=$('cloudBtn'); btn.textContent='云端总结中…'; btn.disabled=true;
  const r=await api('cloud_summarize', current.id);
  if(r){ const o=typeof r==='string'?JSON.parse(r):r; if(o.started===false){ alert(o.error||'无法开始'); btn.textContent='云端重写总结'; btn.disabled=false; return; } }
  const timer=setInterval(async()=>{
    const raw=await api('cloud_status'); if(!raw) return;
    const s=typeof raw==='string'?JSON.parse(raw):raw;
    btn.textContent=s.message||'云端总结中…';
    if(!s.running){ clearInterval(timer); await refreshAll(); alert(s.message&&s.message.startsWith('失败')?s.message:'云端总结完成'); }
  },500);
}

function meetDate(m){ return m.record_date||m.date||''; }

// 按录音日期统计每天的会议
function dateMap(){
  const map={};
  meetings.forEach(m=>{ const d=meetDate(m); if(d) (map[d]=map[d]||[]).push(m); });
  return map;
}

function calendarHtml(){
  const map=dateMap();
  const days=Object.keys(map).sort();
  if(!calMonth){
    // 初始定位到当前会议所在月，否则最新录音月
    const base=(current&&meetDate(current))||days[days.length-1]||'';
    calMonth=base?{y:+base.slice(0,4), m:+base.slice(5,7)-1}:{y:new Date().getFullYear(), m:new Date().getMonth()};
  }
  const y=calMonth.y, mo=calMonth.m;
  const first=new Date(y,mo,1), start=(first.getDay()+6)%7, total=new Date(y,mo+1,0).getDate();
  const pad=n=>String(n).padStart(2,'0');
  let cells='';
  for(let i=0;i<start;i++) cells+='<i class="cal-cell pad"></i>';
  for(let d=1;d<=total;d++){
    const key=`${y}-${pad(mo+1)}-${pad(d)}`;
    const n=(map[key]||[]).length;
    const cls=['cal-cell'];
    if(n) cls.push('has');
    if(key===calDay) cls.push('sel');
    const today=new Date(); if(y===today.getFullYear()&&mo===today.getMonth()&&d===today.getDate()) cls.push('today');
    cells+=`<i class="${cls.join(' ')}" data-date="${key}" ${n?`title="${n} 场录音"`:''}>${d}</i>`;
  }
  const monthLabel=`${y} 年 ${mo+1} 月`;
  let dayList='';
  if(calDay){
    const list=map[calDay]||[];
    dayList=`<div class="cal-daytitle">${esc(calDay)} · ${list.length} 场</div>`+
      (list.length?list.map(m=>`<div class="cal-item ${current&&current.id===m.id?'on':''}" data-id="${esc(m.id)}"><span>${esc(m.title)}</span><span class="st">${fmt(m.duration)}</span></div>`).join(''):'<div class="st">这天没有录音</div>');
  } else {
    dayList='<div class="st">点有标记的日期查看当天录音</div>';
  }
  return `<div class="st" style="margin-top:1rem">录音日历</div>
    <div class="cal">
      <div class="cal-head"><span class="cal-prev" title="上个月">‹</span><b>${monthLabel}</b><span class="cal-next" title="下个月">›</span></div>
      <div class="cal-grid cal-dow"><i>一</i><i>二</i><i>三</i><i>四</i><i>五</i><i>六</i><i>日</i></div>
      <div class="cal-grid">${cells}</div>
    </div>
    ${dayList}`;
}

function bindCalendar(){
  const root=$('right'); if(!root) return;
  root.querySelectorAll('.cal-cell[data-date]').forEach(el=>el.onclick=()=>{
    calDay=(calDay===el.dataset.date)?'':el.dataset.date;
    if(calDay && openDates){ openDates.add(calDay); renderList(); }  // 联动展开左栏
    renderRight();
  });
  const prev=root.querySelector('.cal-prev'), next=root.querySelector('.cal-next');
  if(prev) prev.onclick=()=>{ calMonth={y:calMonth.y,m:calMonth.m-1}; if(calMonth.m<0){calMonth.m=11;calMonth.y--;} calDay=''; renderRight(); };
  if(next) next.onclick=()=>{ calMonth={y:calMonth.y,m:calMonth.m+1}; if(calMonth.m>11){calMonth.m=0;calMonth.y++;} calDay=''; renderRight(); };
  root.querySelectorAll('.cal-item').forEach(el=>el.onclick=()=>openMeeting(el.dataset.id));
}

function renderRight(){
  if(!current){
    $('right').innerHTML='<div class="st">会议信息</div><div class="empty">未选择会议</div>'+calendarHtml();
    bindCalendar(); return;
  }
  const m=current, segs=m.segments||[];
  const hits = terms.length ? segs.map((s,i)=>({s,i})).filter(o=>terms.every(t=>o.s.text.toLowerCase().includes(t.toLowerCase()))) : [];
  let html = `<div class="st">会议信息</div>
    <div class="kv"><span>录音日期</span><span>${esc(m.record_date||m.date)}</span></div>
    <div class="kv"><span>时长</span><span>${fmt(m.duration)}</span></div>
    <div class="kv"><span>段落</span><span>${segs.length}</span></div>
    <div class="kv"><span>转写</span><span>本机</span></div>`;
  if(terms.length){
    html += `<div class="st" style="margin-top:1rem">命中 ${hits.length} 处</div>`;
    html += hits.slice(0,8).map(o=>`<div class="tlrow" data-i="${o.i}"><span class="ts">${fmt(o.s.start)}</span><span>${marked(o.s.text,terms)}</span></div>`).join('')||'<div class="st">当前会议无命中</div>';
  }
  html += calendarHtml();
  $('right').innerHTML = html; bindTimeline(); bindCalendar();
}

function audioSrc(m){
  const raw=String(m.audio||'').replace(/\\/g,'/'), base=String(DB.audioBase||'').replace(/\\/g,'/');
  if(/^https?:|^file:/i.test(raw)) return raw;
  return 'file:///' + (base?base.replace(/^\/+/,'')+'/':'') + raw;
}
function setAudio(){ const a=$('player'); if(a&&current) a.src=audioSrc(current); }
function jump(i){
  if(!current) return;
  document.querySelectorAll('#tabs span[data-tab]').forEach(x=>x.classList.toggle('on',x.dataset.tab==='audio'));
  document.querySelectorAll('.tabpane').forEach(p=>p.classList.toggle('on',p.dataset.pane==='audio'));
  document.querySelectorAll('.tlrow,.segline').forEach(el=>el.classList.toggle('hit',Number(el.dataset.i)===i));
  setTimeout(()=>{ const a=$('player'); if(a){ a.currentTime=Number((current.segments[i]||{}).start)||0; a.play().catch(()=>{}); } setAudio(); },0);
}

function renderAll(){ renderList(); renderCenter(); renderRight(); applyAppearance(); }
function openMeeting(id){ current=meetings.find(m=>m.id===id)||null; renderAll(); }

function bindWorkbench(){
  const b=$('processAllBtn'), ab=$('autoProcessBtn');
  if(b) b.onclick=()=>processNew(scanInfo.new.map(n=>n.key));
  if(ab) ab.onclick=()=>processNew(scanInfo.new.map(n=>n.key));
}

async function processNew(keys){
  if(!keys||!keys.length) return;
  processing=true;
  renderCenter();
  const res = await api('process_new', JSON.stringify(keys));
  if(res){ const r=typeof res==='string'?JSON.parse(res):res; if(r.started===false){ processing=false; renderCenter(); alert(r.error||'无法开始处理'); return; } }
  let lastDone=-1;
  const timer=setInterval(async()=>{
    const raw=await api('process_status');
    if(!raw) return;
    const s=typeof raw==='string'?JSON.parse(raw):raw;
    if(s.done!==lastDone){ lastDone=s.done; updateProcList(keys,s); }
    if(!s.running){
      clearInterval(timer);
      processing=false;
      await refreshAll();
      alert(`处理完成：${s.done} 个录音已转写归档${s.message==='部分失败'?'（部分失败，见日志）':''}`);
      if(window.__processResult && window.__processResult.failed && window.__processResult.failed.length)
        alert('失败详情:\n'+window.__processResult.failed.join('\n'));
    }
  }, 500);
}
function updateProcList(keys,s){
  const pl=$('procList'); if(!pl) return;
  const pct=s.total?Math.round(s.done/s.total*100):0;
  pl.innerHTML = keys.map(k=>{
    const n=scanInfo.new.find(x=>x.key===k)||{name:k.rsplit?k.rsplit('|',1)[0]:k};
    const name=n.name||String(k);
    const isDone=s.done>=keys.indexOf(k)+1;
    return `<div class="row"><span>${esc(name)}</span><span>${isDone?'✓ 完成':(s.current===name?'处理中…':'等待')}</span></div>`;
  }).join('') + `<div class="prog"><i style="width:${pct}%"></i></div><div class="meta">${esc(s.message||'')} · ${s.done}/${s.total}</div>`;
}
window.onProcessFinished = function(){ };

async function refreshAll(){
  const [data, sc, st] = await Promise.all([api('get_data'), api('scan'), api('get_settings')]);
  if(data){ try{ const o=typeof data==='string'?JSON.parse(data):data; DB.audioBase=o.audioBase||DB.audioBase; meetings=o.meetings||[]; }catch(e){} }
  if(sc){ try{ scanInfo=typeof sc==='string'?JSON.parse(sc):sc; }catch(e){} }
  if(st){ try{ settings=typeof st==='string'?JSON.parse(st):st; }catch(e){} }
  if(current){ const f=meetings.find(m=>m.id===current.id); current=f||(meetings[meetings.length-1]||null); }
  $('statusbar').textContent = `本机运行 · 未联网 · 共 ${meetings.length} 场会议 · ${scanInfo.new_count||0} 个新录音`;
  renderAll();
}

function modalHtml(){
  const d=draft||settings;
  if(modalTab==='general') return `<div class="switchrow"><span>启动时自动扫描新录音</span><span class="sw ${d.auto_scan?'':'off'}" data-sw="auto_scan"><i></i></span></div>
    <div class="st" style="margin-top:0.8rem">数据全部保存在本机 <code>${esc(DB.audioBase||'')}</code>，不会上传。</div>`;
  if(modalTab==='record') return `<div class="field"><label>录音存放目录</label><div class="val">
      <input id="recordDir" value="${esc(d.record_dir||'')}" placeholder="默认：工作台目录下的 待处理">
      <button class="btn" id="chooseDir">选择…</button><button class="btn" id="openDir">打开</button></div></div>
    <div class="st">应用会扫描此目录里的新录音，显示在工作台。默认目录：${esc(DB.audioBase||'')}\\待处理</div>
    <div class="switchrow"><span>自动扫描</span><span class="sw ${d.auto_scan?'':'off'}" data-sw="auto_scan"><i></i></span></div>
    <div class="switchrow"><span>扫描间隔</span><select id="scanInterval">${[1,5,10,30,60].map(v=>`<option value="${v}" ${d.scan_interval==v?'selected':''}>每 ${v} 分钟</option>`).join('')}</select></div>
    <div class="switchrow"><span>扫描子文件夹</span><span class="sw ${d.scan_subdirs?'':'off'}" data-sw="scan_subdirs"><i></i></span></div>
    <div class="switchrow"><span>发现新录音后</span><select id="onNew"><option value="prompt" ${d.on_new==='prompt'?'selected':''}>提示我，手动处理</option><option value="auto" ${d.on_new==='auto'?'selected':''}>自动处理</option></select></div>`;
  if(modalTab==='asr') return `<div class="st">转写在本机使用 SenseVoice 模型完成，首次需下载模型，之后可断网使用。</div>
    <div class="switchrow"><span>转写语言</span><span>中文（zh）</span></div>
    <div class="switchrow"><span>识别引擎</span><span>本机 SenseVoice int8</span></div>
    <div class="switchrow"><span>音频处理</span><span>本机 ffmpeg + Silero VAD</span></div>
    <div class="st" style="margin-top:0.8rem">这些为当前固定配置，后续版本会开放切换。</div>`;
  if(modalTab==='ai') return `<div class="switchrow"><span>启用云端总结 <span style="font-size:0.72rem;color:var(--muted)">（仅上传转写文字）</span></span><span class="sw ${d.cloud_enabled?'':'off'}" data-sw="cloud_enabled"><i></i></span></div>
    <div class="field" style="margin-top:1rem"><label>API 密钥（仅存本机，不会显示明文）</label><input type="password" id="cloudKey" value="" autocomplete="off" placeholder="${d.cloud_key_set?'已保存，留空则不修改':'sk-...'}" style="width:100%;border:1px solid var(--border);border-radius:0.4rem;padding:0.45rem 0.6rem;font-size:0.8rem;background:var(--panel)"></div>
    <div class="st" style="margin-top:0.3rem">${d.cloud_key_set?'密钥已保存在本机设置文件，界面不回显。':'尚未配置密钥。'} <a href="javascript:void(0)" id="clearKey" style="color:var(--accent);text-decoration:none">清除已保存的密钥</a></div>
    <div class="field"><label>服务地址</label><input id="cloudBase" value="${esc(d.cloud_base||'')}" style="width:100%;border:1px solid var(--border);border-radius:0.4rem;padding:0.45rem 0.6rem;font-size:0.8rem;background:var(--panel)"></div>
    <div class="field"><label>模型</label><input id="cloudModel" value="${esc(d.cloud_model||'')}" style="width:100%;border:1px solid var(--border);border-radius:0.4rem;padding:0.45rem 0.6rem;font-size:0.8rem;background:var(--panel)"></div>
    <div class="st">云端总结会把转写文字发到上述服务，音频不上传。关闭时自动使用本机规则摘要。当前在会议详情页点「云端重写」生成。</div>`;
  const sc=d.font_scale||1;
  return `<div class="field"><label>外观主题</label><div class="seg-opt" id="themeOpt">
      <span data-v="light" class="${d.theme==='light'?'on':''}">亮色</span>
      <span data-v="dark" class="${d.theme==='dark'?'on':''}">暗色</span>
      <span data-v="system" class="${d.theme==='system'?'on':''}">跟随系统</span></div></div>
    <div class="field"><label>字体大小</label><div style="display:flex;align-items:center;gap:0.6rem">
      <button class="btn" id="fontMinus">A−</button>
      <input class="slider" type="range" id="fontRange" min="80" max="135" value="${Math.round(sc*100)}">
      <button class="btn" id="fontPlus">A+</button>
      <span id="fontVal" style="min-width:2.5rem;text-align:right">${Math.round(sc*100)}%</span></div></div>
    <div class="st">设置保存后对整个应用生效，偏好存在本机。</div>`;
}

function renderModal(){
  $('modalBody').innerHTML = modalHtml();
  document.querySelectorAll('.sw').forEach(sw=>sw.onclick=()=>{
    const key=sw.dataset.sw; draft[key]=!draft[key]; sw.classList.toggle('off',!draft[key]);
  });
  const rd=$('recordDir'); if(rd) rd.oninput=e=>draft.record_dir=e.target.value;
  const si=$('scanInterval'); if(si) si.onchange=e=>draft.scan_interval=Number(e.target.value);
  const on=$('onNew'); if(on) onchangeSafe(on,e=>draft.on_new=e.target.value);
  const ck=$('cloudKey'); if(ck) ck.oninput=e=>{draft.cloud_api_key=e.target.value; draft.clear_cloud_key=false;};
  const ckl=$('clearKey'); if(ckl) ckl.onclick=()=>{draft.cloud_api_key=''; draft.clear_cloud_key=true; draft.cloud_key_set=false; renderModal();};
  const cb=$('cloudBase'); if(cb) cb.oninput=e=>draft.cloud_base=e.target.value;
  const cm=$('cloudModel'); if(cm) cm.oninput=e=>draft.cloud_model=e.target.value;
  document.querySelectorAll('#themeOpt span').forEach(sp=>sp.onclick=()=>{
    draft.theme=sp.dataset.v;
    document.querySelectorAll('#themeOpt span').forEach(x=>x.classList.toggle('on',x===sp));
    applyAppearance();
  });
  const fr=$('fontRange');
  if(fr) fr.oninput=e=>{ draft.font_scale=Number(e.target.value)/100; $('fontVal').textContent=e.target.value+'%'; applyAppearance(); };
  const fm=$('fontMinus'); if(fm) fm.onclick=()=>{ draft.font_scale=Math.max(0.8,(draft.font_scale||1)-0.05); syncFont(); };
  const fp=$('fontPlus'); if(fp) fp.onclick=()=>{ draft.font_scale=Math.min(1.35,(draft.font_scale||1)+0.05); syncFont(); };
  const cd=$('chooseDir');
  if(cd) cd.onclick=async()=>{ const p=await api('choose_folder'); if(p){ draft.record_dir=p; $('recordDir').value=p; } };
  const od=$('openDir'); if(od) od.onclick=()=>api('open_folder','record');
}
function syncFont(){ const v=Math.round((draft.font_scale||1)*100); const fr=$('fontRange'); if(fr) fr.value=v; const fv=$('fontVal'); if(fv) fv.textContent=v+'%'; applyAppearance(); }
function onchangeSafe(el,fn){ el.onchange=fn; }

function openSettings(){
  draft = JSON.parse(JSON.stringify(settings));
  modalTab = 'record';
  document.querySelectorAll('#mtabs span').forEach(x=>x.classList.toggle('on',x.dataset.tab===modalTab));
  renderModal(); $('overlay').classList.add('on');
}
function closeSettings(){ draft=null; $('overlay').classList.remove('on'); applyAppearance(); }

$('settingsBtn').onclick=openSettings;
$('cancelSettings').onclick=closeSettings;
$('saveSettings').onclick=async()=>{
  const raw=await api('save_settings',JSON.stringify(draft||settings));
  if(raw){ try{ const r=typeof raw==='string'?JSON.parse(raw):raw; if(r.settings) settings=r.settings; }catch(e){} }
  closeSettings(); await refreshAll();
};
document.querySelectorAll('#mtabs span').forEach(sp=>sp.onclick=()=>{
  modalTab=sp.dataset.tab;
  document.querySelectorAll('#mtabs span').forEach(x=>x.classList.toggle('on',x===sp));
  renderModal();
});
$('overlay').onclick=e=>{ if(e.target===$('overlay')) closeSettings(); };
$('refresh').onclick=async()=>{ const b=$('refresh'); b.textContent='↻ 读取中…'; await refreshAll(); b.textContent='↻ 刷新'; };

$('search').oninput=e=>{
  terms=e.target.value.trim().split(/\s+/).filter(Boolean);
  if(terms.length){
    const segAll=meetings.map(m=>({m,text:(m.title+' '+(m.segments||[]).map(s=>s.text).join(' ')+' '+(m.summary_content||'')).toLowerCase()}));
    const hit=segAll.find(o=>terms.every(t=>o.text.includes(t.toLowerCase())));
    if(hit) current=hit.m;
  }
  renderAll();
};
document.querySelectorAll('#navTags span[data-nav]').forEach(sp=>sp.onclick=()=>{
  navMode=sp.dataset.nav;
  document.querySelectorAll('#navTags span[data-nav]').forEach(x=>x.classList.toggle('on',x===sp));
  renderList();
});

applyAppearance();
renderAll();
if(meetings.length) openMeeting(meetings[meetings.length-1].id);
refreshAll();

if(settings.auto_scan && window.pywebview && window.pywebview.api){
  setInterval(async()=>{ const sc=await api('scan'); if(sc){ try{ const o=typeof sc==='string'?JSON.parse(sc):sc; scanInfo=o; if(o.new_count && o.on_new==='auto') processNew(o.new.map(n=>n.key)); else renderCenter(); }catch(e){} } }, Math.max(1,settings.scan_interval)*60000);
}
</script>
</body>
</html>
"""


_RECORD_DATE_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")


def _record_date(m: dict) -> str:
    """从标题（手机录音文件名）解析录音日期；解析不到则回退到 date（导入日）。"""
    hit = _RECORD_DATE_RE.search(str(m.get("title") or ""))
    if hit:
        y, mo, d = hit.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    return str(m.get("date") or "")


def build_payload() -> dict:
    idx = json.loads(INDEX.read_text(encoding="utf-8")) if INDEX.exists() else {"meetings": []}
    enriched = []
    for m in idx.get("meetings", []):
        item = dict(m)
        item["record_date"] = _record_date(m)
        for key in ("transcript", "summary"):
            p = DATA / m.get(key, "")
            item[key + "_content"] = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
        enriched.append(item)
    return {
        "meetings": enriched,
        "audioBase": str(DATA),
        "settings": public_settings(),
        "scan": scan_recordings(),
    }


def main() -> None:
    payload = json.dumps(build_payload(), ensure_ascii=False).replace("</", "<\\/")
    icon_png = DATA / "图标.png"
    src_icon = DATA.parent / "图标" / "图标_512.png"
    if src_icon.exists():
        import shutil
        shutil.copy(src_icon, icon_png)
    html = APP_TEMPLATE.replace("__DATA__", payload).replace("__ICON__", "图标.png")
    out = DATA / "工作台.html"
    out.write_text(html, encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
