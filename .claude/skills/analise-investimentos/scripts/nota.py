"""Nota de 0 a 10: quantitativa (regras transparentes) + conselho de 3 analistas.

Princípio da metodologia: a nota final NUNCA aparece sozinha. Junto com ela vêm as notas
das dimensões, as travas acionadas e a divergência entre os analistas.

Composição:
  nota_quant      = média ponderada das dimensões calculadas por regras (abaixo)
  nota_conselho   = média das 3 notas dos analistas
  nota_final      = 50% quant + 50% conselho, limitada pelas TRAVAS:
     - se alguma dimensão quantitativa ≤ 2  -> final ≤ 5
     - se a margem de segurança base < −30% -> final ≤ 4
     - se o desvio-padrão entre analistas > 2 -> a convicção vira "baixa" (sinal de alta incerteza)
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

PESOS = {"negocio": 0.20, "saude_financeira": 0.25, "gestao": 0.15, "valuation": 0.30, "risco_mercado": 0.10}


def _clip(x, lo=0.0, hi=10.0):
    return float(max(lo, min(hi, x)))


def _lin(x, x0, x1):
    """Mapeia x linearmente: x0 -> 0, x1 -> 10 (com corte)."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    return _clip((x - x0) / (x1 - x0) * 10)


def dimensoes_quant(d: dict) -> dict:
    """Regras explícitas a partir de dados.json. Retorna {dimensão: (nota, justificativa)}."""
    out = {}
    fin = d.get("instituicao_financeira")
    ke = ((d.get("custo_capital") or {}).get("ke") or {}).get("ke_base")
    val = d.get("valuation") or {}
    ltm = d.get("ltm") or {}
    est = d.get("estatisticas_ativo") or {}

    # Valuation: variação do valor base em relação ao preço (−40% -> 0; +40% -> 10)
    base = (val.get("cenarios") or {}).get("base") or {}
    up = base.get("variacao_vs_preco")
    if up is None and val.get("valor_por_acao") and (d.get("cotacao") or {}).get("preco"):
        up = val["valor_por_acao"] / d["cotacao"]["preco"] - 1
    if up is not None:
        out["valuation"] = (_lin(up, -0.40, 0.40), f"valor base {up:+.0%} vs. preço")

    # Negócio e saúde financeira
    if fin and ltm:
        roe = ltm.get("lucro_controladores", np.nan) / ltm.get("pl_controlador", np.nan)
        pdd = abs(ltm.get("pdd", np.nan)) / ltm.get("margem_bruta_intermediacao", np.nan)
        if ke:
            out["negocio"] = (_lin(roe - ke, -0.12, 0.08), f"ROE LTM {roe:.1%} − Ke {ke:.1%} = {roe - ke:+.1%}")
        out["saude_financeira"] = (_lin(-pdd, -0.80, -0.20), f"PDD/margem bruta {pdd:.0%} (20% -> 10; 80% -> 0)")
    else:
        ind = d.get("indicadores_ultimo_ano") or {}
        roic, dl = ind.get("roic"), ind.get("divida_liquida_ebitda")
        if roic is not None and ke:
            out["negocio"] = (_lin(roic - ke, -0.10, 0.10), f"ROIC {roic:.1%} − Ke {ke:.1%}")
        if dl is not None:
            out["saude_financeira"] = (_lin(-dl, -4.0, 0.0), f"Dív. líq./EBITDA {dl:.1f}x (0x -> 10; 4x -> 0)")

    # Risco de mercado: drawdown máximo (−70% -> 0; −15% -> 10)
    if est.get("drawdown_maximo") is not None:
        out["risco_mercado"] = (_lin(est["drawdown_maximo"], -0.70, -0.15),
                                f"drawdown máx. {est['drawdown_maximo']:.0%}, vol. {est.get('volatilidade_anualizada', float('nan')):.0%}")
    # Gestão: sem regra quantitativa confiável -> vem dos analistas
    return {k: v for k, v in out.items() if v[0] is not None}


def consolidar(dados: dict, pareceres: list[dict]) -> dict:
    dq = dimensoes_quant(dados)
    # gestão: média das notas de gestão dos analistas (se houver)
    g = [p["notas_dimensoes"]["gestao"] for p in pareceres if (p.get("notas_dimensoes") or {}).get("gestao") is not None]
    if g:
        dq["gestao"] = (float(np.mean(g)), "média das avaliações qualitativas dos 3 analistas")
    pesos = {k: PESOS[k] for k in dq if k in PESOS}
    nota_quant = sum(dq[k][0] * w for k, w in pesos.items()) / sum(pesos.values()) if pesos else None
    notas = [float(p["nota"]) for p in pareceres if p.get("nota") is not None]
    nota_conselho = float(np.mean(notas)) if notas else None
    desvio = float(np.std(notas, ddof=0)) if len(notas) > 1 else 0.0
    partes = [x for x in (nota_quant, nota_conselho) if x is not None]
    final = float(np.mean(partes)) if partes else None
    travas = []
    if final is not None:
        if any(v[0] <= 2 for v in dq.values()):
            travas.append("dimensão com nota ≤ 2: final limitada a 5")
            final = min(final, 5.0)
        up = (((dados.get("valuation") or {}).get("cenarios") or {}).get("base") or {}).get("margem_seguranca")
        if up is not None and up < -0.30:
            travas.append("margem de segurança base < −30%: final limitada a 4")
            final = min(final, 4.0)
    conv = "baixa" if desvio > 2 else ("media" if desvio > 1 else "alta")
    leitura = (None if final is None else "Evitar" if final < 3 else "Pouco atrativa" if final < 5
               else "Neutra / preço justo" if final < 7 else "Atrativa" if final < 9 else "Excepcional")
    return {"nota_final": None if final is None else round(final, 1), "leitura": leitura,
            "nota_quant": None if nota_quant is None else round(nota_quant, 1),
            "nota_conselho": None if nota_conselho is None else round(nota_conselho, 1),
            "desvio_analistas": round(desvio, 2), "consenso": conv, "travas": travas,
            "dimensoes": {k: {"nota": round(v[0], 1), "regra": v[1], "peso": PESOS.get(k)} for k, v in dq.items()},
            "analistas": [{k: p.get(k) for k in ("analista", "nota", "conviccao", "veredito")} for p in pareceres]}


if __name__ == "__main__":
    import sys
    pasta = Path(sys.argv[1])
    dados = json.loads((pasta / "dados.json").read_text(encoding="utf-8"))
    pareceres = [json.loads(f.read_text(encoding="utf-8")) for f in sorted(pasta.glob("parecer_*.json"))]
    r = consolidar(dados, pareceres)
    (pasta / "nota.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(r, ensure_ascii=False, indent=2))
