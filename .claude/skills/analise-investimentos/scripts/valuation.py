"""Valuation: CAPM, WACC, DCF (FCFF), Gordon, DDM, lucro residual, sensibilidade.

Regra: NENHUMA premissa tem valor padrão. Se faltar algo, o cálculo é
interrompido com a lista do que falta (regra 'não preencha lacunas com
suposições silenciosas'). As premissas vêm de um JSON documentado com fonte.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

OBRIGATORIAS_DCF = [
    "ano_base", "receita_base", "anos_projecao", "crescimento_receita", "margem_ebit",
    "aliquota_ir", "da_sobre_receita", "capex_sobre_receita", "capital_giro_sobre_receita",
    "crescimento_terminal", "rf", "beta", "premio_risco_mercado", "custo_divida_pre_ir",
    "peso_divida", "divida_liquida", "acoes",
]


class PremissasIncompletas(ValueError):
    pass


def carregar_premissas(caminho: str | Path) -> dict:
    p = json.loads(Path(caminho).read_text(encoding="utf-8"))
    return p


def _exigir(p: dict, campos: list[str]) -> None:
    faltam = [c for c in campos if p.get(c) is None]
    if faltam:
        raise PremissasIncompletas("Premissas ausentes: " + ", ".join(faltam))


def _vetor(v, n: int) -> np.ndarray:
    """Aceita escalar ou lista (um valor por ano projetado)."""
    if isinstance(v, (int, float)):
        return np.full(n, float(v))
    a = np.asarray(v, float)
    if len(a) != n:
        raise PremissasIncompletas(f"Lista com {len(a)} valores; esperado {n} (anos_projecao)")
    return a


def capm(rf: float, beta: float, premio: float, premio_adicional: float = 0.0) -> float:
    """Ke = Rf + β (E[Rm] − Rf) [+ prêmio adicional explícito, p.ex. tamanho/liquidez]."""
    return rf + beta * premio + premio_adicional


def wacc(ke: float, kd_pre: float, t: float, peso_divida: float) -> float:
    """WACC = Ke·E/V + Kd·(1−T)·D/V."""
    return ke * (1 - peso_divida) + kd_pre * (1 - t) * peso_divida


def dcf_fcff(p: dict, *, sobrescrever: dict | None = None) -> dict:
    p = {**p, **(sobrescrever or {})}
    _exigir(p, OBRIGATORIAS_DCF)
    n = int(p["anos_projecao"])
    g = _vetor(p["crescimento_receita"], n)
    mg = _vetor(p["margem_ebit"], n)
    da = _vetor(p["da_sobre_receita"], n)
    cx = _vetor(p["capex_sobre_receita"], n)
    cg = _vetor(p["capital_giro_sobre_receita"], n)
    t = float(p["aliquota_ir"])
    ke = capm(p["rf"], p["beta"], p["premio_risco_mercado"], p.get("premio_adicional", 0.0))
    w = p.get("wacc_override") or wacc(ke, p["custo_divida_pre_ir"], t, p["peso_divida"])
    gt = float(p["crescimento_terminal"])
    if gt >= w:
        raise PremissasIncompletas(f"Crescimento terminal ({gt:.2%}) >= WACC ({w:.2%}): modelo indefinido")

    receita = p["receita_base"] * np.cumprod(1 + g)
    receita_ant = np.concatenate([[p["receita_base"]], receita[:-1]])
    ebit = receita * mg
    nopat = ebit * (1 - t)
    d_a = receita * da
    capex = receita * cx
    dcg = (receita - receita_ant) * cg
    fcff = nopat + d_a - capex - dcg
    anos = np.arange(1, n + 1)
    # convenção de meio de ano opcional
    expo = anos - 0.5 if p.get("meio_de_ano") else anos
    fd = (1 + w) ** -expo
    vp_fluxos = float((fcff * fd).sum())
    # valor terminal: FCFF_{n+1} consistente com ROIC de longo prazo, se informado
    if p.get("roic_terminal"):
        reinvest = gt / p["roic_terminal"]
        fcff_term = nopat[-1] * (1 + gt) * (1 - reinvest)
    else:
        fcff_term = fcff[-1] * (1 + gt)
    vt = fcff_term / (w - gt)
    vp_vt = float(vt * fd[-1])
    ev = vp_fluxos + vp_vt
    equity = ev - p["divida_liquida"] - p.get("minoritarios", 0.0) + p.get("ativos_nao_operacionais", 0.0)
    por_acao = equity / p["acoes"]
    tabela = pd.DataFrame({"ano": p["ano_base"] + anos, "receita": receita, "ebit": ebit, "nopat": nopat,
                           "d&a": d_a, "capex": capex, "delta_capital_giro": dcg, "fcff": fcff,
                           "fator_desconto": fd, "vp_fcff": fcff * fd})
    return {"ke": ke, "wacc": w, "crescimento_terminal": gt, "vp_fluxos": vp_fluxos,
            "valor_terminal": float(vt), "vp_valor_terminal": vp_vt,
            "peso_valor_terminal": vp_vt / ev if ev else np.nan, "enterprise_value": ev,
            "equity_value": equity, "valor_por_acao": por_acao, "projecao": tabela}


def sensibilidade(p: dict, var_linha: str, valores_linha, var_coluna: str, valores_coluna) -> pd.DataFrame:
    """Matriz de valor por ação variando duas premissas (ex.: wacc_override × crescimento_terminal)."""
    m = pd.DataFrame(index=[f"{v:.2%}" for v in valores_linha], columns=[f"{v:.2%}" for v in valores_coluna], dtype=float)
    m.index.name, m.columns.name = var_linha, var_coluna
    for a in valores_linha:
        for b in valores_coluna:
            try:
                m.loc[f"{a:.2%}", f"{b:.2%}"] = dcf_fcff(p, sobrescrever={var_linha: a, var_coluna: b})["valor_por_acao"]
            except PremissasIncompletas:
                m.loc[f"{a:.2%}", f"{b:.2%}"] = np.nan
    return m


def cenarios(p: dict) -> dict:
    """p['cenarios'] = {"pessimista": {...overrides}, "base": {}, "otimista": {...}} — opcional."""
    out = {}
    for nome, ov in (p.get("cenarios") or {"base": {}}).items():
        r = dcf_fcff(p, sobrescrever=ov)
        out[nome] = {k: r[k] for k in ("wacc", "enterprise_value", "equity_value", "valor_por_acao", "peso_valor_terminal")}
    return out


def gordon(dividendo_proximo: float, ke: float, g: float) -> float:
    """P0 = D1 / (Ke − g)."""
    if g >= ke:
        raise PremissasIncompletas("g >= Ke no modelo de Gordon")
    return dividendo_proximo / (ke - g)


def ddm_dois_estagios(d0: float, g1: float, n: int, g2: float, ke: float) -> float:
    d = d0 * np.cumprod(np.full(n, 1 + g1))
    vp = float((d / (1 + ke) ** np.arange(1, n + 1)).sum())
    return vp + gordon(d[-1] * (1 + g2), ke, g2) / (1 + ke) ** n


def lucro_residual(vpa0: float, roe: list[float], payout: float, ke: float, g_terminal: float) -> float:
    """V0 = VPA0 + Σ (ROE_t − Ke)·VPA_{t−1}/(1+Ke)^t + terminal (Ohlson, 1995)."""
    vpa, v = vpa0, vpa0
    for t, r in enumerate(roe, 1):
        ri = (r - ke) * vpa
        v += ri / (1 + ke) ** t
        vpa = vpa * (1 + r * (1 - payout))
    ri_term = (roe[-1] - ke) * vpa
    v += ri_term / (ke - g_terminal) / (1 + ke) ** len(roe)
    return v


def margem_seguranca(valor_justo: float, preco: float) -> float:
    """(Valor justo − Preço) / Valor justo."""
    return (valor_justo - preco) / valor_justo


def premissas_implicitas_no_preco(p: dict, preco: float, variavel: str = "crescimento_receita",
                                  lo: float = -0.2, hi: float = 0.5) -> float | None:
    """Engenharia reversa (reverse DCF): que valor da variável justifica o preço atual?"""
    def f(x):
        return dcf_fcff(p, sobrescrever={variavel: x})["valor_por_acao"] - preco
    try:
        a, b = f(lo), f(hi)
    except PremissasIncompletas:
        return None
    if a * b > 0:
        return None
    for _ in range(80):
        mid = (lo + hi) / 2
        fm = f(mid)
        if a * fm <= 0:
            hi, b = mid, fm
        else:
            lo, a = mid, fm
    return (lo + hi) / 2


# ---------------------------------------------------------------- custo de capital e bancos
def ke_brasil(rf_brl: float, beta: float, erp_total: float, spread_default: float, erp_maduro: float) -> dict:
    """Ke em R$ por dois métodos usuais (Damodaran), para não contar o risco-país duas vezes.

    A: (Rf_BRL − spread de default soberano) + β × ERP total do país
    B: Rf_BRL + β × ERP de mercado maduro (o Rf local já embute o risco soberano)
    """
    a = rf_brl - spread_default + beta * erp_total
    b = rf_brl + beta * erp_maduro
    return {"ke_metodo_a": a, "ke_metodo_b": b, "ke_base": round((a + b) / 2, 4)}


def valuation_banco(vpa0: float, preco: float, ke: float, g: float, payout: float,
                    cenarios: dict, anos: int = 5) -> dict:
    """Lucro residual em 2 estágios: ROE do ano 1 converge linearmente ao ROE sustentável no ano N.

    cenarios = {"pessimista": [roe_ano1, roe_sust], "base": [...], "otimista": [...]}
    """
    def v(r1, rs, k=ke, gg=g, vpa=vpa0):
        return lucro_residual(vpa, list(np.linspace(r1, rs, anos)), payout, k, gg)

    out = {"vpa0": vpa0, "preco": preco, "ke": ke, "g": g, "payout": payout, "cenarios": {}}
    for nome, (r1, rs) in cenarios.items():
        val = v(r1, rs)
        out["cenarios"][nome] = {"roe_ano1": r1, "roe_sustentavel": rs, "valor_por_acao": val,
                                 "p_vp_implicito": val / vpa0, "margem_seguranca": margem_seguranca(val, preco),
                                 "variacao_vs_preco": val / preco - 1}
    r1_base = cenarios.get("base", list(cenarios.values())[0])[0]
    roes = [0.10, 0.12, 0.14, 0.16, 0.18, 0.20]
    kes = [ke - 0.02, ke - 0.01, ke, ke + 0.01, ke + 0.02]
    out["sens_ke_roe"] = pd.DataFrame({f"ROE {r:.0%}": [v(r1_base, r, k=k) for k in kes] for r in roes},
                                      index=[f"Ke {k:.1%}" for k in kes])
    out["sens_g_roe"] = pd.DataFrame({f"ROE {r:.0%}": [v(r1_base, r, gg=x) for x in (g - 0.01, g, g + 0.01)] for r in roes},
                                     index=[f"g {x:.1%}" for x in (g - 0.01, g, g + 0.01)])
    # ROE sustentável implícito no preço
    pvp = preco / vpa0
    out["roe_implicito_gordon"] = g + pvp * (ke - g)
    lo, hi = -0.2, 0.6
    for _ in range(80):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if v(r1_base, mid) < preco else (lo, mid)
    out["roe_implicito_2_estagios"] = (lo + hi) / 2
    return out
