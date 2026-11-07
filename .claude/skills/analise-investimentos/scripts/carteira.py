"""Teoria Moderna do Portfólio (Markowitz, 1952) e métricas de risco.

TODOS os números aqui são HISTÓRICOS (DADO OBSERVADO ou estatística derivada).
Retorno histórico não é retorno esperado; covariâncias são instáveis no tempo.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

DU = 252  # dias úteis por ano


def retornos(precos: pd.DataFrame) -> pd.DataFrame:
    return precos.sort_index().pct_change(fill_method=None).dropna(how="all")


def rf_diario_de_cdi(cdi_pct_ad: pd.Series, indice: pd.Index) -> pd.Series:
    """CDI (% a.d., série SGS 12) alinhado às datas dos retornos."""
    return (cdi_pct_ad / 100).reindex(indice, method="ffill").fillna(0)


def drawdown_maximo(r: pd.Series) -> float:
    acum = (1 + r.fillna(0)).cumprod()
    return float((acum / acum.cummax() - 1).min())


def estatisticas(r: pd.Series, rf_d: pd.Series | float = 0.0, bench: pd.Series | None = None) -> dict:
    r = r.dropna()
    rf = rf_d.reindex(r.index).fillna(0) if isinstance(rf_d, pd.Series) else pd.Series(rf_d, index=r.index)
    ex = r - rf
    anos = len(r) / DU
    ret_anual = float((1 + r).prod() ** (1 / anos) - 1) if anos > 0 else np.nan
    vol = float(r.std(ddof=1) * np.sqrt(DU))
    down = ex[ex < 0]
    semidesvio = float(np.sqrt((down ** 2).sum() / len(ex)) * np.sqrt(DU)) if len(ex) else np.nan
    out = {
        "observacoes": int(len(r)), "inicio": str(r.index.min().date()), "fim": str(r.index.max().date()),
        "retorno_anualizado": ret_anual, "volatilidade_anualizada": vol,
        "sharpe": float(ex.mean() * DU / vol) if vol else np.nan,
        "sortino": float(ex.mean() * DU / semidesvio) if semidesvio else np.nan,
        "drawdown_maximo": drawdown_maximo(r),
        "var_95_diario_historico": float(np.percentile(r, 5)),
        "cvar_95_diario_historico": float(r[r <= np.percentile(r, 5)].mean()),
    }
    if bench is not None:
        b = bench.reindex(r.index)
        ok = b.notna()
        if ok.sum() > 30:
            cov = np.cov(r[ok], b[ok], ddof=1)
            out["beta"] = float(cov[0, 1] / cov[1, 1])
            out["beta_ajustado_blume"] = 0.67 * out["beta"] + 0.33
            out["correlacao_mercado"] = float(np.corrcoef(r[ok], b[ok])[0, 1])
            out["r2_mercado"] = out["correlacao_mercado"] ** 2
    return out


def beta_rolante(r: pd.Series, bench: pd.Series, janela: int = 252) -> pd.Series:
    cov = r.rolling(janela).cov(bench)
    return (cov / bench.rolling(janela).var()).dropna()


def ledoit_wolf(X: np.ndarray) -> tuple[np.ndarray, float]:
    """Encolhimento de Ledoit & Wolf (2004) rumo à identidade escalada.

    Ledoit, O. & Wolf, M. (2004). A well-conditioned estimator for large-dimensional
    covariance matrices. Journal of Multivariate Analysis, 88(2), 365–411.
    """
    X = X - X.mean(axis=0)
    n, p = X.shape
    S = X.T @ X / n
    mu = np.trace(S) / p
    F = mu * np.eye(p)
    d2 = np.linalg.norm(S - F, "fro") ** 2
    b2 = sum(np.linalg.norm(np.outer(x, x) - S, "fro") ** 2 for x in X) / n ** 2
    delta = min(b2, d2) / d2 if d2 > 0 else 1.0
    return delta * F + (1 - delta) * S, float(delta)


def metricas_carteira(w: np.ndarray, R: pd.DataFrame, rf_d: pd.Series | float, bench: pd.Series | None) -> dict:
    w = np.asarray(w, float)
    rp = R.fillna(0) @ w
    est = estatisticas(rp, rf_d, bench)
    cov = R.cov().values * DU
    sigma = float(np.sqrt(w @ cov @ w))
    mcr = cov @ w / sigma if sigma else np.zeros_like(w)
    cr = w * mcr
    est["volatilidade_wsw"] = sigma
    est["contribuicao_risco"] = {a: {"peso": float(wi), "risco_marginal": float(m), "contribuicao": float(c),
                                     "contribuicao_pct": float(c / sigma) if sigma else np.nan}
                                 for a, wi, m, c in zip(R.columns, w, mcr, cr)}
    est["diversification_ratio"] = float((w @ np.sqrt(np.diag(cov))) / sigma) if sigma else np.nan
    est["n_efetivo_hhi"] = float(1 / np.sum(w ** 2))
    return est


def comparar_inclusao(R: pd.DataFrame, pesos: dict[str, float], novo: str, rf_d, bench,
                      grade: tuple[float, ...] = (0.05, 0.10, 0.15, 0.20, 0.30)) -> dict:
    """A: carteira original; B: com novo ativo a 10%; C: grade de pesos.

    A inclusão reduz proporcionalmente os pesos existentes.
    """
    ativos = list(pesos)
    w0 = np.array([pesos[a] for a in ativos], float)
    w0 = w0 / w0.sum()
    A = metricas_carteira(w0, R[ativos], rf_d, bench)
    res = {"A_original": A, "C_grade": {}}
    if novo in ativos:
        res["aviso"] = (f"{novo} já está na carteira; os cenários mostram vender tudo (0%), "
                        f"manter o peso atual e aumentar.")
        ativos_sem = [a for a in ativos if a != novo]
        base = np.array([pesos[a] for a in ativos_sem], float)
        base = base / base.sum()
        atual = round(float(w0[ativos.index(novo)]), 4)
        grade = tuple(sorted(set((0.0, atual) + tuple(grade))))
    else:
        ativos_sem, base = ativos, w0
    cols = ativos_sem + [novo]
    for x in grade:
        w = np.append(base * (1 - x), x)
        m = metricas_carteira(w, R[cols], rf_d, bench)
        res["C_grade"][f"{x:.0%}"] = {k: m[k] for k in ("retorno_anualizado", "volatilidade_anualizada",
                                                        "sharpe", "sortino", "drawdown_maximo",
                                                        "diversification_ratio")}
        res["C_grade"][f"{x:.0%}"]["contribuicao_risco_novo_pct"] = m["contribuicao_risco"][novo]["contribuicao_pct"]
        if abs(x - 0.10) < 1e-9:
            res["B_com_10pct"] = m
    return res


def fronteira_monte_carlo(R: pd.DataFrame, rf_anual: float, n: int = 20000, seed: int = 42,
                          shrink: bool = True, max_peso: float = 1.0) -> dict:
    """Fronteira por simulação (pesos Dirichlet, sem venda a descoberto).

    Usa média histórica como proxy de retorno esperado — premissa fraca
    (ver Michaud, 1989; DeMiguel, Garlappi & Uppal, 2009). Reporte como ilustração.
    """
    rng = np.random.default_rng(seed)
    X = R.dropna().values
    mu = X.mean(axis=0) * DU
    cov, delta = ledoit_wolf(X) if shrink else (np.cov(X, rowvar=False, ddof=1), 0.0)
    cov = cov * DU
    W = rng.dirichlet(np.ones(X.shape[1]), n)
    W = W[(W <= max_peso).all(axis=1)]
    ret = W @ mu
    vol = np.sqrt(np.einsum("ij,jk,ik->i", W, cov, W))
    sh = (ret - rf_anual) / vol
    imin, imax = int(vol.argmin()), int(sh.argmax())
    nomes = list(R.columns)
    return {
        "metodo": "Monte Carlo (Dirichlet), long-only" + (f", Ledoit-Wolf delta={delta:.2f}" if shrink else ""),
        "minima_variancia": {"pesos": dict(zip(nomes, W[imin].round(4))), "retorno": float(ret[imin]), "vol": float(vol[imin])},
        "max_sharpe": {"pesos": dict(zip(nomes, W[imax].round(4))), "retorno": float(ret[imax]),
                       "vol": float(vol[imax]), "sharpe": float(sh[imax])},
        "pontos": pd.DataFrame({"retorno": ret, "vol": vol, "sharpe": sh}).sample(min(2000, len(ret)), random_state=seed),
    }


def estabilidade_pesos(R: pd.DataFrame, rf_anual: float, reamostras: int = 200, seed: int = 7) -> pd.DataFrame:
    """Bootstrap dos retornos -> distribuição dos pesos de máximo Sharpe (instabilidade)."""
    rng = np.random.default_rng(seed)
    X = R.dropna()
    linhas = []
    for _ in range(reamostras):
        amostra = X.iloc[rng.integers(0, len(X), len(X))]
        f = fronteira_monte_carlo(amostra, rf_anual, n=3000, seed=int(rng.integers(1e9)))
        linhas.append(f["max_sharpe"]["pesos"])
    return pd.DataFrame(linhas).describe(percentiles=[0.05, 0.5, 0.95]).T


def monte_carlo_patrimonio(R: pd.DataFrame, w: np.ndarray, anos: int, n: int = 5000, seed: int = 1) -> dict:
    """Bootstrap em blocos mensais (~21 d.u.) de retornos históricos da carteira."""
    rng = np.random.default_rng(seed)
    rp = (R.fillna(0) @ np.asarray(w)).values
    bloco = 21
    nblocos = int(np.ceil(anos * DU / bloco))
    inicios = rng.integers(0, len(rp) - bloco, size=(n, nblocos))
    finais = np.array([np.prod(1 + np.concatenate([rp[s:s + bloco] for s in linha])) for linha in inicios])
    q = np.percentile(finais, [5, 25, 50, 75, 95])
    return {"horizonte_anos": anos, "simulacoes": n, "multiplo_patrimonio_p5_p25_p50_p75_p95": q.round(3).tolist(),
            "prob_perda_nominal": float((finais < 1).mean()),
            "aviso": "Reamostragem do passado; não captura regimes ou choques inéditos."}
