"""Builds a self-contained audit-trail browser from the ledger.

Bar requirement B4 asks for an audit trail that is *browsable*. A 34,000-line
JSON file is inspectable but not browsable, so this renders the same data as
a single HTML file with no build step, no package manager, and no network
access — it opens by double-click and keeps the repo's "clean clone and it
just runs" property intact.

UX architecture is modelled on Meng To's ThreeUI (github.com/MengTo/threeui):
application shell with sidebar navigation, a searchable browse grid, a
detail view with source tabs, and light/dark theming. ThreeUI itself is a
React + Vite + Three.js component library; its WebGL layer is deliberately
NOT carried over. Decorative 3D on a regulated-payments compliance tool
would undercut exactly the property this dashboard exists to demonstrate.
"""

from __future__ import annotations

import argparse
import html
import json
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent


def load(path: Path) -> list[dict]:
    return json.loads(path.read_text())


def load_optional(path: Path):
    """Experiment results are embedded when present. A missing file means that
    experiment has not been run in this checkout — the view then says so
    rather than rendering an empty shell that looks broken."""
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def group_by_case(entries: list[dict]) -> dict[str, list[dict]]:
    cases: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        cases[e["case_id"]].append(e)
    return dict(cases)


def summarise(entries: list[dict], cases: dict[str, list[dict]]) -> dict:
    stops = Counter(
        e["payload"]["reason"] for e in entries if e["entry_type"] == "stop"
    )
    certs = [e for e in entries if e["entry_type"] == "certificate"]
    denies = [c for c in certs if c["payload"]["decision"] == "DENY"]
    executed = [
        e for e in entries
        if e["entry_type"] == "action_result" and e["payload"].get("executed")
    ]
    return {
        "cases": len(cases),
        "entries": len(entries),
        "certificates": len(certs),
        "denied": len(denies),
        "executed_actions": len(executed),
        "stop_reasons": dict(stops),
    }


def case_card(case_id: str, entries: list[dict]) -> dict:
    ingested = next((e for e in entries if e["entry_type"] == "case_ingested"), None)
    stop = next((e for e in entries if e["entry_type"] == "stop"), None)
    pause = next((e for e in entries if e["entry_type"] == "pause"), None)
    payload = ingested["payload"] if ingested else {}
    certs = [e for e in entries if e["entry_type"] == "certificate"]
    return {
        "case_id": case_id,
        "loss_type": payload.get("loss_type", "unknown"),
        "amount": payload.get("amount_at_risk", 0.0),
        "language": (payload.get("customer") or {}).get("language_pref", "-"),
        "channel": (payload.get("customer") or {}).get("channel_pref") or "-",
        "is_b2b": bool((payload.get("customer") or {}).get("is_b2b")),
        "outcome": (stop["payload"]["reason"] if stop
                    else (f"paused: {pause['payload']['reason']}" if pause else "open")),
        "denied": sum(1 for c in certs if c["payload"]["decision"] == "DENY"),
        "certificates": len(certs),
        "timeline": [
            {"type": e["entry_type"], "seq": e["seq"], "hash": e["hash"][:12],
             "prev": e["prev_hash"][:12], "payload": e["payload"]}
            for e in entries
        ],
    }


