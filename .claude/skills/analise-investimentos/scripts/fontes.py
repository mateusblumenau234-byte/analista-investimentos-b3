"""Coleta de dados em tempo real de fontes primárias.

Fontes:
  - CVM (dados.cvm.gov.br): DFP, ITR, FCA (ticker -> CNPJ), cadastro.
  - Banco Central (SGS e Olinda/Focus): Selic, CDI, IPCA, câmbio, expectativas.
  - Yahoo Finance (chart API): preços ajustados de ações e do Ibovespa.

Toda coleta é registrada em um "registro de proveniência" (URL, data/hora de
coleta, observações) para que o relatório possa citar a origem de cada número.
Os downloads ficam em cache local (diretório .cache) para evitar repetição.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import os
import time
import zipfile
from dataclasses import dataclass, field, asdict
from pathlib import Path

import pandas as pd
import requests

USER_AGENT = "analise-investimentos/1.0 (pesquisa academica; python-requests)"
CACHE_DIR = Path(os.environ.get("ANALISE_CACHE", Path.home() / ".cache" / "analise-investimentos"))
CVM_BASE = "https://dados.cvm.gov.br/dados/CIA_ABERTA"
SGS_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"
FOCUS_URL = "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/ExpectativasMercadoAnuais"
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{simbolo}"

# Séries do SGS/BCB mais usadas
SGS = {
    "selic_meta": 432,      # % a.a.
    "selic_diaria": 11,     # % a.d.
    "cdi_diario": 12,       # % a.d.
    "ipca_mensal": 433,     # % a.m.
    "ptax_venda": 1,        # R$/US$
    "pib_mensal": 4380,     # R$ milhões (valores correntes)
    "desemprego": 24369,    # taxa de desocupação PNAD (%)
}


class FonteIndisponivel(RuntimeError):
    """A fonte não respondeu ou os dados não existem."""


@dataclass
class Registro:
    fonte: str
    url: str
    coletado_em: str
    observacao: str = ""


@dataclass
class Proveniencia:
    registros: list[Registro] = field(default_factory=list)

    def add(self, fonte: str, url: str, observacao: str = "") -> None:
        agora = dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
        self.registros.append(Registro(fonte, url, agora, observacao))

    def to_list(self) -> list[dict]:
        return [asdict(r) for r in self.registros]


PROV = Proveniencia()


# ---------------------------------------------------------------- HTTP / cache
def _get(url: str, params: dict | None = None, *, tentativas: int = 4, timeout: int = 60) -> requests.Response:
    ultimo_erro: Exception | None = None
    for i in range(tentativas):
        try:
            r = requests.get(url, params=params, timeout=timeout,
                             headers={"User-Agent": USER_AGENT, "Cache-Control": "no-cache"})
            if r.status_code == 304 or (r.status_code == 200 and not r.content):
                raise RuntimeError(f"resposta vazia ({r.status_code}) em {r.url}")
            if r.status_code == 404:
                raise FonteIndisponivel(f"404 em {r.url}")
            r.raise_for_status()
            return r
        except FonteIndisponivel:
            raise
        except Exception as e:  # rede, 5xx, 429
            ultimo_erro = e
            time.sleep(2 ** (i + 1))
    raise FonteIndisponivel(f"Falha ao acessar {url}: {ultimo_erro}")


def _cache_path(nome: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / nome


def _baixar_binario(url: str, nome_cache: str, max_idade_h: float) -> bytes:
    p = _cache_path(nome_cache)
    if p.exists() and (time.time() - p.stat().st_mtime) / 3600 < max_idade_h:
        return p.read_bytes()
    conteudo = _get(url, timeout=300).content
    p.write_bytes(conteudo)
    return conteudo


# ---------------------------------------------------------------- CVM
def _ler_csv_zip(z: zipfile.ZipFile, nome: str) -> pd.DataFrame:
    with z.open(nome) as f:
        return pd.read_csv(f, sep=";", encoding="latin-1", dtype=str)


def cvm_ticker_para_empresa(ticker: str, ano: int | None = None) -> dict:
    """Resolve ticker -> CNPJ/CD_CVM/nome usando o FCA (valores mobiliários)."""
    ticker = ticker.upper().replace(".SA", "")
    ano = ano or dt.date.today().year
    for a in (ano, ano - 1, ano - 2):
        url = f"{CVM_BASE}/DOC/FCA/DADOS/fca_cia_aberta_{a}.zip"
        try:
            dados = _baixar_binario(url, f"fca_{a}.zip", max_idade_h=24 * 7)
        except FonteIndisponivel:
            continue
        z = zipfile.ZipFile(io.BytesIO(dados))
        arq = next((n for n in z.namelist() if "valor_mobiliario" in n), None)
        if not arq:
            continue
        df = _ler_csv_zip(z, arq)
        col = next((c for c in df.columns if c.lower() == "codigo_negociacao"), None)
        if col is None:
            continue
        hit = df[df[col].str.upper() == ticker]
        if hit.empty:
            continue
        row = hit.iloc[-1]
        PROV.add("CVM — FCA (valores mobiliários)", url, f"Ticker {ticker} resolvido")
        cnpj = row.get("CNPJ_Companhia") or row.get("CNPJ_CIA")
        nome = row.get("Nome_Empresarial") or row.get("DENOM_CIA") or ""
        return {"ticker": ticker, "cnpj": cnpj, "nome": nome,
                "mercado": row.get("Mercado", ""), "segmento": row.get("Segmento", "")}
    raise FonteIndisponivel(f"Ticker {ticker} não encontrado no FCA da CVM; informe --cnpj manualmente.")


def cvm_cadastro(cnpj: str) -> dict:
    url = f"{CVM_BASE}/CAD/DADOS/cad_cia_aberta.csv"
    dados = _baixar_binario(url, "cad_cia_aberta.csv", max_idade_h=24 * 7)
    df = pd.read_csv(io.BytesIO(dados), sep=";", encoding="latin-1", dtype=str)
    hit = df[df["CNPJ_CIA"] == cnpj]
    if hit.empty:
        raise FonteIndisponivel(f"CNPJ {cnpj} não está no cadastro da CVM")
    PROV.add("CVM — Cadastro de companhias abertas", url)
    return hit.iloc[-1].dropna().to_dict()


def cvm_demonstracoes(cnpj: str, anos: list[int], tipo: str = "DFP", consolidado: bool = True) -> pd.DataFrame:
    """Baixa BPA, BPP, DRE e DFC (MI ou MD) de DFP/ITR para os anos pedidos.

    Retorna DataFrame longo com colunas: demonstracao, DT_REFER, DT_INI_EXERC,
    DT_FIM_EXERC, ORDEM_EXERC, CD_CONTA, DS_CONTA, VL_CONTA (em R$ unidades).
    """
    tipo = tipo.upper()
    sufixo = "con" if consolidado else "ind"
    frames = []
    for ano in anos:
        url = f"{CVM_BASE}/DOC/{tipo}/DADOS/{tipo.lower()}_cia_aberta_{ano}.zip"
        try:
            dados = _baixar_binario(url, f"{tipo.lower()}_{ano}.zip", max_idade_h=24)
        except FonteIndisponivel:
            continue
        z = zipfile.ZipFile(io.BytesIO(dados))
        for dem in ("BPA", "BPP", "DRE", "DFC_MI", "DFC_MD"):
            nome = f"{tipo.lower()}_cia_aberta_{dem}_{sufixo}_{ano}.csv"
            if nome not in z.namelist():
                continue
            df = _ler_csv_zip(z, nome)
            df = df[df["CNPJ_CIA"] == cnpj]
            if df.empty:
                continue
            # usa somente a versão mais recente de cada documento (reapresentações)
            df["VERSAO"] = df["VERSAO"].astype(int)
            df = df[df["VERSAO"] == df.groupby("DT_REFER")["VERSAO"].transform("max")]
            df["demonstracao"] = "DFC" if dem.startswith("DFC") else dem
            frames.append(df)
        PROV.add(f"CVM — {tipo} {ano} ({'consolidado' if consolidado else 'individual'})", url)
    if not frames:
        raise FonteIndisponivel(f"Nenhuma demonstração {tipo} encontrada para {cnpj} em {anos}")
    df = pd.concat(frames, ignore_index=True)
    escala = df["ESCALA_MOEDA"].map({"MIL": 1_000, "UNIDADE": 1}).fillna(1)
    df["VL_CONTA"] = pd.to_numeric(df["VL_CONTA"], errors="coerce") * escala
    cols = ["demonstracao", "DT_REFER", "DT_INI_EXERC", "DT_FIM_EXERC", "ORDEM_EXERC",
            "CD_CONTA", "DS_CONTA", "VL_CONTA", "DENOM_CIA"]
    return df[[c for c in cols if c in df.columns]]


def cvm_fre_acoes(cnpj: str, ano: int | None = None) -> dict | None:
    """Tenta obter quantidade de ações (ON/PN/total) no FRE — capital social."""
    ano = ano or dt.date.today().year
    for a in (ano, ano - 1):
        url = f"{CVM_BASE}/DOC/FRE/DADOS/fre_cia_aberta_{a}.zip"
        try:
            dados = _baixar_binario(url, f"fre_{a}.zip", max_idade_h=24 * 7)
        except FonteIndisponivel:
            continue
        z = zipfile.ZipFile(io.BytesIO(dados))
        arq = next((n for n in z.namelist() if n.endswith(f"capital_social_{a}.csv")), None)
        if not arq:
            continue
        df = _ler_csv_zip(z, arq)
        ccol = next((c for c in df.columns if c.upper().startswith("CNPJ")), None)
        df = df[df[ccol] == cnpj] if ccol else df.iloc[0:0]
        if df.empty:
            continue
        tcol = next((c for c in df.columns if "Tipo_Capital" in c), None)
        if tcol:
            integ = df[df[tcol].str.contains("Integralizado", case=False, na=False)]
            df = integ if not integ.empty else df
        row = df.iloc[-1]
        def num(chave):
            c = next((c for c in df.columns if chave.lower() in c.lower()), None)
            return float(row[c]) if c and pd.notna(row[c]) else None
        PROV.add("CVM — FRE (capital social)", url)
        return {"ordinarias": num("Quantidade_Acoes_Ordinarias"),
                "preferenciais": num("Quantidade_Acoes_Preferenciais"),
                "total": num("Quantidade_Total_Acoes"),
                "data_referencia": row.get("Data_Referencia")}
    return None


# ---------------------------------------------------------------- Banco Central
def bcb_sgs(serie: str | int, inicio: dt.date, fim: dt.date | None = None) -> pd.Series:
    """Série temporal do SGS/BCB. Janelas >10 anos são divididas (limite da API)."""
    codigo = SGS.get(serie, serie) if isinstance(serie, str) else serie
    fim = fim or dt.date.today()
    partes = []
    a = inicio
    while a <= fim:
        b = min(fim, a.replace(year=a.year + 9))
        params = {"formato": "json", "dataInicial": a.strftime("%d/%m/%Y"), "dataFinal": b.strftime("%d/%m/%Y")}
        url = SGS_URL.format(codigo=codigo)
        try:
            js = _get(url, params, tentativas=2).json()
        except FonteIndisponivel:
            # a API às vezes devolve 304/vazio para certas janelas; sem dataFinal costuma funcionar
            params.pop("dataFinal")
            js = [x for x in _get(url, params).json()
                  if dt.datetime.strptime(x["data"], "%d/%m/%Y").date() <= b]
        partes.extend(js)
        a = b + dt.timedelta(days=1)
    if not partes:
        raise FonteIndisponivel(f"SGS {codigo} sem dados")
    df = pd.DataFrame(partes)
    s = pd.Series(pd.to_numeric(df["valor"], errors="coerce").values,
                  index=pd.to_datetime(df["data"], dayfirst=True), name=str(serie))
    PROV.add(f"Banco Central — SGS {codigo} ({serie})", SGS_URL.format(codigo=codigo),
             f"{inicio:%d/%m/%Y} a {fim:%d/%m/%Y}")
    s = s[s.index <= pd.Timestamp(dt.date.today())]  # séries como a 432 trazem datas futuras
    return s[~s.index.duplicated()].sort_index()


def bcb_focus(indicador: str = "IPCA", n: int = 40) -> pd.DataFrame:
    """Expectativas anuais do Boletim Focus (mediana) para um indicador."""
    from urllib.parse import quote
    filtro = quote(f"Indicador eq '{indicador}' and baseCalculo eq 0")
    url = f"{FOCUS_URL}?$top={n}&$format=json&$orderby=Data%20desc&$filter={filtro}"
    js = _get(url).json()  # OData exige %20, não '+', nos espaços
    df = pd.DataFrame(js.get("value", []))
    if df.empty:
        raise FonteIndisponivel(f"Focus sem dados para {indicador}")
    PROV.add(f"Banco Central — Focus ({indicador})", FOCUS_URL)
    df = df[df["Data"] == df["Data"].max()]
    return df[["Data", "DataReferencia", "Mediana", "Media", "Minimo", "Maximo", "numeroRespondentes"]]


# ---------------------------------------------------------------- Preços
def precos(simbolos: list[str], anos: int = 5) -> pd.DataFrame:
    """Preços ajustados: tenta Yahoo (rápido) e, se falhar, usa a B3 oficial (COTAHIST).

    Na B3 não há o índice Ibovespa: '^BVSP' é aproximado pelo ETF BOVA11 (registrado
    na proveniência).
    """
    try:
        return _precos_yahoo(simbolos, anos)
    except FonteIndisponivel as e:
        import b3
        mapa = {s: ("BOVA11" if s.upper() == "^BVSP" else s.upper().replace(".SA", "")) for s in simbolos}
        df = b3.precos_ajustados(sorted(set(mapa.values())), anos)
        out = pd.DataFrame({s.upper(): df[t] for s, t in mapa.items() if t in df})
        PROV.add("B3 — preços (fallback)", b3.COTAHIST_URL.format(ano="<ANO>"),
                 f"Yahoo indisponível ({str(e)[:60]}); ^BVSP aproximado por BOVA11")
        saltos = {k: v for k, v in b3.checar_saltos(out).items() if v}
        if saltos:
            PROV.add("B3 — ALERTA", "", f"Saltos >35% possivelmente não ajustados: {saltos}")
        return out


def _precos_yahoo(simbolos: list[str], anos: int = 5) -> pd.DataFrame:
    """Preços de fechamento ajustados (proventos/desdobramentos) via Yahoo Finance.

    Tickers da B3 recebem sufixo .SA automaticamente; '^BVSP' = Ibovespa.
    """
    series = {}
    for s in simbolos:
        sym = s if (s.startswith("^") or "." in s) else f"{s.upper()}.SA"
        url = YAHOO_URL.format(simbolo=sym)
        js = _get(url, {"range": f"{anos}y", "interval": "1d", "includeAdjustedClose": "true"}, tentativas=1).json()
        res = (js.get("chart") or {}).get("result")
        if not res:
            raise FonteIndisponivel(f"Sem preços para {sym}: {js.get('chart', {}).get('error')}")
        r = res[0]
        ind = r["indicators"]
        valores = (ind.get("adjclose") or [{}])[0].get("adjclose") or ind["quote"][0]["close"]
        idx = pd.to_datetime(r["timestamp"], unit="s").normalize()
        series[s.upper()] = pd.Series(valores, index=idx, dtype=float)
        PROV.add("Yahoo Finance — preços ajustados", url, sym)
    df = pd.DataFrame(series).sort_index()
    return df[~df.index.duplicated()].dropna(how="all")


def cotacao_atual(ticker: str) -> dict:
    """Cotação: Yahoo (intradiária, ~15 min de atraso) ou, se falhar, último fechamento oficial B3."""
    try:
        return _cotacao_yahoo(ticker)
    except FonteIndisponivel:
        import b3
        return b3.ultimo_fechamento(ticker)


def _cotacao_yahoo(ticker: str) -> dict:
    sym = ticker if "." in ticker or ticker.startswith("^") else f"{ticker.upper()}.SA"
    url = YAHOO_URL.format(simbolo=sym)
    js = _get(url, {"range": "5d", "interval": "1d"}, tentativas=1).json()
    meta = js["chart"]["result"][0]["meta"]
    PROV.add("Yahoo Finance — cotação", url, sym)
    ts = meta.get("regularMarketTime")
    return {"preco": meta.get("regularMarketPrice"), "moeda": meta.get("currency"),
            "horario": dt.datetime.fromtimestamp(ts).isoformat() if ts else None,
            "atraso_aviso": "Cotação pode ter atraso de ~15 min; confirme na B3."}


# ---------------------------------------------------------------- Tesouro, Damodaran, Crossref
TESOURO_CSV = ("https://www.tesourotransparente.gov.br/ckan/dataset/df56aa42-484a-4a59-8184-7676580c81e3/"
               "resource/796d2059-14e9-44e3-80c9-2d9e30b405c1/download/precotaxatesourodireto.csv")
DAMODARAN_ERP = "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/ctryprem.html"
DAMODARAN_BETAS = "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/Betas.html"


def tesouro_curva() -> pd.DataFrame:
    """Taxas do Tesouro Direto no último dia disponível (Tesouro Transparente, oficial)."""
    dados = _baixar_binario(TESOURO_CSV, "tesouro_taxas.csv", max_idade_h=12)
    d = pd.read_csv(io.BytesIO(dados), sep=";", decimal=",")
    d["Data Base"] = pd.to_datetime(d["Data Base"], dayfirst=True)
    d["Data Vencimento"] = pd.to_datetime(d["Data Vencimento"], dayfirst=True)
    u = d[d["Data Base"] == d["Data Base"].max()].copy()
    u["anos"] = (u["Data Vencimento"] - u["Data Base"]).dt.days / 365.25
    PROV.add("Tesouro Transparente — taxas do Tesouro Direto", TESOURO_CSV, f"data-base {u['Data Base'].max():%d/%m/%Y}")
    return u[["Tipo Titulo", "Data Vencimento", "Data Base", "anos", "Taxa Compra Manha"]].sort_values(["Tipo Titulo", "anos"])


def rf_longo(prazo_anos: float = 10) -> dict:
    """Taxa livre de risco nominal em R$: prefixado com juros semestrais (NTN-F) mais próximo do prazo."""
    c = tesouro_curva()
    pre = c[c["Tipo Titulo"].str.contains("Prefixado com Juros", case=False)]
    if pre.empty:
        pre = c[c["Tipo Titulo"].str.contains("Prefixado", case=False)]
    r = pre.iloc[(pre["anos"] - prazo_anos).abs().argsort().iloc[0]]
    ipca = c[c["Tipo Titulo"].str.fullmatch("Tesouro IPCA\\+ com Juros Semestrais", case=False)]
    real = ipca.iloc[(ipca["anos"] - prazo_anos).abs().argsort().iloc[0]] if not ipca.empty else None
    return {"rf": float(r["Taxa Compra Manha"]) / 100, "titulo": r["Tipo Titulo"],
            "vencimento": str(r["Data Vencimento"].date()), "data_base": str(r["Data Base"].date()),
            "juro_real_ipca": float(real["Taxa Compra Manha"]) / 100 if real is not None else None}


def _html_texto(url: str, nome: str) -> str:
    import html as _h
    import re as _re
    t = _baixar_binario(url, nome, max_idade_h=24 * 7).decode("latin-1")
    return _h.unescape(_re.sub(r"\s+", " ", _re.sub(r"<[^>]+>", " ", t)))


def damodaran_erp(pais: str = "Brazil") -> dict:
    """Prêmio de risco (Damodaran): spread de default, CRP e ERP total do país + ERP maduro."""
    import re as _re
    t = _html_texto(DAMODARAN_ERP, "damodaran_ctryprem.html")
    m = _re.search(_re.escape(pais) + r" (\S+) ([\d.]+)% ([\d.]+)% ([\d.]+)%", t)
    if not m:
        raise FonteIndisponivel(f"{pais} não encontrado na tabela de Damodaran")
    data = _re.search(r"Last updated: ([A-Za-z]+ \d+, \d{4})", t)
    spread, crp, total = (float(m.group(i)) / 100 for i in (2, 3, 4))
    PROV.add("Damodaran — Country Risk Premiums", DAMODARAN_ERP, data.group(1) if data else "")
    return {"rating": m.group(1), "spread_default": spread, "crp": crp, "erp_total": total,
            "erp_maduro": round(total - crp, 4), "atualizado": data.group(1) if data else None}


def damodaran_beta_setor(setor: str) -> dict | None:
    """Beta setorial (EUA) de Damodaran, ex.: 'Bank (Money Center)'. Referência, não substitui regressão local."""
    import re as _re
    t = _html_texto(DAMODARAN_BETAS, "damodaran_betas.html")
    m = _re.search(_re.escape(setor) + r" (\d+) ([\d.]+) ([\d.]+)% ([\d.]+)% ([\d.]+)", t)
    if not m:
        return None
    PROV.add("Damodaran — Betas by Sector (EUA)", DAMODARAN_BETAS, setor)
    return {"setor": setor, "empresas": int(m.group(1)), "beta": float(m.group(2)),
            "de": float(m.group(3)) / 100, "beta_desalavancado": float(m.group(5))}


def crossref(doi: str) -> dict:
    """Confere um DOI na Crossref (título, autor, ano, periódico)."""
    js = _get(f"https://api.crossref.org/works/{doi}", tentativas=2).json()["message"]
    autores = js.get("author") or [{}]
    return {"doi": doi, "titulo": (js.get("title") or [""])[0], "autor": autores[0].get("family"),
            "ano": (js.get("issued", {}).get("date-parts") or [[None]])[0][0],
            "periodico": (js.get("container-title") or [""])[0]}


if __name__ == "__main__":  # diagnóstico rápido de conectividade
    for nome, f in [("BCB SGS", lambda: bcb_sgs("selic_meta", dt.date.today() - dt.timedelta(days=10))),
                    ("Cotação (Yahoo→B3)", lambda: cotacao_atual("PETR4")),
                    ("Tesouro", rf_longo), ("Damodaran", damodaran_erp),
                    ("Crossref", lambda: crossref("10.2307/1927792")),
                    ("CVM cadastro", lambda: _get(f"{CVM_BASE}/CAD/DADOS/cad_cia_aberta.csv", timeout=30))]:
        try:
            f(); print(f"[ok]   {nome}")
        except Exception as e:
            print(f"[erro] {nome}: {e}")
    print(json.dumps(PROV.to_list(), ensure_ascii=False, indent=2))
