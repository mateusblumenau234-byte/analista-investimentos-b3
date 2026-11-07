#!/usr/bin/env python3
"""Gera o relatório profissional em HTML (uma página, gráficos SVG embutidos, tema claro/escuro).

Uso: python relatorio_html.py relatorios/<TICKER>_<data>
Lê: dados.json, nota.json, parecer_*.json, precos.csv, indicadores_banco.csv (ou indicadores.csv), RELATORIO.md
Grava: relatorio.html (pronto para publicar como Artifact ou abrir no navegador e imprimir em PDF)
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

import markdown
import pandas as pd

NOMES = {"valor": "Fundamentalista de Valor", "macro": "Estrategista Macro Global", "risco": "Gestor de Risco Cético"}
ESCOLA = {"valor": "Graham · Buffett · Damodaran", "macro": "Dalio · Soros · Shiller", "risco": "Taleb · Marks · contabilidade forense"}
DIM = {"negocio": "Negócio", "saude_financeira": "Saúde financeira", "gestao": "Gestão e governança",
       "valuation": "Valuation", "risco_mercado": "Risco de mercado", "macro": "Ambiente macro"}


def e(x) -> str:
    return html.escape(str(x))


def faixa(n: float | None) -> str:
    if n is None:
        return "na"
    return "bad" if n < 3 else "weak" if n < 5 else "mid" if n < 7 else "good"


def num(x, casas=1, pct=False):
    if x is None:
        return "n/d"
    s = f"{x * 100:.{casas}f}%" if pct else f"{x:,.{casas}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def gauge(n: float) -> str:
    """Semicírculo de 0 a 10 com marcador; cores semânticas por faixa."""
    import math
    cx, cy, r = 110, 104, 86
    def pt(v, rr=r):
        a = math.pi * (1 - v / 10)
        return cx + rr * math.cos(a), cy - rr * math.sin(a)
    arcos = []
    for a, b, cls in ((0, 3, "bad"), (3, 5, "weak"), (5, 7, "mid"), (7, 10, "good")):
        x1, y1 = pt(a); x2, y2 = pt(b)
        arcos.append(f'<path d="M{x1:.1f},{y1:.1f} A{r},{r} 0 0 1 {x2:.1f},{y2:.1f}" class="arc {cls}"/>')
    mx, my = pt(n, r - 2)
    ticks = "".join(f'<text x="{pt(v, r + 14)[0]:.1f}" y="{pt(v, r + 14)[1] + 4:.1f}" class="tick">{v}</text>' for v in (0, 5, 10))
    return (f'<svg viewBox="0 0 220 128" class="gauge" role="img" aria-label="Nota {num(n)} de 10">{"".join(arcos)}{ticks}'
            f'<line x1="{cx}" y1="{cy}" x2="{mx:.1f}" y2="{my:.1f}" class="needle"/><circle cx="{cx}" cy="{cy}" r="5" class="hub"/></svg>')


def grafico_precos(p: pd.DataFrame, tk: str) -> str:
    """Base 100 do ativo vs. BOVA11/^BVSP."""
    bench = next((c for c in ("^BVSP", "BOVA11") if c in p.columns), None)
    cols = [c for c in (tk, bench) if c and c in p.columns]
    d = p[cols].dropna()
    if d.empty:
        return ""
    d = d / d.iloc[0] * 100
    d = d.iloc[:: max(1, len(d) // 260)]
    W, H, L, R, T, B = 640, 240, 44, 12, 14, 26
    lo, hi = float(d.min().min()), float(d.max().max())
    lo, hi = lo - (hi - lo) * 0.05, hi + (hi - lo) * 0.05
    X = lambda i: L + (W - L - R) * i / (len(d) - 1)  # noqa: E731
    Y = lambda v: T + (H - T - B) * (1 - (v - lo) / (hi - lo))  # noqa: E731
    grade = []
    passo = 25 if hi - lo > 80 else 10
    v = (int(lo // passo) + 1) * passo
    while v < hi:
        grade.append(f'<line x1="{L}" x2="{W - R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" class="grid"/>'
                     f'<text x="{L - 6}" y="{Y(v) + 4:.1f}" class="axis" text-anchor="end">{v}</text>')
        v += passo
    anos = []
    ultimo = None
    for i, ts in enumerate(d.index):
        if ts.year != ultimo and i > 0:
            anos.append(f'<text x="{X(i):.1f}" y="{H - 8}" class="axis" text-anchor="middle">{ts.year}</text>')
        ultimo = ts.year
    linhas = []
    for c, cls in zip(cols, ("s1", "s2")):
        pts = " ".join(f"{X(i):.1f},{Y(val):.1f}" for i, val in enumerate(d[c]))
        linhas.append(f'<polyline points="{pts}" class="line {cls}"/>')
        linhas.append(f'<circle cx="{X(len(d) - 1):.1f}" cy="{Y(d[c].iloc[-1]):.1f}" r="3.5" class="dot {cls}"/>')
    leg = " ".join(f'<span class="key {cls}">{e(c if c != "^BVSP" else "Ibovespa")} {num(d[c].iloc[-1], 0)}</span>'
                   for c, cls in zip(cols, ("s1", "s2")))
    return (f'<figure class="chart"><figcaption>Desempenho com proventos reinvestidos, base 100 em {d.index[0]:%d/%m/%Y} · {leg}</figcaption>'
            f'<div class="scroll"><svg viewBox="0 0 {W} {H}" role="img" aria-label="Preço ajustado base 100">{"".join(grade)}{"".join(anos)}{"".join(linhas)}</svg></div></figure>')


def grafico_roe(ind: pd.DataFrame, ke: float | None, ltm_roe: float | None) -> str:
    if "roe" not in ind.columns:
        return ""
    s = ind["roe"].dropna()
    rotulos = [str(int(a)) for a in s.index]
    vals = list(s.values)
    if ltm_roe is not None:
        rotulos.append("12m"); vals.append(ltm_roe)
    if not vals:
        return ""
    W, H, L, B, T = 640, 220, 44, 26, 16
    top = max(max(vals), ke or 0) * 1.15
    bw = (W - L - 12) / len(vals)
    Y = lambda v: T + (H - T - B) * (1 - v / top)  # noqa: E731
    barras = []
    for i, (r, v) in enumerate(zip(rotulos, vals)):
        x = L + i * bw + bw * 0.18
        cls = "bar hi" if r == "12m" else "bar"
        barras.append(f'<rect x="{x:.1f}" y="{Y(v):.1f}" width="{bw * 0.64:.1f}" height="{H - B - Y(v):.1f}" class="{cls}"/>'
                      f'<text x="{x + bw * 0.32:.1f}" y="{Y(v) - 5:.1f}" class="val" text-anchor="middle">{num(v, 0, True)}</text>'
                      f'<text x="{x + bw * 0.32:.1f}" y="{H - 8}" class="axis" text-anchor="middle">{r}</text>')
    linha = ""
    if ke:
        linha = (f'<line x1="{L}" x2="{W - 12}" y1="{Y(ke):.1f}" y2="{Y(ke):.1f}" class="ke"/>'
                 f'<text x="{W - 14}" y="{Y(ke) - 6:.1f}" class="kelabel" text-anchor="end">Custo de capital {num(ke, 1, True)}</text>')
    return (f'<figure class="chart"><figcaption>ROE contra o custo de capital: criação de valor exige barra acima da linha</figcaption>'
            f'<div class="scroll"><svg viewBox="0 0 {W} {H}" role="img" aria-label="ROE por ano">'
            f'<line x1="{L}" x2="{W - 12}" y1="{Y(0):.1f}" y2="{Y(0):.1f}" class="grid"/>{"".join(barras)}{linha}</svg></div></figure>')


def heatmap(csv: Path, preco: float | None) -> str:
    if not csv.exists():
        return ""
    m = pd.read_csv(csv, index_col=0)
    linhas = ["<tr><th></th>" + "".join(f"<th>{e(c)}</th>" for c in m.columns) + "</tr>"]
    for i, row in m.iterrows():
        cel = []
        for v in row.values:
            cls = "" if preco is None else ("up" if v >= preco * 1.2 else "eq" if v >= preco * 0.9 else "down")
            cel.append(f'<td class="{cls}">{num(v, 2)}</td>')
        linhas.append(f"<th>{e(i)}</th>" + "".join(cel))
    leg = "" if preco is None else (f'<p class="note">Verde: ≥ 20% acima do preço (R$ {num(preco, 2)}) · '
                                    'âmbar: entre −10% e +20% · vermelho: mais de 10% abaixo.</p>')
    return (f'<div class="scroll"><table class="heat"><caption>Valor por ação (R$): custo de capital × ROE sustentável</caption>'
            + "".join(f"<tr>{l}</tr>" if not l.startswith("<tr>") else l for l in linhas) + f"</table></div>{leg}")


def card_analista(p: dict) -> str:
    a = p.get("analista", "?")
    n = p.get("nota")
    tese = "".join(f"<li>{e(t)}</li>" for t in (p.get("tese") or []))
    riscos = "".join(f"<li>{e(t)}</li>" for t in (p.get("riscos") or []))
    gat = "".join(f"<li>{e(t)}</li>" for t in (p.get("gatilhos_para_mudar_de_opiniao") or []))
    return f"""<article class="analyst">
  <header><div><h3>{e(NOMES.get(a, a))}</h3><p class="school">{e(ESCOLA.get(a, ""))}</p></div>
  <div class="score {faixa(n)}"><b>{num(n)}</b><span>/10</span></div></header>
  <p class="verdict">{e(p.get("veredito", ""))}</p>
  <p class="conv">Convicção: <b>{e(p.get("conviccao", "n/d"))}</b></p>
  <details open><summary>Tese</summary><ul>{tese}</ul></details>
  <details><summary>Riscos</summary><ul>{riscos}</ul></details>
  <details><summary>O que mudaria a opinião</summary><ul>{gat}</ul></details>