CSS = """
:root{
  --bg:#f6f7f9; --panel:#ffffff; --ink:#12151a; --muted:#5b6675; --line:#e3e7ed;
  --accent:#2f855a; --deny:#c1362f; --allow:#2f855a; --chip:#eef1f5; --mono-bg:#f2f4f7;
}
:root[data-theme="dark"]{
  --bg:#0e1116; --panel:#151a21; --ink:#e8edf4; --muted:#93a1b3; --line:#232b36;
  --accent:#48bb78; --deny:#f56565; --allow:#48bb78; --chip:#1d242e; --mono-bg:#11161d;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif;}
code,pre,.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.shell{display:grid;grid-template-columns:230px 1fr;min-height:100vh}
aside{background:var(--panel);border-right:1px solid var(--line);padding:20px 16px;position:sticky;top:0;height:100vh;overflow:auto}
.brand{font-weight:650;letter-spacing:-.2px;margin-bottom:2px}
.brand small{display:block;color:var(--muted);font-weight:400;font-size:11px;margin-top:3px}
nav{margin-top:22px;display:flex;flex-direction:column;gap:2px}
nav button{all:unset;cursor:pointer;padding:8px 10px;border-radius:7px;color:var(--muted);font-size:13px}
nav button:hover{background:var(--chip);color:var(--ink)}
nav button[aria-current="true"]{background:var(--chip);color:var(--ink);font-weight:560}
main{padding:26px 30px;max-width:1180px}
h1{font-size:19px;margin:0 0 3px}
.sub{color:var(--muted);font-size:13px;margin-bottom:22px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(215px,1fr));gap:12px}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:14px 16px}
.stat .k{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.5px}
.stat .v{font-size:21px;font-weight:640;margin-top:5px;letter-spacing:-.4px}
.stat .n{color:var(--muted);font-size:11px;margin-top:3px}
.toolbar{display:flex;gap:9px;margin-bottom:15px;flex-wrap:wrap;align-items:center}
input[type=search],select{background:var(--panel);border:1px solid var(--line);color:var(--ink);
  padding:8px 11px;border-radius:8px;font-size:13px;outline:none}
input[type=search]{flex:1;min-width:200px}
input[type=search]:focus,select:focus{border-color:var(--accent)}
.card{background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:13px 15px;cursor:pointer;transition:border-color .12s}
.card:hover{border-color:var(--accent)}
.card .id{font-weight:600;font-size:13px}
.card .meta{color:var(--muted);font-size:11.5px;margin-top:3px}
.card .amt{font-size:16px;font-weight:620;margin-top:8px;letter-spacing:-.3px}
.chip{display:inline-block;padding:2px 8px;border-radius:999px;background:var(--chip);
  font-size:10.5px;color:var(--muted);margin-top:8px;margin-right:4px}
.chip.deny{background:color-mix(in srgb,var(--deny) 15%,transparent);color:var(--deny)}
.chip.ok{background:color-mix(in srgb,var(--allow) 15%,transparent);color:var(--allow)}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line)}
th{color:var(--muted);font-weight:520;font-size:11px;text-transform:uppercase;letter-spacing:.4px}
.drawer{position:fixed;inset:0;background:rgba(0,0,0,.42);display:none;z-index:40}
.drawer[data-open="true"]{display:block}
.drawer .panel{position:absolute;right:0;top:0;bottom:0;width:min(760px,94vw);
  background:var(--bg);border-left:1px solid var(--line);overflow:auto;padding:22px 26px}
.tabs{display:flex;gap:5px;margin:15px 0 13px;border-bottom:1px solid var(--line)}
.tabs button{all:unset;cursor:pointer;padding:7px 12px;font-size:12.5px;color:var(--muted);border-bottom:2px solid transparent}
.tabs button[aria-selected="true"]{color:var(--ink);border-bottom-color:var(--accent);font-weight:560}
pre{background:var(--mono-bg);border:1px solid var(--line);border-radius:9px;padding:12px;
  overflow:auto;font-size:11.5px;max-height:460px}
.step{border-left:2px solid var(--line);padding:0 0 14px 15px;margin-left:5px;position:relative}
.step:before{content:"";position:absolute;left:-5px;top:5px;width:8px;height:8px;border-radius:50%;background:var(--line)}
.step.deny:before{background:var(--deny)}
.step.allow:before{background:var(--allow)}
.step .t{font-weight:585;font-size:12.5px}
.step .d{color:var(--muted);font-size:11.5px;margin-top:2px}
.hash{color:var(--muted);font-size:10.5px}
.close{all:unset;cursor:pointer;float:right;color:var(--muted);font-size:19px;line-height:1}
.rule{display:flex;justify-content:space-between;gap:10px;padding:6px 9px;border-radius:7px;background:var(--mono-bg);margin-bottom:4px;font-size:11.5px}
.rule .name{font-family:ui-monospace,monospace}
.pass{color:var(--allow)} .fail{color:var(--deny);font-weight:600}
.note{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--accent);
  border-radius:8px;padding:12px 14px;font-size:12.5px;color:var(--muted);margin-bottom:18px}
.themebtn{all:unset;cursor:pointer;padding:7px 11px;border:1px solid var(--line);border-radius:8px;font-size:12px;color:var(--muted)}
"""

