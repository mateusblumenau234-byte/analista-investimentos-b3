"""Instituições financeiras (DFs IFRS na CVM): tabela anual, indicadores e LTM.

Contas localizadas por DESCRIÇÃO dentro dos grupos (o plano de bancos varia mais
que o de companhias não financeiras). Métricas: ROE, ROA, alavancagem, eficiência,
custo do risco (PDD/margem), payout. Basileia e inadimplência NÃO constam nas DFs
padronizadas da CVM — buscá-las no release/Pilar 3 do banco.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

# nome: (demonstração, prefixo do grupo, regex da descrição, só no nível do grupo?)
CONTAS_BANCO = {
    "ativo_total": ("BPA", "1", r"^ativo total", True),
    "ativos_financeiros": ("BPA", "1", r"^ativos financeiros$", False),
    "caixa": ("BPA", "1", r"^caixa e equivalentes", False),
    "pl_total": ("BPP", "2", r"^patrim[oô]nio l[ií]quido consolidado", False),
    "pl_controlador": ("BPP", "2", r"patrim[oô]nio l[ií]quido atribu[ií]do ao controlador", False),
    "depositos": ("BPP", "2", r"^dep[oó]sitos$", False),
    "receita_intermediacao": ("DRE", "3", r"^receitas? (?:de|da) intermedia", False),
    "despesa_intermediacao": ("DRE", "3", r"^despesas? (?:de|da) intermedia", False),
    "margem_bruta_intermediacao": ("DRE", "3", r"^resultado bruto (?:(?:de|da) )?intermedia", False),
    "pdd": ("DRE", "3", r"provis[aã]o para (?:perdas?|cr[eé]dito)|perda esperada", False),
    "receita_servicos": ("DRE", "3", r"presta[cç][aã]o de servi[cç]os|tarifas", False),
    "despesas_pessoal": ("DRE", "3", r"despesas? (?:com|de) pessoal", False),
    "despesas_administrativas": ("DRE", "3", r"administrativas", False),
    "equivalencia": ("DRE", "3", r"equival[eê]ncia patrimonial", False),
    "lair": ("DRE", "3", r"^resultado antes dos tributos", False),
    "ir_csll": ("DRE", "3", r"^imposto de renda e contribui[cç][aã]o social", False),
    "lucro_liquido": ("DRE", "3", r"^lucro(?: ou |/)preju[ií]zo(?: l[ií]quido)? consolidado", False),
    "lucro_controladores": ("DRE", "3", r"atribu[ií]do a(?:os)? s[oó]cios da (?:empresa )?controladora", False),
    "fco": ("DFC", "6", r"^caixa l[ií]quido (?:das|de) atividades operacionais", False),
    "dividendos_pagos": ("DFC", "6.03", r"dividend|juros sobre (?:o )?capital pr[oó]prio", False),
}


def _primeiro_nivel(sub: pd.DataFrame) -> pd.DataFrame:
    """Entre contas casadas, mantém só as que não têm ancestral casado."""
    cods = sorted(sub["CD_CONTA"].unique(), key=len)
    mant = []
    for c in cods:
        if not any(c.startswith(m + ".") for m in mant):
            mant.append(c)
    return sub[sub["CD_CONTA"].isin(mant)]


def _extrair(d: pd.DataFrame, chave_periodo: str) -> pd.DataFrame:
    linhas = {}
    for nome, (dem, prefixo, regex, _) in CONTAS_BANCO.items():
        sub = d[(d["demonstracao"] == dem)
                & ((d["CD_CONTA"] == prefixo) | d["CD_CONTA"].str.startswith(prefixo + "."))
                & d["DS_CONTA"].str.strip().str.contains(regex, flags=re.I, na=False)]
        if nome == "dividendos_pagos":
            sub = sub[sub["VL_CONTA"] < 0]
            # exclui dividendos RECEBIDOS (grupo de investimento) — já filtrado pelo prefixo 6.03
        if sub.empty:
            continue
        linhas[nome] = _primeiro_nivel(sub).groupby(chave_periodo)["VL_CONTA"].sum()
    return pd.DataFrame(linhas).T


def tabela_anual_banco(dfp: pd.DataFrame) -> pd.DataFrame:
    d = dfp[dfp["ORDEM_EXERC"].str.upper().str.startswith(("ÚLTIMO", "ULTIMO"))].copy()
    d["ano"] = pd.to_datetime(d["DT_FIM_EXERC"]).dt.year
    t = _extrair(d, "ano")
    return t.reindex(columns=sorted(t.columns))


def ltm_banco(dfp_ano: pd.DataFrame, itr: pd.DataFrame) -> dict | None:
    """Últimos 12 meses: exercício anual + acumulado do ano corrente − acumulado do ano anterior.

    Saldos (balanço) usam a data do último ITR.
    """
    if itr is None or itr.empty:
        return None
    ult = itr["DT_REFER"].max()
    i = itr[itr["DT_REFER"] == ult].copy()
    ini_ano = i["DT_FIM_EXERC"].str[:4] + "-01-01"
    acum = i[(i["DT_INI_EXERC"].isna()) | (i["DT_INI_EXERC"] == ini_ano) | (i["demonstracao"].isin(["BPA", "BPP"]))]
    acum = acum.assign(periodo=acum["ORDEM_EXERC"].str.upper().str.startswith(("ÚLTIMO", "ULTIMO")).map({True: "atual", False: "anterior"}))
    # balanço: PENÚLTIMO = 31/12 do ano anterior; resultado/DFC: PENÚLTIMO = mesmo período do ano anterior
    t = _extrair(acum, "periodo")
    ano_ant = int(ult[:4]) - 1
    if ano_ant not in dfp_ano.columns or "atual" not in t.columns:
        return None
    fluxo = {k for k, v in CONTAS_BANCO.items() if v[0] in ("DRE", "DFC")}
    out = {"data_referencia": ult, "meses_acumulados": int(ult[5:7])}
    for k in t.index:
        if k in fluxo:
            if "anterior" in t.columns and pd.notna(t.loc[k].get("anterior")) and pd.notna(dfp_ano.loc[k, ano_ant] if k in dfp_ano.index else np.nan):
                out[k] = float(dfp_ano.loc[k, ano_ant] + t.loc[k, "atual"] - t.loc[k, "anterior"])
        else:
            out[k] = float(t.loc[k, "atual"])
    # bancos sem segregação de não controladores: usa os totais
    out.setdefault("lucro_controladores", out.get("lucro_liquido"))
    out.setdefault("pl_controlador", out.get("pl_total"))
    return out


def indicadores_banco(t: pd.DataFrame) -> pd.DataFrame:
    T = t.T.astype(float)
    for c in CONTAS_BANCO:  # contas ausentes viram NaN (planos de contas variam entre bancos)
        if c not in T.columns:
            T[c] = np.nan
    i = pd.DataFrame(index=T.index)
    media = lambda s: ((s + s.shift(1)) / 2).fillna(s)  # noqa: E731
    pl = T["pl_controlador"].fillna(T["pl_total"])
    ll = T["lucro_controladores"].fillna(T["lucro_liquido"])
    receitas_op = T["margem_bruta_intermediacao"]  # resultado bruto de intermediação, antes da PDD
    custos = T["despesas_pessoal"].abs().fillna(0) + T["despesas_administrativas"].abs().fillna(0)
    i["lucro_controladores"] = ll
    i["crescimento_lucro"] = ll.pct_change()
    i["pl_controlador"] = pl
    i["roe"] = ll / media(pl)
    i["roa"] = T["lucro_liquido"] / media(T["ativo_total"])
    i["alavancagem_ativo_pl"] = T["ativo_total"] / T["pl_total"].fillna(pl)
    i["margem_bruta_intermediacao"] = T["margem_bruta_intermediacao"]
    i["margem_sobre_ativos"] = T["margem_bruta_intermediacao"] / media(T["ativo_total"])
    i["pdd"] = T["pdd"].abs()
    i["pdd_sobre_margem"] = T["pdd"].abs() / T["margem_bruta_intermediacao"]
    i["receita_servicos"] = T["receita_servicos"]
    i["indice_eficiencia"] = custos / (receitas_op + T["receita_servicos"].fillna(0))
    i["aliquota_efetiva"] = -T["ir_csll"] / T["lair"]
    i["dividendos_pagos"] = T["dividendos_pagos"].abs()
    i["payout_caixa"] = i["dividendos_pagos"] / ll
    return i


def multiplos_banco(ll_ltm: float, pl_contr: float, preco: float, acoes: float, dividendos_12m: float | None) -> dict:
    mcap = preco * acoes
    return {"preco": preco, "acoes": acoes, "valor_mercado": mcap,
            "p_l_ltm": mcap / ll_ltm if ll_ltm > 0 else None,
            "p_vp": mcap / pl_contr, "lpa_ltm": ll_ltm / acoes, "vpa": pl_contr / acoes,
            "dividend_yield_caixa": (dividendos_12m / mcap) if dividendos_12m else None,
            "p_vp_justificado_formula": "P/VP* = (ROE − g) / (Ke − g)  [Gordon aplicado ao valor patrimonial]"}


def pvp_justificado(roe: float, ke: float, g: float) -> float:
    """Valor justo / VPA em estado estacionário: (ROE − g)/(Ke − g). Exige Ke > g."""
    if ke <= g:
        raise ValueError("Ke deve ser maior que g")
    return (roe - g) / (ke - g)
