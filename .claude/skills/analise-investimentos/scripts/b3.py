"""Preços oficiais da B3 (COTAHIST) ajustados por eventos corporativos — sem token.

- COTAHIST_A<ANO>.ZIP (bvmf.bmfbovespa.com.br): cotações diárias de todos os ativos.
  Cada ano é lido UMA vez e salvo em cache compacto (só mercado à vista, lote padrão).
  Anos encerrados ficam em cache permanente; o ano corrente é renovado a cada 12 h.
- Eventos (sistemaswebb3-listados.b3.com.br): desdobramentos, grupamentos, bonificações
  e proventos em dinheiro, usados para o ajuste retroativo (como no "adjusted close").

Ajuste aplicado: para cada evento com data-com D, preços até D são multiplicados por
  - desdobramento/bonificação com fator f%: 1 / (1 + f/100)
  - grupamento com fator f (ações novas por antiga): 1 / f
  - provento em dinheiro de R$ v por ação: (1 − v / fechamento em D)
"""
from __future__ import annotations

import base64
import datetime as dt
import io
import json
import time
import zipfile

import numpy as np
import pandas as pd

import fontes as fx

COTAHIST_URL = "https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A{ano}.ZIP"
EVENTOS_URL = "https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall/GetListedSupplementCompany/{param}"


def _ano_compacto(ano: int) -> pd.DataFrame:
    """Lê o COTAHIST de um ano e devolve (data, ticker, isin, fechamento, volume)."""
    cache = fx._cache_path(f"cotahist_{ano}.csv.gz")
    corrente = ano >= dt.date.today().year
    if cache.exists() and (not corrente or (time.time() - cache.stat().st_mtime) / 3600 < 12):
        return pd.read_csv(cache, dtype={"ticker": str, "isin": str}, parse_dates=["data"])
    url = COTAHIST_URL.format(ano=ano)
    bruto = fx._get(url, timeout=600).content
    z = zipfile.ZipFile(io.BytesIO(bruto))
    linhas = []
    with z.open(z.namelist()[0]) as f:
        for ln in io.TextIOWrapper(f, encoding="latin-1"):
            # registro 01, BDI 02 (lote padrão) ou 12 (FII) / 14 (ETF), mercado à vista 010
            if ln[0:2] != "01" or ln[24:27] != "010" or ln[10:12] not in ("02", "12", "14"):
                continue
            linhas.append((ln[2:10], ln[12:24].strip(), ln[230:242], int(ln[108:121]) / 100,
                           int(ln[170:188]) / 100, int(ln[210:217])))
    df = pd.DataFrame(linhas, columns=["data", "ticker", "isin", "fechamento", "volume", "fatcot"])
    df["data"] = pd.to_datetime(df["data"], format="%Y%m%d")
    df["fechamento"] = df["fechamento"] / df["fatcot"].replace(0, 1)  # cotação por lote de 1000 (raro)
    df = df.drop(columns="fatcot")
    df.to_csv(cache, index=False, compression="gzip")
    fx.PROV.add(f"B3 — COTAHIST {ano}", url)
    return df


def _num(s: str) -> float:
    return float(str(s).replace(".", "").replace(",", "."))


def eventos(ticker: str) -> dict:
    """Desdobramentos/grupamentos/bonificações e proventos em dinheiro do emissor."""
    emissor = ticker[:4].upper()
    param = base64.b64encode(json.dumps({"issuingCompany": emissor, "language": "pt-br"}).encode()).decode()
    url = EVENTOS_URL.format(param=param)
    cache = fx._cache_path(f"eventos_{emissor}.json")
    if cache.exists() and (time.time() - cache.stat().st_mtime) / 3600 < 24:
        js = json.loads(cache.read_text())
    else:
        js = fx._get(url).json()
        cache.write_text(json.dumps(js))
        fx.PROV.add("B3 — eventos corporativos e proventos", url.split("/GetListed")[0], emissor)
    return js[0] if isinstance(js, list) and js else (js or {})