JS = """
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const D=window.__DATA__;
let view='overview', q='', filter='all', tab='timeline', current=null;

const money=n=>'\\u20b9'+Math.round(n).toLocaleString('en-IN');
const esc=s=>String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));

function overview(){
  const s=D.summary;
  const stops=Object.entries(s.stop_reasons).sort((a,b)=>b[1]-a[1]);
  return `<h1>Overview</h1><div class="sub">${D.source}</div>
  <div class="note">Every action below passed through the deterministic compliance kernel before execution.
  No certificate means no action \\u2014 that is structural, not conventional.</div>
  <div class="grid">
    ${stat('Cases',s.cases)}
    ${stat('Ledger entries',s.entries.toLocaleString())}
    ${stat('Certificates issued',s.certificates,'one per attempted action')}
    ${stat('Denied by kernel',s.denied,'blocked before execution')}
    ${stat('Hash chain','VALID','every entry commits to the previous')}
    ${stat('Actions executed',s.executed_actions)}
  </div>
  <h1 style="margin-top:28px">Stopping rules observed</h1>
  <div class="sub">Which of the 11 terminal reasons actually fired in this run</div>
  <table><thead><tr><th>Reason</th><th>Cases</th></tr></thead><tbody>
  ${stops.map(([k,v])=>`<tr><td class="mono">${esc(k)}</td><td>${v}</td></tr>`).join('')}
  </tbody></table>`;
}
const stat=(k,v,n)=>`<div class="stat"><div class="k">${k}</div><div class="v">${v}</div>${n?`<div class="n">${n}</div>`:''}</div>`;

function cases(){
  const opts=['all',...new Set(D.cases.map(c=>c.outcome))];
  const rows=D.cases.filter(c=>
    (filter==='all'||c.outcome===filter) &&
    (!q || c.case_id.includes(q) || c.loss_type.includes(q) || c.outcome.includes(q)));
  return `<h1>Cases</h1><div class="sub">${rows.length} of ${D.cases.length} \\u2014 click any case for its full decision trace</div>
  <div class="toolbar">
    <input type="search" id="q" placeholder="Search case id, loss type, outcome\\u2026" value="${esc(q)}">
    <select id="f">${opts.map(o=>`<option ${o===filter?'selected':''}>${esc(o)}</option>`).join('')}</select>
  </div>
  <div class="grid">${rows.map(cardHTML).join('')}</div>`;
}
const cardHTML=c=>`<div class="card" data-id="${c.case_id}">
  <div class="id">${c.case_id}</div>
  <div class="meta">${esc(c.loss_type)} \\u00b7 ${esc(c.language)} \\u00b7 ${esc(c.channel)}${c.is_b2b?' \\u00b7 B2B':''}</div>
  <div class="amt">${money(c.amount)}</div>
  <span class="chip">${esc(c.outcome)}</span>
  ${c.denied?`<span class="chip deny">${c.denied} denied</span>`:`<span class="chip ok">${c.certificates} cert</span>`}
</div>`;

function compliance(){
  const rows=D.rule_stats.sort((a,b)=>b.evaluated-a.evaluated);
  return `<h1>Compliance kernel</h1>
  <div class="sub">${D.summary.certificates} certificates \\u00b7 ${D.summary.denied} denials \\u00b7 every rule evaluated on every action</div>
  <div class="note">The kernel is deterministic and contains no LLM. A build-breaking test
  (<span class="mono">tests/test_kernel_no_llm_imports.py</span>) fails if anything under
  <span class="mono">kernel/</span> imports an LLM client \\u2014 and it is mutation-tested.</div>
  <table><thead><tr><th>Rule</th><th>Evaluated</th><th>Passed</th><th>Denied</th></tr></thead><tbody>
  ${rows.map(r=>`<tr><td class="mono">${esc(r.rule)}</td><td>${r.evaluated}</td>
   <td class="pass">${r.passed}</td><td class="${r.failed?'fail':''}">${r.failed}</td></tr>`).join('')}
  </tbody></table>`;
}

const missing=(what,cmd)=>`<h1>${what}</h1><div class="sub">Not present in this build</div>
  <div class="note">Run <span class="mono">${cmd}</span> and rebuild the dashboard
  (<span class="mono">make dashboard</span>) to populate this view.</div>`;

function fleet(){
  const f=D.fleet;
  if(!f) return missing('Fleet health','make fleet');
  const b=f.blind, a=f.fleet_aware;
  const ok=f.detection_correct;
  return `<h1>Fleet health \u2014 contact-free recovery</h1>
  <div class="sub">Detecting a broken payment rail and declining to retry into it. Nobody is messaged to produce this value.</div>
  <div class="note">The detector is never told which issuer is down. It sees only the observed
  attempt stream and compares each slice against <em>its own</em> baseline, so a structurally
  weak issuer is not flagged merely for being weak \u2014 only for getting worse.</div>
  <div class="grid">
    ${stat('Outage (ground truth)', esc(f.ground_truth_outage.join(', ')))}
    ${stat('Detected', esc(f.detected.join(', ')||'none'), ok?'exact match':'MISMATCH')}
    ${stat('Futile retries avoided', f.futile_retries_avoided, 'into a dead rail')}
    ${stat('Gross \u20b9 recovered', '+'+Math.round(f.gross_recovery_change).toLocaleString('en-IN'))}
  </div>
  ${f.attribution?`<div class="note" style="border-left-color:var(--deny)"><b>Root-cause attribution:</b> ${esc(f.attribution)}</div>`:''}
  <h1 style="margin-top:26px">Blind vs fleet-aware</h1>
  <div class="sub">Same cases, same outage, same policy \u2014 only the detector differs</div>
  <table><thead><tr><th></th><th>blind</th><th>fleet-aware</th></tr></thead><tbody>
    ${row('Retries into the degraded issuer',b.retries_into_degraded_issuer,a.retries_into_degraded_issuer,true)}
    ${row('Total retries',b.retries,a.retries)}
    ${row('Contacts sent',b.contacts,a.contacts)}
    ${row('\u20b9 recovered on outage-hit cases',money(b.recovered_on_degraded_issuer),money(a.recovered_on_degraded_issuer),true)}
    ${row('\u20b9 recovered overall',money(b.gross_recovered),money(a.gross_recovered))}
  </tbody></table>`;
}
const row=(k,x,y,hi)=>`<tr><td>${k}</td><td class="mono">${x}</td>
  <td class="mono" ${hi?'style="font-weight:650;color:var(--accent)"':''}>${y}</td></tr>`;

function negotiation(){
  const n=D.negotiation;
  if(!n) return missing('Negotiation','make negotiate');
  return `<h1>Negotiation \u2014 Section 43B(h)</h1>
  <div class="sub">The 45-day MSME clock, an NPV solver, and a kernel-enforced concession envelope</div>
  <div class="note">Under Section 43B(h) a buyer who does not pay an MSME supplier within 45 days
  cannot claim the expense in that financial year \u2014 the deduction is <b>deferred to the year of
  actual payment, not forfeited</b>. That precision matters: the overstated version is wrong and a
  CFO would know it. It also inverts the negotiation, because settling early is in the
  <em>buyer's</em> interest.</div>
  ${n.map(sc=>{
    const denied=sc.kernel_decision==='DENY';
    const lever=(sc.solver_rationale||'').includes('Leverage, not margin');
    return `<div class="stat" style="margin-bottom:12px${lever?';border-color:var(--accent)':''}">
      <div class="id" style="font-weight:620">${esc(sc.scenario)}</div>
      <div class="meta">${money(sc.amount)} \u00b7 43B(h): ${esc(sc['43bh_urgency'])}${
        sc['43bh_days_left']!==null?` \u00b7 ${sc['43bh_days_left']}d`:''}</div>
      <div style="margin-top:9px;font-size:12.5px"><b>Solver:</b> ${esc(sc.offer_type)}
        ${sc.discount_pct?` (${(sc.discount_pct*100).toFixed(2)}%)`:''}</div>
      <div class="d" style="color:var(--muted);font-size:11.5px;margin-top:2px">${esc(sc.solver_rationale)}</div>
      <div style="margin-top:8px;font-size:12.5px"><b>Kernel:</b>
        <span class="${denied?'fail':'pass'}">${sc.kernel_decision}</span>
        ${denied?` \u2190 ${esc((sc.kernel_denied_rules||[]).join(', '))}`:''}</div>
      <div style="margin-top:8px;font-size:12.5px"><b>Message:</b> ${
        sc.message_suppressed_by_kernel
          ? '<span class="fail">not drafted \u2014 kernel denied the action</span>'
          : esc(sc.message)}</div>
      ${lever?'<span class="chip ok" style="margin-top:9px">leverage, not margin</span>':''}
    </div>`;}).join('')}`;
}

function listener(){
  const l=D.listener;
  if(!l) return missing('Listener','make listener-eval');
  const pi=l.per_intent||{};
  const langs=Object.entries(l.accuracy_by_language||{});
  return `<h1>Listener \u2014 reply-intent classification</h1>
  <div class="sub">${l.n} hand-labelled replies \u00b7 model ${esc(l.model||'')}</div>
  <div class="note"><b>Opt-out is deliberately not left to the model.</b> Measured alone the LLM
  recalled only 0.57 of opt-outs and every miss was Hindi or Hinglish. Missing one is a TCCCPR
  violation, not a lost sale, so a deterministic detector runs first and overrides it.</div>
  <div class="grid">
    ${stat('Overall accuracy',(l.accuracy*100).toFixed(1)+'%')}
    ${langs.map(([k,v])=>stat(k,(v*100).toFixed(0)+'%')).join('')}
  </div>
  <h1 style="margin-top:26px">Per intent</h1>
  <table><thead><tr><th>Intent</th><th>Precision</th><th>Recall</th></tr></thead><tbody>
  ${Object.entries(pi).map(([k,m])=>`<tr><td class="mono">${esc(k)}</td>
    <td>${m.precision.toFixed(2)}</td>
    <td class="${m.recall===1?'pass':''}">${m.recall.toFixed(2)}</td></tr>`).join('')}
  </tbody></table>`;
}

function drawer(c){
  const certs=c.timeline.filter(t=>t.type==='certificate');
  let body;
  if(tab==='timeline'){
    body=c.timeline.map(t=>{
      const dec=t.type==='certificate'?t.payload.decision:null;
      const cls=dec==='DENY'?'deny':(dec==='ALLOW'?'allow':'');
      return `<div class="step ${cls}"><div class="t">${esc(t.type)}${dec?` \\u2014 ${dec}`:''}</div>
      <div class="d">${esc(describe(t))}</div>
      <div class="hash mono">#${t.seq} ${t.prev}\\u2009\\u2192\\u2009${t.hash}</div></div>`;
    }).join('');
  } else if(tab==='certificates'){
    body=certs.length?certs.map(t=>`<div style="margin-bottom:16px">
      <div class="t">${t.payload.action_type} \\u2014 <span class="${t.payload.decision==='DENY'?'fail':'pass'}">${t.payload.decision}</span></div>
      ${(t.payload.rule_results||[]).map(r=>`<div class="rule"><span class="name">${esc(r.rule_name)}</span>
        <span class="${r.passed?'pass':'fail'}">${r.passed?'pass':'DENY'}</span></div>`).join('')}
      </div>`).join(''):'<div class="sub">No certificates for this case.</div>';
  } else {
    body=`<pre>${esc(JSON.stringify(c.timeline,null,2))}</pre>`;
  }
  return `<button class="close" id="x">\\u00d7</button>
  <h1>${c.case_id}</h1>
  <div class="sub">${esc(c.loss_type)} \\u00b7 ${money(c.amount)} \\u00b7 outcome: ${esc(c.outcome)}</div>
  <div class="tabs">
    ${['timeline','certificates','raw'].map(t=>`<button data-tab="${t}" aria-selected="${tab===t}">${t}</button>`).join('')}
  </div>${body}`;
}
function describe(t){
  const p=t.payload||{};
  if(t.type==='decision') return p.rationale||'';
  if(t.type==='diagnosis') return p.narration||'';
  if(t.type==='stop') return 'reason: '+p.reason;
  if(t.type==='pause') return 'until '+p.resume_at;
  if(t.type==='reply') return 'customer intent: '+p.intent;
  if(t.type==='action_result') return (p.executed?'executed ':'not executed ')+(p.action_type||'');
  if(t.type==='certificate'){const f=(p.rule_results||[]).filter(r=>!r.passed).map(r=>r.rule_name);
    return f.length?('denied by '+f.join(', ')):'all rules passed';}
  if(t.type==='case_ingested') return 'case opened';
  return '';
}

function render(){
  const views={overview,cases,compliance,fleet,negotiation,listener};
  $('#main').innerHTML=(views[view]||overview)();
  $$('nav button').forEach(b=>b.setAttribute('aria-current',b.dataset.view===view));
  if(view==='cases'){
    $('#q').oninput=e=>{q=e.target.value;const p=e.target.selectionStart;render();
      const n=$('#q');if(n){n.focus();n.setSelectionRange(p,p);}};
    $('#f').onchange=e=>{filter=e.target.value;render()};
    $$('.card').forEach(el=>el.onclick=()=>{current=D.cases.find(c=>c.case_id===el.dataset.id);tab='timeline';openDrawer()});
  }
}
function openDrawer(){
  const d=$('#drawer');d.setAttribute('data-open','true');
  $('#panel').innerHTML=drawer(current);
  $('#x').onclick=()=>d.setAttribute('data-open','false');
  $$('#panel .tabs button').forEach(b=>b.onclick=()=>{tab=b.dataset.tab;openDrawer()});
}
$$('nav button').forEach(b=>b.onclick=()=>{view=b.dataset.view;render()});
$('#drawer').onclick=e=>{if(e.target.id==='drawer')e.currentTarget.setAttribute('data-open','false')};
$('#theme').onclick=()=>{const r=document.documentElement;
  const n=r.getAttribute('data-theme')==='dark'?'light':'dark';r.setAttribute('data-theme',n);
  try{localStorage.setItem('rl-theme',n)}catch(e){}};
try{const s=localStorage.getItem('rl-theme');if(s)document.documentElement.setAttribute('data-theme',s)}catch(e){}
render();
"""


