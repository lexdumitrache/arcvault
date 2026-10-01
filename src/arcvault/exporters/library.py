"""Standalone searchable HTML library: one file, no server, no framework."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING, Any

from arcvault.exporters import _folder_path, location_path

if TYPE_CHECKING:
    from arcvault.vault import Library


def _loc(path: list[tuple[str, str]], source: str) -> dict[str, Any]:
    return {"k": [k for k, _ in path], "n": [n for _, n in path], "s": source}


def export_library(lib: Library, out: Path) -> None:
    data = [
        {
            "t": r.title or r.url,
            "u": r.url,
            "d": r.domain or "",
            "y": r.resource_type.value if r.resource_type else "unknown",
            "c": r.category or "Other",
            "v": r.when.date().isoformat() if r.when else "",
            # Every place this resource was saved in Arc.
            "L": [_loc(location_path(loc), loc.source_type.value) for loc in r.locations],
        }
        for r in lib.unique
    ]
    folders = [_loc(_folder_path(f), f.source_type.value) for f in lib.folders]
    # No "<" may reach the inline script: "</script>" would end it early, and "<!--<script>"
    # (e.g. in a page title) switches the HTML parser into a state where it never ends.
    js = json.dumps({"items": data, "folders": folders}, ensure_ascii=False).replace("<", "\\u003c")
    html = TEMPLATE.replace("__DATA__", js).replace("__STAMP__", escape(f"{datetime.now(UTC):%Y-%m-%d}"))
    out.write_text(html, encoding="utf-8")


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ArcVault Library</title>
<style>
:root{--bg:#fbfaf8;--fg:#1d1d1f;--mut:#6b6b70;--line:#e6e3de;--card:#fff;--acc:#4b5bdc;--chip:#f0eee9}
@media (prefers-color-scheme:dark){:root{--bg:#141416;--fg:#ececef;--mut:#9a9aa2;--line:#2a2a2f;--card:#1c1c20;--acc:#8b97ff;--chip:#26262b}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
header{padding:20px 24px 12px;border-bottom:1px solid var(--line)}
h1{margin:0;font-size:20px}h1 small{color:var(--mut);font-weight:400;font-size:13px;margin-left:8px}
#stats{color:var(--mut);margin-top:4px;font-size:13px}
.bar{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
input,select{font:inherit;padding:7px 10px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--fg)}
input[type=search]{flex:1 1 260px}
main{display:grid;grid-template-columns:260px 1fr;min-height:calc(100vh - 130px)}
nav{border-right:1px solid var(--line);padding:12px 8px;overflow:auto;max-height:calc(100vh - 130px);position:sticky;top:0}
nav details{margin-left:10px}nav summary,nav a{cursor:pointer;display:block;padding:2px 6px;border-radius:6px;color:var(--fg);text-decoration:none;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
nav a:hover,nav summary:hover{background:var(--chip)}nav .on{background:var(--chip);font-weight:600}
nav .n{color:var(--mut);font-size:12px;margin-left:4px}
#list{padding:8px 24px 40px}
.r{padding:10px 0;border-bottom:1px solid var(--line)}
.r a.t{color:var(--fg);font-weight:550;text-decoration:none}.r a.t:hover{color:var(--acc);text-decoration:underline}
.meta{color:var(--mut);font-size:12px;margin-top:2px;display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.chip{background:var(--chip);border-radius:5px;padding:0 6px}
.locs{display:block}.locs div{margin-top:1px}
#more{margin:16px 0;padding:8px 14px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--fg);cursor:pointer}
@media (max-width:760px){main{grid-template-columns:1fr}nav{display:none}header,#list{padding-left:16px;padding-right:16px}}
</style></head><body>
<header>
<h1>ArcVault Library<small>exported __STAMP__</small></h1>
<div id="stats"></div>
<div class="bar">
<input type="search" id="q" placeholder="Search titles, URLs, folders…" autofocus>
<select id="cat"><option value="">All categories</option></select>
<select id="typ"><option value="">All types</option></select>
<select id="spc"><option value="">All spaces</option></select>
<select id="src"><option value="">All sources</option></select>
</div></header>
<main><nav id="tree"></nav><section id="list"></section></main>
<script>
const {items:DATA,folders:FOLDERS}=__DATA__;
const $=id=>document.getElementById(id);
const SEP='\u0001';
let folder=null, shown=200;
function esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
const safeUrl=u=>/^(https?|ftp|mailto):/i.test(u);
DATA.forEach(r=>{r.spaces=[...new Set(r.L.map(l=>l.n[0]))];r.srcs=[...new Set(r.L.map(l=>l.s))];
  r.keys=r.L.map(l=>l.k.join(SEP)+SEP);r.text=(r.t+' '+r.u+' '+r.L.map(l=>l.n.join(' ')).join(' ')).toLowerCase()});
function counts(get){const m={};DATA.forEach(r=>[].concat(get(r)).forEach(v=>m[v]=(m[v]||0)+1));return m}
function fill(sel,c,label){Object.keys(c).sort((a,b)=>c[b]-c[a]).forEach(v=>{const o=document.createElement('option');o.value=v;o.textContent=`${label?label(v):v} (${c[v]})`;sel.appendChild(o)})}
fill($('cat'),counts(r=>r.c));fill($('typ'),counts(r=>r.y),v=>v.replace('_',' '));fill($('spc'),counts(r=>r.spaces));fill($('src'),counts(r=>r.srcs));
const nLoc=DATA.reduce((n,r)=>n+r.L.length,0);
$('stats').textContent=`${DATA.length.toLocaleString()} resources · ${nLoc.toLocaleString()} saved locations · ${Object.keys(counts(r=>r.d)).length.toLocaleString()} domains`;
// Folder tree keyed by stable ids, so same-named folders stay separate; seeded so empty folders show.
const root={c:{},n:new Set()};
function walk(l,ri){let n=root;l.k.forEach((k,i)=>{n=n.c[k]=n.c[k]||{name:l.n[i],c:{},n:new Set()};if(ri!==undefined)n.n.add(ri)})}
FOLDERS.forEach(l=>walk(l));
DATA.forEach((r,ri)=>r.L.forEach(l=>walk(l,ri)));
function select(el,key){document.querySelectorAll('nav .on').forEach(x=>x.classList.remove('on'));el.classList.add('on');folder=key;shown=200;render()}
function tree(node,path,el){Object.entries(node.c).forEach(([k,ch])=>{const p=[...path,k];
 const a=document.createElement('a');a.innerHTML=`${esc(ch.name)}<span class="n">${ch.n.size}</span>`;a.onclick=e=>{e.preventDefault();select(a,p.join(SEP)+SEP)};
 if(Object.keys(ch.c).length){const d=document.createElement('details');const s=document.createElement('summary');s.appendChild(a);d.appendChild(s);el.appendChild(d);tree(ch,p,d)}else el.appendChild(a)})}
const all=document.createElement('a');all.textContent='All resources';all.className='on';all.onclick=e=>{e.preventDefault();select(all,null)};
$('tree').appendChild(all);tree(root,[],$('tree'));
function render(){
 const terms=$('q').value.toLowerCase().split(/\s+/).filter(Boolean),c=$('cat').value,y=$('typ').value,s=$('spc').value,src=$('src').value;
 const res=DATA.filter(r=>(!c||r.c===c)&&(!y||r.y===y)&&(!s||r.spaces.includes(s))&&(!src||r.srcs.includes(src))&&
   (!folder||r.keys.some(k=>k.startsWith(folder)))&&(!terms.length||terms.every(t=>r.text.includes(t))));
 const L=$('list');L.innerHTML=`<p class="meta">${res.length.toLocaleString()} results</p>`+res.slice(0,shown).map(r=>{
  const title=safeUrl(r.u)?`<a class="t" href="${esc(r.u)}" target="_blank" rel="noopener noreferrer">${esc(r.t)}</a>`:`<span class="t">${esc(r.t)}</span> <span class="meta">${esc(r.u)}</span>`;
  const locs=r.L.map(l=>`<div>${esc(l.n.join(' › '))} <span class="chip">${esc(l.s)}</span></div>`).join('');
  return `<div class="r">${title}<div class="meta"><span>${esc(r.d)}</span><span class="chip">${esc(r.y.replace('_',' '))}</span><span class="chip">${esc(r.c)}</span>${r.v?`<span>${r.v}</span>`:''}</div><div class="meta locs">${locs}</div></div>`}).join('');
 if(res.length>shown){const b=document.createElement('button');b.id='more';b.textContent=`Show more (${res.length-shown} left)`;b.onclick=()=>{shown+=500;render()};L.appendChild(b)}
}
['q','cat','typ','spc','src'].forEach(id=>$(id).addEventListener('input',()=>{shown=200;render()}));
render();
</script></body></html>
"""
