#!/usr/bin/env python3
"""Orquestrador: coleta dados em tempo real e gera o relatório quantitativo.

Exemplo:
  python analisar.py --ticker WEGE3 --anos 8 \
      --carteira "ITUB4:0.25,PETR4:0.20,BOVA11:0.35,TAEE11:0.20" \
      --pares "EMBR3,RAIL3" --horizonte 5 --objetivo crescimento \
      --premissas premissas_WEGE3.json

Saída: relatorios/<TICKER>_<AAAA-MM-DD>/
  relatorio_quantitativo.md  — base numérica rotulada (DADO OBSERVADO / ESTIMATIVA / PREMISSA)
  dados.json                 — tudo em formato máquina + proveniência + lacunas
  *.csv                      — tabelas (demonstrações, indicadores, correlação etc.)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bancos as bk  # noqa: E402
import carteira as ct  # noqa: E402
import fontes as fx  # noqa: E402
import fundamentos as fd  # noqa: E402
import memoria as mem  # noqa: E402
import valuation as vl  # noqa: E402

PCT = {"crescimento_receita", "margem_bruta", "margem_ebit", "margem_ebitda", "margem_liquida", "roe", "roa",
       "roic", "aliquota_efetiva", "accruals_sobre_ativo", "payout_caixa", "reinvestimento_sobre_nopat",
       "retorno_anualizado", "volatilidade_anualizada", "drawdown_maximo", "dividend_yield_caixa",
       "contribuicao_risco_novo_pct", "contribuicao_pct", "peso", "crescimento_terminal", "ke", "wacc", "peso_valor_terminal",
       "margem_seguranca", "variacao_vs_preco", "payout", "g", "pdd_sobre_margem", "indice_eficiencia",
       "margem_sobre_ativos", "crescimento_lucro"}


def fmt(v, chave: str = "") -> str:
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return "n/d"
    if isinstance(v, (bool, np.bool_)):
        return str(v)
    if isinstance(v, (int, np.integer)) and chave not in PCT:
        return str(int(v)) if chave in ("ano_base", "observacoes") else f"{int(v):,}".replace(",", ".")
    if isinstance(v, (int, float, np.floating, np.integer)):
        v = float(v)
        if chave in PCT or chave.startswith("roe"):
            return f"{v:.1%}".replace(".", ",")
        if abs(v) >= 1e9:
            return f"{v / 1e9:,.2f} bi".replace(",", "X").replace(".", ",").replace("X", ".")
        if abs(v) >= 1e6:
            return f"{v / 1e6:,.1f} mi".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return str(v)


def tabela_md(df: pd.DataFrame, pct_linhas: bool = True) -> str:
    cols = [str(c) for c in df.columns]
    linhas = ["| | " + " | ".join(cols) + " |", "|---" * (len(cols) + 1) + "|"]
    for idx, row in df.iterrows():
        linhas.append(f"| {idx} | " + " | ".join(
            fmt(v, str(idx) if pct_linhas else str(c)) for c, v in zip(df.columns, row.values)) + " |")
    return "\n".join(linhas)


def parse_carteira(s: str | None) -> dict[str, float]:
    if not s:
        return {}
    out = {}
    for item in s.split(","):
        a, w = item.split(":")
        out[a.strip().upper()] = float(w)
    return out


class Coletor:
    def __init__(self):
        self.dados: dict = {}
        self.lacunas: list[str] = []

    def etapa(self, nome: str, func, *a, **k):
        try:
            r = func(*a, **k)
            return r
        except Exception as e:
            self.lacunas.append(f"{nome}: {type(e).__name__}: {e}")
            if "--debug" in sys.argv:
                traceback.print_exc()
            return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--cnpj", help="Força o CNPJ (formato 00.000.000/0000-00) se o ticker não for resolvido")
    ap.add_argument("--anos", type=int, default=8, help="Anos de histórico das DFPs")
    ap.add_argument("--carteira", help='Ex.: "ITUB4:0.3,BOVA11:0.7" (pesos normalizados). '
                    'Se omitido, usa dados/carteira.csv (memória do investidor), pesando por valor de mercado.')
    ap.add_argument("--sem-memoria", action="store_true", help="Ignora dados/carteira.csv")
    ap.add_argument("--pares", help="Concorrentes, ex.: EMBR3,RAIL3")
    ap.add_argument("--horizonte", type=int, default=5)
    ap.add_argument("--objetivo", default="equilibrio", choices=["crescimento", "dividendos", "equilibrio"])
    ap.add_argument("--premissas", help="JSON de premissas do DCF (ver references/premissas_exemplo.json)")
    ap.add_argument("--acoes", type=float, help="Quantidade de ações (ex-tesouraria) se FRE indisponível")
    ap.add_argument("--preco", type=float, help="Preço atual se a cotação automática falhar (citar a fonte)")
    ap.add_argument("--preco-data", help="Data/hora e fonte do --preco")
    ap.add_argument("--anos-precos", type=int, default=5)
    ap.add_argument("--saida", default="relatorios")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    hoje = dt.date.today()
    tk = args.ticker.upper()
    out = Path(args.saida) / f"{tk}_{hoje:%Y-%m-%d}"
    out.mkdir(parents=True, exist_ok=True)
    C = Coletor()
    md: list[str] = []
    w = md.append

    # ---------------- 1. Identificação
    emp = {"ticker": tk, "cnpj": args.cnpj} if args.cnpj else C.etapa("Resolver ticker (CVM/FCA)", fx.cvm_ticker_para_empresa, tk)
    cad = C.etapa("Cadastro CVM", fx.cvm_cadastro, emp["cnpj"]) if emp else None
    cot = C.etapa("Cotação atual", fx.cotacao_atual, tk)
    if cot is None and args.preco:
        cot = {"preco": args.preco, "moeda": "BRL", "horario": args.preco_data or "informado pelo analista",
               "atraso_aviso": "preço informado manualmente via --preco (citar a fonte no relatório)"}
    C.dados.update(empresa=emp, cadastro=cad, cotacao=cot)

    w(f"# Base quantitativa — {tk}\n")
    w(f"*Gerado em {dt.datetime.now():%d/%m/%Y %H:%M} por scripts/analisar.py. "
      "Este arquivo é a BASE NUMÉRICA do relatório; a interpretação é feita na etapa de redação.*\n")
    w("Legenda: **[DADO OBSERVADO]** extraído de fonte primária · **[ESTIMATIVA]** cálculo estatístico "
      "sobre dados observados · **[PREMISSA]** hipótese informada pelo analista.\n")
    w("## 1. Identificação [DADO OBSERVADO]\n")
    if emp:
        w(f"- Empresa: {emp.get('nome') or (cad or {}).get('DENOM_SOCIAL', 'n/d')}")
        w(f"- CNPJ: {emp.get('cnpj')}")
    if cad:
        for k in ("DENOM_COMERC", "SETOR_ATIV", "SIT", "DT_REG", "CATEG_REG", "CONTROLE_ACIONARIO", "AUDITOR", "MUN", "UF"):
            if k in cad:
                w(f"- {k}: {cad[k]}")
    if cot:
        w(f"- Preço: R$ {fmt(cot['preco'])} em {cot['horario']} ({cot['atraso_aviso']})")
    w("")

    # ---------------- 2. Demonstrações
    anos = list(range(hoje.year - args.anos, hoje.year + 1))
    tab = ind = ben = itr = None
    ltm = None
    financeira = False
    if emp:
        dfp = C.etapa("DFP (CVM)", fx.cvm_demonstracoes, emp["cnpj"], anos, "DFP", True)
        if dfp is not None:
            financeira = fd.eh_financeira(dfp)
            dfp.to_csv(out / "dfp_bruto.csv", index=False)
            tab = fd.tabela_anual(dfp)
            tab.to_csv(out / "demonstracoes_padronizadas.csv")
            if not financeira:
                ind = fd.indicadores(tab)
                ind.to_csv(out / "indicadores.csv")
                ben = fd.beneish(tab)
                ben.to_csv(out / "beneish.csv")
        itr = C.etapa("ITR mais recente (CVM)", fx.cvm_demonstracoes, emp["cnpj"], [hoje.year], "ITR", True)
        if itr is not None:
            itr.to_csv(out / "itr_bruto.csv", index=False)
            C.dados["ultimo_itr"] = str(itr["DT_REFER"].max())

    w("## 2. Demonstrações financeiras (DFP consolidada, R$) [DADO OBSERVADO]\n")
    if financeira and dfp is not None:
        w("> **Instituição financeira detectada.** Usado o módulo bancário (scripts/bancos.py): ROE, ROA, "
          "alavancagem, custo do risco, eficiência, payout. Basileia e inadimplência vêm do release/Pilar 3. "
          "As DFs da CVM são IFRS; o lucro 'ajustado' divulgado pelo banco (BR GAAP/COSIF) pode diferir.\n")
        tab = bk.tabela_anual_banco(dfp)
        tab.to_csv(out / "demonstracoes_padronizadas.csv")
        ind_b = bk.indicadores_banco(tab)
        ind_b.to_csv(out / "indicadores_banco.csv")
        ltm = C.etapa("LTM (DFP + ITR)", bk.ltm_banco, tab, itr)
        C.dados["ltm"] = ltm
        w(tabela_md(tab, pct_linhas=False))
        w("\n## 3. Indicadores bancários [ESTIMATIVA sobre DADO OBSERVADO]\n")
        w(tabela_md(ind_b.T))
        if ltm:
            w(f"\n### Últimos 12 meses até {ltm['data_referencia']} [ESTIMATIVA: DFP + ITR acumulado − ITR do ano anterior]\n")
            for k, v in ltm.items():
                w(f"- {k}: {fmt(v, k)}")
            roe_ltm = ltm.get("lucro_controladores", np.nan) / ltm.get("pl_controlador", np.nan)
            w(f"- ROE LTM (sobre PL final): {fmt(roe_ltm, 'roe')}")
        w("")
        tab = None  # evita a tabela de empresas não financeiras abaixo
    if tab is not None:
        w(f"Defasagem: último exercício anual = {tab.columns.max()}; último ITR = {C.dados.get('ultimo_itr', 'n/d')}.\n")
        w(tabela_md(tab.loc[[r for r in tab.index if tab.loc[r].notna().any()]], pct_linhas=False))
        w("")
    if ind is not None:
        w("## 3. Indicadores fundamentalistas [ESTIMATIVA sobre DADO OBSERVADO]\n")
        w(tabela_md(ind.T))
        w("")
        cg = {k: fd.cagr(ind[k]) for k in ("receita_liquida", "lucro_controladores", "ebitda", "fco")}
        C.dados["cagr"] = cg
        w("CAGR = (Valor final / Valor inicial)^(1/n) − 1: " +
          "; ".join(f"{k}: {fmt(v, 'crescimento_receita')}" for k, v in cg.items()) + "\n")
        w("Médias do período (base para premissas — NÃO são premissas): " + "; ".join(
            f"{k} {fmt(ind[k].mean(), k)} (dp {fmt(ind[k].std(), k)})"
            for k in ("crescimento_receita", "margem_ebit", "roic", "roe", "aliquota_efetiva")) + "\n")
    if ben is not None:
        w("## 4. Qualidade dos lucros — Beneish M-Score (triagem) [ESTIMATIVA]\n")
        w("Limiar −1,78 (modelo de 8 variáveis, Beneish 1999). Resultado acima do limiar = investigar, não prova de fraude.\n")
        w(tabela_md(ben.drop(columns=["sinal_triagem"]).T, pct_linhas=False))
        w("\nSinal por ano: " + "; ".join(f"{a}: {s}" for a, s in ben["sinal_triagem"].items()) + "\n")

    # ---------------- 3. Ações e múltiplos
    acoes = args.acoes
    if acoes is None and emp:
        fre = C.etapa("Quantidade de ações (FRE)", fx.cvm_fre_acoes, emp["cnpj"])
        C.dados["fre_acoes"] = fre
        acoes = (fre or {}).get("total")
    mult = None
    if ind is not None and cot and acoes:
        mult = C.etapa("Múltiplos", fd.multiplos, tab, ind, cot["preco"], acoes)
        if mult:
            w("## 5. Múltiplos de mercado [ESTIMATIVA: preço atual × último exercício]\n")
            for k, v in mult.items():
                if k != "observacoes":
                    w(f"- {k}: {fmt(v, k)}")
            for o in mult["observacoes"]:
                w(f"  - Obs.: {o}")
            w("")
    elif financeira and ltm and cot and acoes:
        div12 = abs(ltm["dividendos_pagos"]) if ltm.get("dividendos_pagos") else None
        mult = bk.multiplos_banco(ltm["lucro_controladores"], ltm["pl_controlador"], cot["preco"], acoes, div12)
        w("## 5. Múltiplos (preço atual × LTM) [ESTIMATIVA]\n")
        for k, v in mult.items():
            w(f"- {k}: {fmt(v, k)}")
        w("")
    elif ind is not None or financeira:
        C.lacunas.append("Múltiplos: preço ou quantidade de ações indisponível (use --preco / --acoes)")
    C.dados["multiplos"] = mult

    # ---------------- 4. Pares
    pares = [p.strip().upper() for p in (args.pares or "").split(",") if p.strip()]
    comp = {}
    for p in pares:
        def _par_banco(p=p):
            e = fx.cvm_ticker_para_empresa(p)
            d = fx.cvm_demonstracoes(e["cnpj"], anos[-5:], "DFP", True)
            t = bk.tabela_anual_banco(d)
            i = bk.indicadores_banco(t)
            itr_p = fx.cvm_demonstracoes(e["cnpj"], [hoje.year], "ITR", True)
            lt = bk.ltm_banco(t, itr_p) or {}
            r = {f"roe_{a}": i.loc[a, "roe"] for a in i.index[-3:]}
            r["roe"] = lt.get("lucro_controladores", np.nan) / lt.get("pl_controlador", np.nan)
            r["alavancagem_ativo_pl"] = lt.get("ativo_total", np.nan) / lt.get("pl_total", np.nan)
            r["lucro_ltm"] = lt.get("lucro_controladores")
            fre = fx.cvm_fre_acoes(e["cnpj"])
            if p.endswith("11"):
                r["obs"] = "unit: múltiplos não calculados (composição da unit varia)"
            elif fre and fre.get("total") and lt:
                q = fx.cotacao_atual(p)
                m = bk.multiplos_banco(lt["lucro_controladores"], lt["pl_controlador"], q["preco"], fre["total"], None)
                r.update(p_vp=m["p_vp"], p_l=m["p_l_ltm"],
                         obs="preço da classe × total de ações (aprox. se ON e PN têm preços diferentes)")
            return r

        def _par(p=p):
            if financeira:
                return _par_banco(p)
            e = fx.cvm_ticker_para_empresa(p)
            d = fx.cvm_demonstracoes(e["cnpj"], anos[-4:], "DFP", True)
            i = fd.indicadores(fd.tabela_anual(d))
            ult = i.index.max()
            r = i.loc[ult, ["receita_liquida", "crescimento_receita", "margem_ebit", "margem_liquida", "roe",
                            "roic", "divida_liquida_ebitda", "fco_sobre_lucro"]].to_dict()
            r["ano"] = int(ult)
            fre = fx.cvm_fre_acoes(e["cnpj"])
            q = fx.cotacao_atual(p)
            if fre and fre.get("total"):
                m = fd.multiplos(fd.tabela_anual(d), i, q["preco"], fre["total"])
                r.update({k: m[k] for k in ("p_l", "p_vp", "ev_ebitda", "dividend_yield_caixa")})
            return r
        r = C.etapa(f"Par {p}", _par)
        if r:
            comp[p] = r
    if comp:
        if financeira and ltm:
            comp = {tk: {"roe": ltm["lucro_controladores"] / ltm["pl_controlador"],
                         "alavancagem_ativo_pl": ltm["ativo_total"] / ltm["pl_total"],
                         "lucro_ltm": ltm["lucro_controladores"],
                         **({"p_vp": mult["p_vp"], "p_l": mult["p_l_ltm"]} if mult else {})}, **comp}
        elif ind is not None:
            ult = ind.index.max()
            base = ind.loc[ult, ["receita_liquida", "crescimento_receita", "margem_ebit", "margem_liquida", "roe",
                                 "roic", "divida_liquida_ebitda", "fco_sobre_lucro"]].to_dict()
            if mult:
                base.update({k: mult[k] for k in ("p_l", "p_vp", "ev_ebitda", "dividend_yield_caixa")})
            comp = {tk: base, **comp}
        dfc = pd.DataFrame(comp)
        dfc.to_csv(out / "comparacao_pares.csv")
        w("## 6. Comparação com concorrentes [ESTIMATIVA]\n")
        w(tabela_md(dfc))
        w("\n*Comparabilidade deve ser justificada qualitativamente (mix, ciclo, contabilidade).*\n")
    C.dados["pares"] = comp

    # ---------------- 5. Macro
    ini = hoje - dt.timedelta(days=365 * args.anos_precos + 30)
    macro = {}
    selic = C.etapa("Selic meta (SGS 432)", fx.bcb_sgs, "selic_meta", hoje - dt.timedelta(days=400))
    ipca = C.etapa("IPCA (SGS 433)", fx.bcb_sgs, "ipca_mensal", hoje - dt.timedelta(days=800))
    ptax = C.etapa("PTAX (SGS 1)", fx.bcb_sgs, "ptax_venda", hoje - dt.timedelta(days=400))
    cdi = C.etapa("CDI diário (SGS 12)", fx.bcb_sgs, "cdi_diario", ini)
    focus = {k: C.etapa(f"Focus {k}", fx.bcb_focus, k) for k in ("IPCA", "Selic", "PIB Total", "Câmbio")}
    if selic is not None:
        macro["selic_meta_atual"] = float(selic.iloc[-1]) / 100
        macro["selic_data"] = str(selic.index[-1].date())
    if ipca is not None:
        macro["ipca_12m"] = float(np.prod(1 + ipca.iloc[-12:] / 100) - 1)
        macro["ipca_ultimo_mes"] = str(ipca.index[-1].date())
    if ptax is not None:
        macro["ptax"] = float(ptax.iloc[-1])
        macro["ptax_var_12m"] = float(ptax.iloc[-1] / ptax.iloc[0] - 1)
    if cdi is not None:
        macro["cdi_12m"] = float(np.prod(1 + cdi.iloc[-252:] / 100) - 1)
    for k, f in focus.items():
        if f is not None:
            macro[f"focus_{k}"] = f[["DataReferencia", "Mediana"]].sort_values("DataReferencia").head(4).to_dict("records")
            macro["focus_data"] = str(f["Data"].iloc[0])
    C.dados["macro"] = macro
    w("## 7. Macroeconomia [DADO OBSERVADO — BCB/SGS e Focus]\n")
    for k, v in macro.items():
        w(f"- {k}: {fmt(v, 'roe') if k in ('selic_meta_atual', 'ipca_12m', 'ptax_var_12m', 'cdi_12m') else v}")
    w("")

    # ---------------- 6. Mercado e Markowitz
    pesos = parse_carteira(args.carteira)
    origem_carteira = "informada em --carteira" if pesos else None
    da_memoria: list[str] = []
    if not pesos and not args.sem_memoria:
        linhas_mem, data_mem = mem.ler_carteira()
        da_memoria = [r["ativo"] for r in linhas_mem if r["cotas_num"]
                      and "exclu" not in r.get("status", "").lower()
                      and not any(s in r.get("classe", "").lower() for s in mem.SEM_COTACAO)]
        C.dados["carteira_memoria"] = {"data_registro": data_mem, "ativos": da_memoria}
    simbolos = sorted(set([tk, "^BVSP"] + list(pesos) + da_memoria + pares))
    px = C.etapa("Preços históricos (Yahoo)", fx.precos, simbolos, args.anos_precos)
    if da_memoria:
        ultimos = px.ffill().iloc[-1].dropna().to_dict() if px is not None else {}
        pesos, avisos_mem = mem.pesos_por_valor(ultimos)
        C.lacunas.extend(f"Carteira (memória): {a}" for a in avisos_mem)
        origem_carteira = (f"dados/carteira.csv, registro de {C.dados['carteira_memoria']['data_registro'] or 'data desconhecida'}, "
                           "pesos por valor de mercado (cotas × último fechamento)")
    C.dados["carteira_usada"] = {"origem": origem_carteira, "pesos": pesos}
    rf_anual = macro.get("cdi_12m") or macro.get("selic_meta_atual")
    est = None
    if px is not None:
        px.to_csv(out / "precos.csv")
        R = ct.retornos(px)
        bench = R.get("^BVSP")
        rf_d = ct.rf_diario_de_cdi(cdi, R.index) if cdi is not None else 0.0
        if cdi is None:
            C.lacunas.append("Sharpe/Sortino calculados com Rf=0 (CDI indisponível)")
        est = C.etapa("Estatísticas do ativo", ct.estatisticas, R[tk], rf_d, bench) if tk in R else None
        C.dados["estatisticas_ativo"] = est
        w("## 8. Risco de mercado do ativo [ESTIMATIVA histórica]\n")
        if est:
            for k, v in est.items():
                w(f"- {k}: {fmt(v, k)}")
            if bench is not None:
                br = ct.beta_rolante(R[tk], bench)
                if len(br):
                    w(f"- beta rolante 252d: mín {br.min():.2f} · mediana {br.median():.2f} · máx {br.max():.2f} · atual {br.iloc[-1]:.2f}")
            w("")
        if pesos:
            ativos = [a for a in pesos if a in R]
            faltam = [a for a in pesos if a not in R]
            if faltam:
                C.lacunas.append(f"Sem preços para {faltam}; removidos da carteira")
            cols = sorted(set(ativos + [tk]))
            Rc = R[cols].dropna()
            corr = Rc.corr()
            corr.to_csv(out / "correlacao.csv")
            (Rc.cov() * ct.DU).to_csv(out / "covariancia_anual.csv")
            comp_c = C.etapa("Markowitz — inclusão", ct.comparar_inclusao, Rc, {a: pesos[a] for a in ativos}, tk, rf_d, bench)
            fr = C.etapa("Fronteira Monte Carlo", ct.fronteira_monte_carlo, Rc, rf_anual or 0.0)
            estab = C.etapa("Estabilidade dos pesos (bootstrap)", ct.estabilidade_pesos, Rc, rf_anual or 0.0, 100)
            w0 = np.array([pesos[a] for a in ativos]) / sum(pesos[a] for a in ativos)
            mc = C.etapa("Monte Carlo do patrimônio", ct.monte_carlo_patrimonio, Rc[ativos], w0, args.horizonte)
            w("## 9. Markowitz — efeito na carteira [ESTIMATIVA histórica]\n")
            w(f"Carteira: {origem_carteira}. Pesos: " + ", ".join(f"{a} {fmt(pesos[a], 'peso')}" for a in ativos) + "\n")
            w(f"Janela: {Rc.index.min().date()} a {Rc.index.max().date()} ({len(Rc)} pregões). "
              f"Rf = CDI acumulado 12m ({fmt(rf_anual, 'roe')}).\n")
            w("### Matriz de correlação\n")
            w(tabela_md(corr, pct_linhas=False))
            if comp_c:
                w("\n### A. Carteira original\n")
                for k in ("retorno_anualizado", "volatilidade_anualizada", "sharpe", "sortino", "drawdown_maximo",
                          "beta", "diversification_ratio", "n_efetivo_hhi"):
                    w(f"- {k}: {fmt(comp_c['A_original'].get(k), k)}")
                w("\nContribuição ao risco (A):\n")
                w(tabela_md(pd.DataFrame(comp_c["A_original"]["contribuicao_risco"]).T, pct_linhas=False))
                w(f"\n### B/C. Inclusão de {tk} com pesos diferentes\n")
                w(tabela_md(pd.DataFrame(comp_c["C_grade"]).T.rename(columns=lambda c: c), pct_linhas=False))
            if fr:
                w("### Fronteira eficiente (ilustrativa)\n")
                w(f"Método: {fr['metodo']}. Retorno esperado = média histórica (premissa fraca).\n")
                for k in ("minima_variancia", "max_sharpe"):
                    w(f"- {k}: " + ", ".join(f"{a} {p:.0%}" for a, p in fr[k]["pesos"].items())
                      + f" | ret {fr[k]['retorno']:.1%} | vol {fr[k]['vol']:.1%}")
                fr["pontos"].to_csv(out / "fronteira_pontos.csv", index=False)
            if estab is not None:
                w("\nInstabilidade dos pesos de máx. Sharpe (bootstrap, p5–p95):\n")
                w(tabela_md(estab[["5%", "50%", "95%"]], pct_linhas=False))
            if mc:
                w(f"\nMonte Carlo ({mc['horizonte_anos']} anos, carteira original): múltiplo do patrimônio "
                  f"p5/p25/p50/p75/p95 = {mc['multiplo_patrimonio_p5_p25_p50_p75_p95']}; "
                  f"P(perda nominal) = {mc['prob_perda_nominal']:.1%}. {mc['aviso']}\n")
            C.dados["markowitz"] = {"correlacao": corr.to_dict(), "comparacao": comp_c,
                                    "fronteira": {k: v for k, v in (fr or {}).items() if k != "pontos"},
                                    "monte_carlo": mc}
        else:
            C.lacunas.append("Carteira sem quantidades (nem --carteira, nem cotas em dados/carteira.csv): "
                             "Markowitz (seção 17) não executado")

    # ---------------- 7. Custo de capital (fontes vivas) e valuation
    w("## 10. Custo de capital [DADO + ESTIMATIVA]\n")
    rfl = C.etapa("Taxa livre de risco (Tesouro)", fx.rf_longo)
    erp = C.etapa("Prêmio de risco (Damodaran)", fx.damodaran_erp)
    beta_ref = C.etapa("Beta setorial (Damodaran)", fx.damodaran_beta_setor,
                       "Bank (Money Center)" if financeira else "Total Market (without financial s)")
    p = vl.carregar_premissas(args.premissas) if args.premissas else {}
    beta = p.get("beta")
    origem_beta = "premissa do analista (JSON)"
    if beta is None and est and est.get("beta_ajustado_blume") is not None:
        beta, origem_beta = est["beta_ajustado_blume"], "regressão contra BOVA11/Ibovespa, ajuste de Blume"
    ke_info = None
    if rfl:
        w(f"- Rf: {rfl['titulo']} venc. {rfl['vencimento']} = {rfl['rf']:.2%} a.a. (data-base {rfl['data_base']}); "
          f"juro real IPCA+ ≈ {fmt(rfl.get('juro_real_ipca'), 'roe')}")
    if erp:
        w(f"- Damodaran ({erp['atualizado']}): rating {erp['rating']}, spread de default {erp['spread_default']:.2%}, "
          f"CRP {erp['crp']:.2%}, ERP total {erp['erp_total']:.2%}, ERP maduro {erp['erp_maduro']:.2%}")
    if beta_ref:
        w(f"- Beta setorial de referência (EUA, Damodaran): {beta_ref['setor']} = {beta_ref['beta']:.2f}")
    if rfl and erp and beta is not None:
        ke_info = vl.ke_brasil(p.get("rf", rfl["rf"]), beta, erp["erp_total"], erp["spread_default"], erp["erp_maduro"])
        ke_info.update(beta=beta, origem_beta=origem_beta)
        w(f"- β usado: {beta:.2f} ({origem_beta})")
        w(f"- Ke método A (Rf − spread + β×ERP total): {ke_info['ke_metodo_a']:.2%} · "
          f"método B (Rf + β×ERP maduro): {ke_info['ke_metodo_b']:.2%} · **Ke base: {ke_info['ke_base']:.2%}**")
    else:
        C.lacunas.append("Ke não calculado: falta Rf, ERP ou beta")
    C.dados["custo_capital"] = {"rf": rfl, "erp": erp, "beta_setor": beta_ref, "ke": ke_info}
    w("")

    w("## 11. Valuation [PREMISSA + ESTIMATIVA]\n")
    if financeira and ltm and cot and acoes and p.get("cenarios_roe") and p.get("g") is not None and ke_info:
        vb = C.etapa("Valuation bancário (lucro residual)", vl.valuation_banco,
                     ltm["pl_controlador"] / acoes, cot["preco"], p.get("ke", ke_info["ke_base"]),
                     p["g"], p.get("payout", 0.3), p["cenarios_roe"])
        if vb:
            w(f"Lucro residual (Ohlson, 1995), 2 estágios. Ke {vb['ke']:.2%}, g {vb['g']:.1%}, payout {vb['payout']:.0%}, "
              f"VPA₀ R$ {vb['vpa0']:.2f}. Justificativas em `_fontes` do JSON.\n")
            w(tabela_md(pd.DataFrame(vb["cenarios"]), pct_linhas=True))
            w(f"\n- ROE sustentável implícito no preço: {vb['roe_implicito_2_estagios']:.1%} (2 estágios) · "
              f"{vb['roe_implicito_gordon']:.1%} (Gordon no P/VP)\n")
            w("### Sensibilidade Ke × ROE sustentável (R$/ação)\n")
            w(tabela_md(vb["sens_ke_roe"], pct_linhas=False))
            w("\n### Sensibilidade g × ROE sustentável (R$/ação)\n")
            w(tabela_md(vb["sens_g_roe"], pct_linhas=False))
            vb["sens_ke_roe"].to_csv(out / "sensibilidade_ke_roe.csv")
            vb["sens_g_roe"].to_csv(out / "sensibilidade_g_roe.csv")
            C.dados["valuation"] = {k: v for k, v in vb.items() if not k.startswith("sens")}
    elif financeira:
        w("**Não executado:** para bancos informe no JSON `cenarios_roe` "
          '({"pessimista":[roe1,roe_sust],"base":[...],"otimista":[...]}), `g` e `payout` (ver references/premissas_banco_exemplo.json).\n')
        C.lacunas.append("Valuation bancário não executado: premissas de ROE/g ausentes")
    elif args.premissas:
        if acoes and p.get("acoes") is None:
            p["acoes"] = acoes
        if ke_info and p.get("beta") is None:
            p.setdefault("rf", rfl["rf"]); p["beta"] = beta
            p.setdefault("premio_risco_mercado", erp["erp_maduro"])
        r = C.etapa("DCF (FCFF)", vl.dcf_fcff, p)
        if r:
            r["projecao"].to_csv(out / "dcf_projecao.csv", index=False)
            w("Premissas (fonte/justificativa no JSON):\n")
            w("```json\n" + json.dumps({k: v for k, v in p.items() if k != "cenarios"}, ensure_ascii=False, indent=1) + "\n```\n")
            for k in ("ke", "wacc", "crescimento_terminal", "vp_fluxos", "vp_valor_terminal", "peso_valor_terminal",
                      "enterprise_value", "equity_value", "valor_por_acao"):
                w(f"- {k}: {fmt(r[k], k)}")
            w("\n" + tabela_md(r["projecao"].set_index("ano").T, pct_linhas=False) + "\n")
            wv = r["wacc"]
            sens = vl.sensibilidade(p, "wacc_override", [wv - 0.02, wv - 0.01, wv, wv + 0.01, wv + 0.02],
                                    "crescimento_terminal", [p["crescimento_terminal"] + d for d in (-0.01, -0.005, 0, 0.005, 0.01)])
            sens.to_csv(out / "sensibilidade_wacc_g.csv")
            w("### Sensibilidade: WACC (linhas) × g terminal (colunas) — R$/ação\n")
            w(tabela_md(sens, pct_linhas=False))
            cen = C.etapa("Cenários", vl.cenarios, p)
            if cen:
                w("\n### Cenários\n")
                w(tabela_md(pd.DataFrame(cen), pct_linhas=False))
            if cot:
                ms = vl.margem_seguranca(r["valor_por_acao"], cot["preco"])
                w(f"\n- Margem de segurança (base): {ms:.1%} = (valor justo − preço) / valor justo")
                imp = vl.premissas_implicitas_no_preco(p, cot["preco"])
                w(f"- Reverse DCF: crescimento anual de receita implícito no preço = {fmt(imp, 'crescimento_receita')}")
            C.dados["valuation"] = {k: v for k, v in r.items() if k != "projecao"}
            C.dados["valuation"]["cenarios"] = cen
    else:
        w("**Não executado: premissas ausentes.** Crie o JSON de premissas (references/premissas_exemplo.json), "
          "com fonte para cada número, e rode novamente com --premissas.\n")
        C.lacunas.append("DCF não executado: arquivo de premissas não informado")

    # ---------------- 7b. Indicadores complementares e posição do investidor
    w("## 11b. Indicadores complementares [ESTIMATIVA: triagem, não valuation]\n")
    preco = (cot or {}).get("preco")
    lpa = (mult or {}).get("lpa") or (mult or {}).get("lpa_ltm")
    vpa = (mult or {}).get("vpa")
    dy = (mult or {}).get("dividend_yield_caixa")
    dpa = dy * preco if dy and preco else None
    selic_atual = macro.get("selic_meta_atual")
    comp_extra = {
        "earnings_yield": fd.earnings_yield(lpa, preco) if preco else None,
        "selic_meta": selic_atual,
        "numero_graham": fd.numero_graham(lpa, vpa),
        "dpa_12m_caixa": dpa,
        "preco_teto_bazin_6pct": fd.preco_teto_bazin(dpa, 0.06),
        "preco_teto_bazin_selic": fd.preco_teto_bazin(dpa, selic_atual) if selic_atual else None,
    }
    C.dados["indicadores_complementares"] = comp_extra
    for k, v in comp_extra.items():
        w(f"- {k}: {fmt(v, 'roe') if k in ('earnings_yield', 'selic_meta') else fmt(v, k)}")
    w("- Leitura: earnings yield abaixo da Selic indica que o lucro atual, sozinho, rende menos que a renda fixa. "
      "Graham e Bazin são heurísticas antigas; servem para conferir agregadores, não para decidir.\n")

    st = mem.status_do_ticker(tk)
    pos = mem.resultado_posicao(tk, preco, dpa)
    C.dados["posicao_investidor"] = {"status": st, "pergunta_central": mem.pergunta_central(st), **(pos or {})}
    w("## 11c. Posição do investidor neste ativo [DADO informado pelo investidor + ESTIMATIVA]\n")
    w(f"- Situação na memória: {st}")
    w(f"- Pergunta central desta análise: {mem.pergunta_central(st)}")
    if pos:
        for k, v in pos.items():
            w(f"- {k}: {fmt(v, 'roe') if k in ('resultado_pct', 'yield_on_cost') else fmt(v, k)}")
    else:
        w("- Sem posição registrada em dados/carteira.csv.")
    w("")

    # ---------------- 8. Lacunas e proveniência
    w("## 12. Lacunas de dados (o que NÃO pôde ser calculado)\n")
    w("\n".join(f"- {l}" for l in C.lacunas) or "- Nenhuma")
    w("\n## 13. Proveniência (fontes consultadas nesta execução)\n")
    w("| Fonte | URL | Coletado em | Obs. |\n|---|---|---|---|")
    for r in fx.PROV.to_list():
        w(f"| {r['fonte']} | {r['url']} | {r['coletado_em']} | {r['observacao']} |")

    (out / "relatorio_quantitativo.md").write_text("\n".join(md), encoding="utf-8")
    C.dados.update(lacunas=C.lacunas, proveniencia=fx.PROV.to_list(), parametros=vars(args),
                   instituicao_financeira=financeira)
    (out / "dados.json").write_text(json.dumps(C.dados, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"OK -> {out}/relatorio_quantitativo.md")
    print(f"Lacunas: {len(C.lacunas)}")
    for l in C.lacunas:
        print("  -", l)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
