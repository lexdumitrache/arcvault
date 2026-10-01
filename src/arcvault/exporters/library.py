"""Standalone searchable HTML library: one file, no server, no framework."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING

from arcvault.exporters import tree_path

if TYPE_CHECKING:
    from arcvault.vault import Library


def export_library(lib: Library, out: Path, keep_duplicates: bool = False) -> None:
    rows = lib.resources if keep_duplicates else lib.unique
    data = [
        {
            "t": r.title or r.url,
            "u": r.url,
            "d": r.domain or "",
            "p": tree_path(r),
            "s": r.source_type.value,
            "y": r.resource_type.value if r.resource_type else "unknown",
            "c": r.category or "Other",
            "f": r.found_in,
            "v": r.when.date().isoformat() if r.when else "",
        }
        for r in rows
    ]
    # "</" inside a <script> would end it early.
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = TEMPLATE.replace("__DATA__", payload).replace("__STAMP__", escape(f"{datetime.now(UTC):%Y-%m-%d}"))
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
const DATA=__DATA__;
const $=id=>document.getElementById(id);
let folder=null, shown=200;
const count=(k)=>DATA.reduce((m,r)=>(m[r[k]]=(m[r[k]]||0)+1,m),{});
function fill(sel,key,label){const c=count(key);Object.keys(c).sort((a,b)=>c[b]-c[a]).forEach(v=>{const o=document.createElement('option');o.value=v;o.textContent=`${label?label(v):v} (${c[v]})`;sel.appendChild(o)})}
DATA.forEach(r=>r.sp=r.p[0]);
fill($('cat'),'c');fill($('typ'),'y',v=>v.replace('_',' '));fill($('spc'),'sp');fill($('src'),'s');
const domains=Object.keys(count('d')).length;
$('stats').textContent=`${DATA.length.toLocaleString()} resources · ${domains.toLocaleString()} domains · ${Object.keys(count('sp')).length} spaces`;
// folder tree
const root={};DATA.forEach(r=>{let n=root;r.p.forEach(p=>{n[p]=n[p]||{_n:0};n[p]._n++;n=n[p]})});
function tree(node,path,el){Object.keys(node).filter(k=>k!=='_n').sort().forEach(k=>{const p=[...path,k],kids=Object.keys(node[k]).length>1;
 const a=document.createElement('a');a.innerHTML=`${esc(k)}<span class="n">${node[k]._n}</span>`;a.onclick=e=>{e.preventDefault();folder=p.join('\u0000');document.querySelectorAll('nav .on').forEach(x=>x.classList.remove('on'));a.classList.add('on');shown=200;render()};
 if(kids){const d=document.createElement('details');const s=document.createElement('summary');s.appendChild(a);d.appendChild(s);el.appendChild(d);tree(node[k],p,d)}else el.appendChild(a)})}
const all=document.createElement('a');all.textContent='All resources';all.className='on';all.onclick=e=>{e.preventDefault();folder=null;document.querySelectorAll('nav .on').forEach(x=>x.classList.remove('on'));all.classList.add('on');render()};
$('tree').appendChild(all);tree(root,[],$('tree'));
function esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function render(){
 const terms=$('q').value.toLowerCase().split(/\s+/).filter(Boolean),c=$('cat').value,y=$('typ').value,s=$('spc').value,src=$('src').value;
 const res=DATA.filter(r=>(!c||r.c===c)&&(!y||r.y===y)&&(!s||r.sp===s)&&(!src||r.s===src)&&(!folder||(r.p.join('\u0000')+'\u0000').startsWith(folder+'\u0000'))&&
   (!terms.length||terms.every(t=>(r.t+' '+r.u+' '+r.p.join(' ')).toLowerCase().includes(t))));
 const L=$('list');L.innerHTML=`<p class="meta">${res.length.toLocaleString()} results</p>`+res.slice(0,shown).map(r=>`<div class="r"><a class="t" href="${esc(r.u)}" target="_blank" rel="noopener noreferrer">${esc(r.t)}</a>
 <div class="meta"><span>${esc(r.d)}</span><span class="chip">${esc(r.y.replace('_',' '))}</span><span class="chip">${esc(r.c)}</span><span>${esc(r.p.join(' › '))}</span>${r.v?`<span>${r.v}</span>`:''}${r.f.length>1?`<span title="${esc(r.f.join('\n'))}">· in ${r.f.length} places</span>`:''}</div></div>`).join('');
 if(res.length>shown){const b=document.createElement('button');b.id='more';b.textContent=`Show more (${res.length-shown} left)`;b.onclick=()=>{shown+=500;render()};L.appendChild(b)}
}
['q','cat','typ','spc','src'].forEach(id=>$(id).addEventListener('input',()=>{shown=200;render()}));
render();
</script></body></html>
"""