def _fatores(ev: dict, isins: set[str], fech: pd.Series) -> pd.Series:
    """Fator multiplicativo acumulado por data (1 = sem ajuste)."""
    fator = pd.Series(1.0, index=fech.index)
    vistos = set()
    for e in ev.get("stockDividends") or []:
        if e.get("isinCode") not in isins:
            continue
        d = pd.to_datetime(e["lastDatePrior"], dayfirst=True)
        f = _num(e["factor"])
        rotulo = e.get("label", "").upper()
        chave = (d, rotulo, f)
        if chave in vistos or f <= 0:
            continue
        vistos.add(chave)
        razao = f if "GRUPAMENTO" in rotulo else 1 + f / 100
        fator[fator.index <= d] /= razao
    for e in ev.get("cashDividends") or []:
        if e.get("isinCode") not in isins:
            continue
        d = pd.to_datetime(e["lastDatePrior"], dayfirst=True)
        v = _num(e["rate"])
        chave = (d, e.get("label"), v, e.get("relatedTo"))
        if chave in vistos or v <= 0:
            continue
        vistos.add(chave)
        base = fech[fech.index <= d]
        if base.empty:
            continue
        # o provento é por ação na base da data-com: compara com o preço não ajustado daquele dia
        p = base.iloc[-1]
        if p > v:
            fator[fator.index <= d] *= (1 - v / p)
    return fator


def precos_ajustados(tickers: list[str], anos: int = 5, ajustar: bool = True) -> pd.DataFrame:
    """Fechamentos diários ajustados para os tickers (ex.: BBAS3, BOVA11)."""
    hoje = dt.date.today()
    lista = [t.upper().replace(".SA", "") for t in tickers]
    from concurrent.futures import ThreadPoolExecutor

    def _um(ano):
        try:
            return _ano_compacto(ano)
        except fx.FonteIndisponivel:
            return None
    # downloads em paralelo (cada ano ~100 MB na primeira vez; depois vem do cache)
    with ThreadPoolExecutor(max_workers=6) as ex:
        anuais = list(ex.map(_um, range(hoje.year - anos, hoje.year + 1)))
    partes = [a[a["ticker"].isin(lista)] for a in anuais if a is not None]
    if not partes:
        raise fx.FonteIndisponivel("COTAHIST indisponível")
    df = pd.concat(partes)
    inicio = pd.Timestamp(hoje) - pd.DateOffset(years=anos)
    out = {}
    for t in lista:
        d = df[df["ticker"] == t].drop_duplicates("data").set_index("data").sort_index()
        if d.empty:
            continue
        fech = d["fechamento"]
        if ajustar:
            try:
                ev = eventos(t)
                fech = fech * _fatores(ev, set(d["isin"].unique()), fech)
            except Exception as e:  # sem eventos: devolve sem ajuste e avisa
                fx.PROV.add("B3 — eventos (FALHOU)", EVENTOS_URL, f"{t}: {e}; série NÃO ajustada")
        out[t] = fech[fech.index >= inicio]
    if not out:
        raise fx.FonteIndisponivel(f"Nenhum dos tickers {lista} encontrado no COTAHIST")
    return pd.DataFrame(out).sort_index()


def ultimo_fechamento(ticker: str) -> dict:
    a = _ano_compacto(dt.date.today().year)
    d = a[a["ticker"] == ticker.upper()].sort_values("data")
    if d.empty:
        raise fx.FonteIndisponivel(f"{ticker} sem negócios no COTAHIST do ano")
    r = d.iloc[-1]
    return {"preco": float(r["fechamento"]), "moeda": "BRL", "horario": str(r["data"].date()),
            "atraso_aviso": "Fechamento oficial B3 (COTAHIST) do último pregão disponível."}


def checar_saltos(p: pd.DataFrame, limite: float = 0.35) -> dict:
    """Retornos diários acima do limite sugerem evento não ajustado."""
    r = p.pct_change(fill_method=None)
    return {c: [str(i.date()) for i in r.index[np.abs(r[c]) > limite]] for c in r.columns}
