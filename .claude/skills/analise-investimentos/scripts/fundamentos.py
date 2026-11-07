"""Demonstrações financeiras (CVM) -> tabelas anuais, indicadores e qualidade dos lucros.

Plano de contas padronizado da CVM para companhias NÃO financeiras. Bancos,
seguradoras e holdings usam outra estrutura: `eh_financeira()` detecta e o
relatório deve trocar as métricas (ROE, índice de Basileia, DDM, lucro residual).
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

# (demonstração, código) — contas fixas do plano CVM
CONTAS = {
    "ativo_total": ("BPA", "1"),
    "ativo_circulante": ("BPA", "1.01"),
    "caixa": ("BPA", "1.01.01"),
    "aplicacoes_financeiras": ("BPA", "1.01.02"),
    "contas_receber": ("BPA", "1.01.03"),
    "estoques": ("BPA", "1.01.04"),
    "ativo_nao_circulante": ("BPA", "1.02"),
    "imobilizado": ("BPA", "1.02.03"),
    "intangivel": ("BPA", "1.02.04"),
    "passivo_circulante": ("BPP", "2.01"),
    "emprestimos_cp": ("BPP", "2.01.04"),
    "passivo_nao_circulante": ("BPP", "2.02"),
    "emprestimos_lp": ("BPP", "2.02.01"),
    "patrimonio_liquido": ("BPP", "2.03"),
    "receita_liquida": ("DRE", "3.01"),
    "custo": ("DRE", "3.02"),
    "lucro_bruto": ("DRE", "3.03"),
    "despesas_operacionais": ("DRE", "3.04"),
    "ebit": ("DRE", "3.05"),
    "resultado_financeiro": ("DRE", "3.06"),
    "receitas_financeiras": ("DRE", "3.06.01"),
    "despesas_financeiras": ("DRE", "3.06.02"),
    "lair": ("DRE", "3.07"),
    "ir_csll": ("DRE", "3.08"),
    "lucro_liquido": ("DRE", "3.11"),
    "lucro_controladores": ("DRE", "3.11.01"),
    "fco": ("DFC", "6.01"),
    "fci": ("DFC", "6.02"),
    "fcf_financiamento": ("DFC", "6.03"),
}

# contas localizadas por descrição (variam entre companhias)
POR_DESCRICAO = {
    "depreciacao_amortizacao": ("DFC", "6.01", r"deprecia|amortiza|exaust", None),
    "capex": ("DFC", "6.02", r"(?:aquisi|adi[cç]|compra|investimento).*(?:imobilizado|intang)", "neg"),
    "dividendos_pagos": ("DFC", "6.03", r"dividend|juros sobre (?:o )?capital", "neg"),
    "recompra_acoes": ("DFC", "6.03", r"recompra|a[cç][oõ]es em tesouraria", "neg"),
    "despesas_vendas": ("DRE", "3.04", r"vendas|comerciais", None),
    "despesas_ga": ("DRE", "3.04", r"gerais e administrativas|administrativas", None),
    "participacao_nao_controladores_pl": ("BPP", "2.03", r"n[aã]o controlador", None),
}


def eh_financeira(df: pd.DataFrame) -> bool:
    d = df[(df["demonstracao"] == "DRE") & (df["CD_CONTA"] == "3.01")]["DS_CONTA"]
    return bool(d.str.contains("intermedia", case=False, na=False).any())


def _ano(df: pd.DataFrame) -> pd.Series:
    return pd.to_datetime(df["DT_FIM_EXERC"]).dt.year


def _somar_sem_duplicar(sub: pd.DataFrame) -> float:
    """Soma contas casadas, descartando filhas de contas já casadas."""
    codigos = sorted(sub["CD_CONTA"].unique(), key=len)
    mantidos = []
    for c in codigos:
        if not any(c.startswith(m + ".") for m in mantidos):
            mantidos.append(c)
    return float(sub[sub["CD_CONTA"].isin(mantidos)]["VL_CONTA"].sum())


def tabela_anual(df: pd.DataFrame) -> pd.DataFrame:
    """Linhas = contas padronizadas; colunas = anos (exercício social)."""
    d = df[df["ORDEM_EXERC"].str.upper().str.startswith("ÚLTIMO") | (df["ORDEM_EXERC"].str.upper() == "ULTIMO")].copy()
    if d.empty:
        d = df.copy()
    d["ano"] = _ano(d)
    anos = sorted(d["ano"].unique())
    out = pd.DataFrame(index=list(CONTAS) + list(POR_DESCRICAO), columns=anos, dtype=float)
    for nome, (dem, cod) in CONTAS.items():
        s = d[(d["demonstracao"] == dem) & (d["CD_CONTA"] == cod)].groupby("ano")["VL_CONTA"].last()
        out.loc[nome, s.index] = s.values
    for nome, (dem, prefixo, regex, sinal) in POR_DESCRICAO.items():
        sub = d[(d["demonstracao"] == dem) & d["CD_CONTA"].str.startswith(prefixo + ".")
                & d["DS_CONTA"].str.contains(regex, flags=re.I, na=False)]
        if sinal == "neg":
            sub = sub[sub["VL_CONTA"] < 0]
        for ano, g in sub.groupby("ano"):
            out.loc[nome, ano] = _somar_sem_duplicar(g)
    return out


def _media(s: pd.Series) -> pd.Series:
    """Média entre saldo do ano e do ano anterior (primeiro ano: saldo final)."""
    return ((s + s.shift(1)) / 2).fillna(s)


def indicadores(t: pd.DataFrame, aliquota_padrao: float = 0.34) -> pd.DataFrame:
    T = t.T.astype(float)  # anos nas linhas
    i = pd.DataFrame(index=T.index)
    rec = T["receita_liquida"]
    divida_bruta = T["emprestimos_cp"].fillna(0) + T["emprestimos_lp"].fillna(0)
    caixa = T["caixa"].fillna(0) + T["aplicacoes_financeiras"].fillna(0)
    da = T["depreciacao_amortizacao"].abs()
    ebitda = T["ebit"] + da.fillna(0)
    aliq = (-T["ir_csll"] / T["lair"]).where(lambda x: (x > 0) & (x < 0.6))
    aliq_usada = aliq.fillna(aliquota_padrao)
    nopat = T["ebit"] * (1 - aliq_usada)
    capital_investido = T["patrimonio_liquido"] + divida_bruta - caixa
    lucro = T["lucro_controladores"].fillna(T["lucro_liquido"])

    i["receita_liquida"] = rec
    i["crescimento_receita"] = rec.pct_change()
    i["margem_bruta"] = T["lucro_bruto"] / rec
    i["margem_ebit"] = T["ebit"] / rec
    i["ebitda"] = ebitda
    i["margem_ebitda"] = ebitda / rec
    i["margem_liquida"] = T["lucro_liquido"] / rec
    i["lucro_liquido"] = T["lucro_liquido"]
    i["lucro_controladores"] = lucro
    i["aliquota_efetiva"] = aliq
    i["roe"] = lucro / _media(T["patrimonio_liquido"])
    i["roa"] = T["lucro_liquido"] / _media(T["ativo_total"])
    i["nopat"] = nopat
    i["capital_investido"] = capital_investido
    i["roic"] = nopat / _media(capital_investido)
    i["divida_bruta"] = divida_bruta
    i["caixa_e_aplicacoes"] = caixa
    i["divida_liquida"] = divida_bruta - caixa
    i["divida_liquida_ebitda"] = i["divida_liquida"] / ebitda
    i["divida_liquida_pl"] = i["divida_liquida"] / T["patrimonio_liquido"]
    i["liquidez_corrente"] = T["ativo_circulante"] / T["passivo_circulante"]
    i["cobertura_juros"] = T["ebit"] / T["despesas_financeiras"].abs()
    i["fco"] = T["fco"]
    i["capex"] = T["capex"]
    i["fcf"] = T["fco"] + T["capex"].fillna(0)
    i["fco_sobre_lucro"] = T["fco"] / T["lucro_liquido"]
    i["accruals"] = T["lucro_liquido"] - T["fco"]
    i["accruals_sobre_ativo"] = i["accruals"] / _media(T["ativo_total"])
    i["dividendos_pagos"] = T["dividendos_pagos"].abs()
    i["payout_caixa"] = i["dividendos_pagos"] / lucro
    i["reinvestimento_sobre_nopat"] = (T["capex"].abs() - da) / nopat
    return i


def cagr(serie: pd.Series) -> float | None:
    s = serie.dropna()
    if len(s) < 2 or s.iloc[0] <= 0 or s.iloc[-1] <= 0:
        return None
    n = s.index[-1] - s.index[0]
    return (s.iloc[-1] / s.iloc[0]) ** (1 / n) - 1


def beneish(t: pd.DataFrame) -> pd.DataFrame:
    """Beneish (1999) M-Score, 8 variáveis. Limiar de triagem: -1,78.

    Instrumento de TRIAGEM, não prova de manipulação. Ver Beneish, M. D. (1999).
    The Detection of Earnings Manipulation. Financial Analysts Journal, 55(5), 24–36.
    """
    T = t.T.astype(float)
    vendas = T["receita_liquida"]
    cpv = T["custo"].abs()
    rec = T["contas_receber"]
    ac = T["ativo_circulante"]
    ppe = T["imobilizado"]
    tit = T["aplicacoes_financeiras"].fillna(0)
    at = T["ativo_total"]
    dep = T["depreciacao_amortizacao"].abs()
    sga = (T["despesas_vendas"].abs().fillna(0) + T["despesas_ga"].abs().fillna(0)).replace(0, np.nan)
    ll = T["lucro_liquido"]
    fco = T["fco"]
    pc = T["passivo_circulante"]
    dlp = T["emprestimos_lp"].fillna(0)

    gm = (vendas - cpv) / vendas
    aq = 1 - (ac + ppe + tit) / at
    deprate = dep / (dep + ppe)
    lev = (pc + dlp) / at
    m = pd.DataFrame(index=T.index)
    m["DSRI"] = (rec / vendas) / (rec / vendas).shift(1)
    m["GMI"] = gm.shift(1) / gm
    m["AQI"] = aq / aq.shift(1)
    m["SGI"] = vendas / vendas.shift(1)
    m["DEPI"] = deprate.shift(1) / deprate
    m["SGAI"] = (sga / vendas) / (sga / vendas).shift(1)
    m["TATA"] = (ll - fco) / at
    m["LVGI"] = lev / lev.shift(1)
    m["M_SCORE"] = (-4.84 + 0.920 * m.DSRI + 0.528 * m.GMI + 0.404 * m.AQI + 0.892 * m.SGI
                    + 0.115 * m.DEPI - 0.172 * m.SGAI + 4.679 * m.TATA - 0.327 * m.LVGI)
    m["sinal_triagem"] = np.where(m["M_SCORE"].isna(), "dados insuficientes",
                                  np.where(m["M_SCORE"] > -1.78, "acima do limiar (investigar)", "abaixo do limiar"))
    return m


def multiplos(t: pd.DataFrame, ind: pd.DataFrame, preco: float, acoes: float) -> dict:
    """Múltiplos com base no último exercício anual disponível."""
    ano = ind.index.max()
    T = t.T.astype(float).loc[ano]
    r = ind.loc[ano]
    mcap = preco * acoes
    minoritarios = float(T.get("participacao_nao_controladores_pl") or 0)
    pl_contr = T["patrimonio_liquido"] - minoritarios
    ev = mcap + r["divida_liquida"] + minoritarios
    lucro = r["lucro_controladores"]
    out = {
        "ano_base": int(ano), "preco": preco, "acoes": acoes, "valor_mercado": mcap,
        "enterprise_value": ev,
        "p_l": mcap / lucro if lucro and lucro > 0 else None,
        "p_vp": mcap / pl_contr if pl_contr > 0 else None,
        "ev_ebitda": ev / r["ebitda"] if r["ebitda"] and r["ebitda"] > 0 else None,
        "ev_ebit": ev / T["ebit"] if T["ebit"] > 0 else None,
        "p_fcf": mcap / r["fcf"] if r["fcf"] and r["fcf"] > 0 else None,
        "dividend_yield_caixa": r["dividendos_pagos"] / mcap if pd.notna(r["dividendos_pagos"]) else None,
        "lpa": lucro / acoes, "vpa": pl_contr / acoes,
        "observacoes": [
            "Múltiplos usam o último exercício anual (DFP); para TTM combine com ITR.",
            "Dividend yield calculado sobre proventos PAGOS no exercício (DFC), não sobre os declarados.",
            "Quantidade de ações deve excluir ações em tesouraria; confirme no FRE/RI.",
        ],
    }
    return out


# ---------------------------------------------------------------- heurísticas e indicadores complementares
# Servem para triagem e para conferir os agregadores (Investidor10, Status Invest).
# Não substituem DCF, DDM ou lucro residual. Ver references/formulas.md.
def numero_graham(lpa: float | None, vpa: float | None) -> float | None:
    """Graham (1949): raiz de 22,5 × LPA × VPA (P/L 15 × P/VP 1,5). Só vale com LPA e VPA positivos."""
    if not lpa or not vpa or lpa <= 0 or vpa <= 0:
        return None
    return float(np.sqrt(22.5 * lpa * vpa))


def preco_teto_bazin(dpa_medio: float | None, yield_minimo: float = 0.06) -> float | None:
    """Bazin: dividendo médio por ação ÷ yield mínimo exigido (6% por padrão).

    Com Selic alta, 6% fica abaixo da renda fixa: informe também o resultado com yield = Selic.
    """
    if not dpa_medio or dpa_medio <= 0 or yield_minimo <= 0:
        return None
    return dpa_medio / yield_minimo


def earnings_yield(lpa: float | None, preco: float) -> float | None:
    """Inverso do P/L (LPA ÷ preço). Comparar com a Selic e com o Tesouro IPCA+."""
    if lpa is None or not preco:
        return None
    return lpa / preco


def peg(p_l: float | None, crescimento_lucro: float | None) -> float | None:
    """PEG de Lynch: P/L ÷ crescimento anual esperado do lucro em pontos percentuais (ex.: 12% -> 12)."""
    if not p_l or not crescimento_lucro or crescimento_lucro <= 0:
        return None
    return p_l / (crescimento_lucro * 100)


def altman_z_emergentes(capital_giro: float, lucros_retidos: float, ebit: float,
                        patrimonio: float, passivo_total: float, ativo_total: float) -> dict:
    """Altman Z'' para mercados emergentes (Altman, 2005). Não usar em bancos.

    Z = 3,25 + 6,56·X1 + 3,26·X2 + 6,72·X3 + 1,05·X4
    X1 = capital de giro/ativo; X2 = lucros retidos/ativo; X3 = EBIT/ativo; X4 = PL/passivo total.
    """
    if not ativo_total or not passivo_total:
        raise ValueError("ativo e passivo total são obrigatórios")
    z = (3.25 + 6.56 * capital_giro / ativo_total + 3.26 * lucros_retidos / ativo_total
         + 6.72 * ebit / ativo_total + 1.05 * patrimonio / passivo_total)
    zona = "segura" if z > 5.85 else ("cinzenta" if z >= 4.35 else "risco")
    return {"z": float(z), "zona": zona}