</article>"""


def painel_global(pareceres: list[dict]) -> str:
    itens = next((p.get("painel_global") for p in pareceres if p.get("painel_global")), None)
    if not itens:
        return ""
    linhas = "".join(
        f"<tr><td>{e(i.get('indicador', ''))}</td><td class='n'>{e(i.get('valor', ''))}</td><td>{e(i.get('data', ''))}</td>"
        f"<td>{e(i.get('leitura', ''))}</td><td><a href=\"{e(i.get('fonte_url', ''))}\" target=\"_blank\" rel=\"noopener\">fonte</a></td></tr>"
        for i in itens)
    return (f'<section><h2>Painel global</h2><p class="lede">Coletado pelo Estrategista Macro com fonte e data de cada número.</p>'
            f'<div class="scroll"><table class="data"><tr><th>Indicador</th><th>Valor</th><th>Data</th><th>Leitura</th><th></th></tr>{linhas}</table></div></section>')


CSS = """
/* Layout: relatório de research em coluna única, ficha de nota no topo, conselho em grade de 3 colunas */
:root{--paper:#f7f8fa;--ink:#16202c;--muted:#5b6878;--rule:#d9dee5;--panel:#ffffff;--accent:#1f4e79;
--good:#1d7a4f;--mid:#b07a12;--weak:#c0561e;--bad:#b3261e;--s2:#8a96a6;
--serif:"Newsreader",Georgia,"Times New Roman",serif;--sans:"Public Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
--mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--paper:#0f141b;--ink:#e6ebf1;--muted:#9aa7b6;--rule:#2a3441;--panel:#161d27;
--accent:#7fb2e5;--good:#4cc38a;--mid:#e0b04a;--weak:#ef8a4f;--bad:#f26d63;--s2:#6f7c8c;color-scheme:dark}}
:root[data-theme="dark"]{--paper:#0f141b;--ink:#e6ebf1;--muted:#9aa7b6;--rule:#2a3441;--panel:#161d27;
--accent:#7fb2e5;--good:#4cc38a;--mid:#e0b04a;--weak:#ef8a4f;--bad:#f26d63;--s2:#6f7c8c;color-scheme:dark}
body{background:var(--paper);color:var(--ink);font:15px/1.6 var(--sans)}
.wrap{max-width:1040px;margin:0 auto;padding-block:28px 64px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));display:grid;grid-template-columns:minmax(0,1fr);gap:36px}
.wrap>*{min-width:0}.final{min-width:0}
h1,h2,h3{font-family:var(--serif);font-weight:600;line-height:1.2;text-wrap:balance;margin:0}
h1{font-size:2.3rem}h2{font-size:1.5rem;padding-bottom:6px;border-bottom:1px solid var(--rule);margin-bottom:14px}h3{font-size:1.12rem}
.eyebrow{font:600 .72rem/1 var(--sans);letter-spacing:.12em;text-transform:uppercase;color:var(--accent)}
.masthead{display:grid;gap:10px}.meta{display:flex;flex-wrap:wrap;gap:6px 22px;color:var(--muted);font-size:.9rem}
.meta b{color:var(--ink);font-family:var(--mono);font-weight:500}
.lede{color:var(--muted);max-width:68ch;margin:0 0 12px}
.scorecard{display:grid;grid-template-columns:minmax(220px,300px) 1fr;gap:28px;background:var(--panel);border:1px solid var(--rule);border-radius:6px;padding:22px}
.final{display:grid;justify-items:center;gap:4px;text-align:center}
.final .big{font:600 3.4rem/1 var(--serif)}.final .big small{font-size:1.1rem;color:var(--muted)}
.final .label{font-weight:700;text-transform:uppercase;letter-spacing:.08em;font-size:.82rem}
.gauge{width:100%;max-width:240px}.arc{fill:none;stroke-width:14}.arc.bad{stroke:var(--bad)}.arc.weak{stroke:var(--weak)}.arc.mid{stroke:var(--mid)}.arc.good{stroke:var(--good)}
.needle{stroke:var(--ink);stroke-width:3;stroke-linecap:round}.hub{fill:var(--ink)}.tick{fill:var(--muted);font:11px var(--mono);text-anchor:middle}
.bad{color:var(--bad)}.weak{color:var(--weak)}.mid{color:var(--mid)}.good{color:var(--good)}
.dims{display:grid;gap:10px;min-width:0}.dim{display:grid;grid-template-columns:150px 1fr 44px;gap:10px;align-items:center;font-size:.9rem}
.bar-bg{height:10px;background:var(--rule);border-radius:5px;overflow:hidden}.bar-fg{height:100%;border-radius:5px;background:currentColor}
.dim .n{font-family:var(--mono);text-align:right}.rule{grid-column:2/4;color:var(--muted);font-size:.78rem;margin-top:-6px}
.splits{display:flex;flex-wrap:wrap;gap:8px 18px;font-size:.86rem;color:var(--muted)}.splits b{font-family:var(--mono);color:var(--ink)}
.flag{display:inline-block;font-size:.78rem;padding:2px 8px;border-radius:999px;border:1px solid currentColor;margin:2px 6px 0 0}
.council{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}
.analyst{background:var(--panel);border:1px solid var(--rule);border-radius:6px;padding:16px;display:grid;gap:8px;align-content:start;min-width:0}
.analyst header{display:flex;justify-content:space-between;gap:12px;align-items:start}
.school{margin:2px 0 0;color:var(--muted);font-size:.8rem}
.score{font-family:var(--mono);text-align:right;white-space:nowrap}.score b{font-size:1.8rem;font-weight:600}.score span{color:var(--muted)}
.verdict{font-family:var(--serif);font-size:1.02rem;margin:0}.conv{margin:0;font-size:.84rem;color:var(--muted)}
details{border-top:1px solid var(--rule);padding-top:6px}summary{cursor:pointer;font-weight:600;font-size:.88rem}
details ul{margin:6px 0 0;padding-left:18px;font-size:.86rem}details li{margin-bottom:4px}
.charts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}
.chart{margin:0;background:var(--panel);border:1px solid var(--rule);border-radius:6px;padding:14px;min-width:0}
.chart figcaption{font-size:.84rem;color:var(--muted);margin-bottom:8px}.chart svg{width:100%;height:auto;min-width:420px}
.grid{stroke:var(--rule);stroke-width:1}.axis{fill:var(--muted);font:11px var(--mono)}.val{fill:var(--ink);font:11px var(--mono)}
.line{fill:none;stroke-width:2}.line.s1,.dot.s1{stroke:var(--accent)}.line.s2,.dot.s2{stroke:var(--s2)}.dot{fill:var(--panel);stroke-width:2}
.key{font-family:var(--mono);margin-left:8px}.key.s1{color:var(--accent)}.key.s2{color:var(--s2)}
.bar{fill:var(--s2)}.bar.hi{fill:var(--bad)}.ke{stroke:var(--accent);stroke-width:2;stroke-dasharray:6 4}.kelabel{fill:var(--accent);font:600 11px var(--sans)}
.scroll{overflow-x:auto}
table{border-collapse:collapse;font-size:.86rem;width:100%}th,td{padding:6px 9px;border-bottom:1px solid var(--rule);text-align:left;vertical-align:top}
th{font-weight:600}td.n,.heat td,.body td{font-family:var(--mono);font-variant-numeric:tabular-nums}
caption{text-align:left;font-size:.84rem;color:var(--muted);padding-bottom:6px}
.heat td{text-align:right}.heat td.up{color:var(--good);font-weight:600}.heat td.eq{color:var(--mid)}.heat td.down{color:var(--bad)}
.note{font-size:.8rem;color:var(--muted);margin:6px 0 0}
a{color:var(--accent)}a:focus-visible,summary:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.body{min-width:0}.body h1{display:none}.body h2{margin-top:30px}.body p,.body li{max-width:72ch}
.body table{margin:10px 0;display:block;overflow-x:auto}.body blockquote{margin:0;padding:8px 14px;border-left:3px solid var(--rule);color:var(--muted)}
.body code{font-family:var(--mono);font-size:.85em}.body pre{overflow-x:auto;background:var(--panel);padding:10px;border-radius:4px}
.disclaimer{font-size:.8rem;color:var(--muted);border-top:1px solid var(--rule);padding-top:12px}
@media (max-width:820px){h1{font-size:1.7rem}.scorecard{grid-template-columns:minmax(0,1fr);padding:16px}.meta{gap:4px 14px}.council,.charts{grid-template-columns:minmax(0,1fr)}.dim{grid-template-columns:96px minmax(0,1fr) 36px}.rule{grid-column:1/4;margin-top:0}}
@media print{.wrap{max-width:none}details{display:block}details>*{display:block}.analyst,.chart,.scorecard{break-inside:avoid}}
"""


def main(pasta: Path) -> Path:
    d = json.loads((pasta / "dados.json").read_text(encoding="utf-8"))
    nota = json.loads((pasta / "nota.json").read_text(encoding="utf-8")) if (pasta / "nota.json").exists() else {}
    pareceres = [json.loads(f.read_text(encoding="utf-8")) for f in sorted(pasta.glob("parecer_*.json"))]
    ordem = {"valor": 0, "macro": 1, "risco": 2}
    pareceres.sort(key=lambda p: ordem.get(p.get("analista"), 9))
    emp = d.get("empresa") or {}
    tk = emp.get("ticker", pasta.name.split("_")[0])
    cot = d.get("cotacao") or {}
    ke = ((d.get("custo_capital") or {}).get("ke") or {}).get("ke_base")
    ltm = d.get("ltm") or {}
    ltm_roe = (ltm.get("lucro_controladores") / ltm.get("pl_controlador")) if ltm.get("pl_controlador") else None
    nf = nota.get("nota_final")

    dims = "".join(
        f'<div class="dim {faixa(v["nota"])}"><span style="color:var(--ink)">{e(DIM.get(k, k))}</span>'
        f'<div class="bar-bg"><div class="bar-fg" style="width:{v["nota"] * 10:.0f}%"></div></div><span class="n">{num(v["nota"])}</span>'
        f'<span class="rule">{e(v["regra"])}{" · peso " + str(int(v["peso"] * 100)) + "%" if v.get("peso") else ""}</span></div>'
        for k, v in (nota.get("dimensoes") or {}).items())
    travas = "".join(f'<span class="flag bad">{e(t)}</span>' for t in nota.get("travas", []))
    consenso = nota.get("consenso", "n/d")
    scorecard = f"""<section class="scorecard" aria-label="Nota">
  <div class="final">{gauge(nf) if nf is not None else ""}
    <div class="big {faixa(nf)}">{num(nf)}<small> /10</small></div>
    <div class="label {faixa(nf)}">{e(nota.get("leitura", "sem nota"))}</div>
  </div>
  <div class="dims"><h3>Como a nota foi formada</h3>
    <div class="splits"><span>Quantitativa (regras) <b>{num(nota.get("nota_quant"))}</b></span>
    <span>Conselho de analistas <b>{num(nota.get("nota_conselho"))}</b></span>
    <span>Divergência (desvio) <b>{num(nota.get("desvio_analistas"), 2)}</b></span>
    <span>Consenso <b>{e(consenso)}</b></span></div>
    {dims}
    <div>{travas}</div>
    <p class="note">Nota final = 50% quantitativa + 50% conselho, sujeita a travas. Ela nunca substitui a leitura das dimensões.</p>
  </div>