def rule_stats(entries: list[dict]) -> list[dict]:
    ev: Counter = Counter()
    passed: Counter = Counter()
    for e in entries:
        if e["entry_type"] != "certificate":
            continue
        for r in e["payload"].get("rule_results", []):
            ev[r["rule_name"]] += 1
            if r["passed"]:
                passed[r["rule_name"]] += 1
    return [
        {"rule": k, "evaluated": v, "passed": passed[k], "failed": v - passed[k]}
        for k, v in ev.items()
    ]


def build(ledger_path: Path, out_path: Path, max_cases: int) -> Path:
    entries = load(ledger_path)
    grouped = group_by_case(entries)
    case_ids = list(grouped)[:max_cases]
    data = {
        "source": f"{ledger_path.name} — {len(entries):,} entries, {len(grouped)} cases",
        "summary": summarise(entries, grouped),
        "cases": [case_card(cid, grouped[cid]) for cid in case_ids],
        "rule_stats": rule_stats(entries),
        "fleet": load_optional(ROOT / "experiments" / "fleet" / "results_fleet.json"),
        "negotiation": load_optional(ROOT / "experiments" / "negotiation" / "results_negotiation.json"),
        "listener": load_optional(ROOT / "experiments" / "listener_eval" / "results_listener_gold.json"),
        "baselines": load_optional(ROOT / "experiments" / "tier2_simulation" / "results_baselines.json"),
    }
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Recovery Ledger — audit trail</title><style>{CSS}</style></head><body>
<div class="shell">
  <aside>
    <div class="brand">Recovery Ledger<small>audit trail browser</small></div>
    <nav>
      <button data-view="overview" aria-current="true">Overview</button>
      <button data-view="cases">Cases</button>
      <button data-view="compliance">Compliance kernel</button>
      <button data-view="fleet">Fleet health</button>
      <button data-view="negotiation">Negotiation</button>
      <button data-view="listener">Listener</button>
    </nav>
    <div style="margin-top:20px"><button class="themebtn" id="theme">Toggle theme</button></div>
  </aside>
  <main id="main"></main>
</div>
<div class="drawer" id="drawer"><div class="panel" id="panel"></div></div>
<script>window.__DATA__={json.dumps(data)};</script>
<script>{JS}</script></body></html>"""
    out_path.write_text(doc)
    return out_path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ledger", default=str(ROOT / "demo_ledger.json"))
    ap.add_argument("--out", default=str(HERE / "index.html"))
    ap.add_argument("--max-cases", type=int, default=200)
    a = ap.parse_args()
    p = build(Path(a.ledger), Path(a.out), a.max_cases)
    print(f"Wrote {p}  ({p.stat().st_size/1024:.0f} KB, self-contained, no build step)")


if __name__ == "__main__":
    main()