</section>"""

    precos = pasta / "precos.csv"
    g1 = grafico_precos(pd.read_csv(precos, index_col=0, parse_dates=True), tk) if precos.exists() else ""
    indf = next((pasta / f for f in ("indicadores_banco.csv", "indicadores.csv") if (pasta / f).exists()), None)
    g2 = grafico_roe(pd.read_csv(indf, index_col=0), ke, ltm_roe) if indf else ""
    corpo = ""
    if (pasta / "RELATORIO.md").exists():
        corpo = markdown.markdown((pasta / "RELATORIO.md").read_text(encoding="utf-8"), extensions=["tables", "fenced_code"])
        corpo = corpo.replace("<a href=", '<a target="_blank" rel="noopener" href=')
    data_ref = (d.get("parametros") or {}).get("data") or pasta.name.split("_")[-1]
    out = f"""<title>{e(tk)} · Research</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Newsreader:opsz,wght@6..72,500;6..72,600&family=Public+Sans:wght@400;600;700&display=swap">
<style>{CSS}</style>
<div class="wrap">
<header class="masthead"><span class="eyebrow">Research de ações · B3</span>
  <h1>{e(emp.get("nome") or tk)} <span style="color:var(--muted);font-weight:500">({e(tk)})</span></h1>
  <div class="meta"><span>Preço <b>R$ {num(cot.get("preco"), 2)}</b> ({e(cot.get("horario", ""))})</span>
  <span>Custo de capital <b>{num(ke, 1, True) if ke else "n/d"}</b></span>
  <span>ROE 12m <b>{num(ltm_roe, 1, True) if ltm_roe is not None else "n/d"}</b></span>
  <span>Data de referência <b>{e(data_ref)}</b></span></div>
</header>
{scorecard}
<section><h2>Conselho de analistas independentes</h2>
<p class="lede">Três analistas trabalharam em paralelo sobre a mesma base de dados, sem ver as conclusões uns dos outros.</p>
<div class="council">{"".join(card_analista(p) for p in pareceres) or "<p>Pareceres ainda não disponíveis.</p>"}</div></section>
{painel_global(pareceres)}
<section><h2>Gráficos</h2><div class="charts">{g1}{g2}</div>
{heatmap(pasta / "sensibilidade_ke_roe.csv", cot.get("preco"))}</section>
<section class="body"><h2>Relatório completo</h2>{corpo}</section>
<p class="disclaimer">Material educacional e de pesquisa. Não constitui recomendação individual de investimento (Resolução CVM 20/2021). Fontes primárias: CVM, B3, Banco Central, Tesouro Transparente, Damodaran; referências conferidas na Crossref.</p>
</div>"""
    destino = pasta / "relatorio.html"
    destino.write_text(out, encoding="utf-8")
    return destino


if __name__ == "__main__":
    print(main(Path(sys.argv[1])))
