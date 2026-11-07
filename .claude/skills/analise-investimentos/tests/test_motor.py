"""Testes offline do motor (dados sintéticos; não acessam a rede).

Rodar:  python -m pytest .claude/skills/analise-investimentos/tests -q
"""
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import carteira as ct  # noqa: E402
import fundamentos as fd  # noqa: E402
import valuation as vl  # noqa: E402


def cvm_sintetico(anos=(2021, 2022, 2023, 2024)) -> pd.DataFrame:
    linhas = []
    for k, a in enumerate(anos):
        f = 1.1 ** k
        contas = [
            ("BPA", "1", "Ativo Total", 1000 * f), ("BPA", "1.01", "Ativo Circulante", 400 * f),
            ("BPA", "1.01.01", "Caixa e Equivalentes", 100 * f), ("BPA", "1.01.02", "Aplicações", 20 * f),
            ("BPA", "1.01.03", "Contas a Receber", 120 * f), ("BPA", "1.01.04", "Estoques", 90 * f),
            ("BPA", "1.02", "Ativo Não Circulante", 600 * f), ("BPA", "1.02.03", "Imobilizado", 400 * f),
            ("BPA", "1.02.04", "Intangível", 50 * f),
            ("BPP", "2.01", "Passivo Circulante", 250 * f), ("BPP", "2.01.04", "Empréstimos", 60 * f),
            ("BPP", "2.02", "Passivo Não Circulante", 250 * f), ("BPP", "2.02.01", "Empréstimos", 200 * f),
            ("BPP", "2.03", "Patrimônio Líquido Consolidado", 500 * f),
            ("BPP", "2.03.09", "Participação dos Acionistas Não Controladores", 10 * f),
            ("DRE", "3.01", "Receita de Venda", 800 * f), ("DRE", "3.02", "Custo", -500 * f),
            ("DRE", "3.03", "Resultado Bruto", 300 * f), ("DRE", "3.04", "Despesas Operacionais", -150 * f),
            ("DRE", "3.04.01", "Despesas com Vendas", -80 * f), ("DRE", "3.04.02", "Despesas Gerais e Administrativas", -70 * f),
            ("DRE", "3.05", "Resultado Antes do Resultado Financeiro", 150 * f),
            ("DRE", "3.06", "Resultado Financeiro", -30 * f), ("DRE", "3.06.01", "Receitas Financeiras", 10 * f),
            ("DRE", "3.06.02", "Despesas Financeiras", -40 * f), ("DRE", "3.07", "LAIR", 120 * f),
            ("DRE", "3.08", "IR e CSLL", -30 * f), ("DRE", "3.11", "Lucro do Período", 90 * f),
            ("DRE", "3.11.01", "Atribuído a Sócios da Controladora", 85 * f),
            ("DFC", "6.01", "Caixa Líquido Atividades Operacionais", 130 * f),
            ("DFC", "6.01.01.02", "Depreciação e Amortização", 40 * f),
            ("DFC", "6.02", "Caixa Líquido Atividades de Investimento", -80 * f),
            ("DFC", "6.02.01", "Aquisição de Imobilizado", -70 * f),
            ("DFC", "6.02.02", "Adições ao Intangível", -10 * f),
            ("DFC", "6.03", "Caixa Líquido Atividades de Financiamento", -40 * f),
            ("DFC", "6.03.03", "Dividendos e Juros sobre Capital Próprio Pagos", -40 * f),
        ]
        for dem, cod, ds, v in contas:
            linhas.append({"demonstracao": dem, "DT_REFER": f"{a}-12-31", "DT_INI_EXERC": f"{a}-01-01",
                           "DT_FIM_EXERC": f"{a}-12-31", "ORDEM_EXERC": "ÚLTIMO", "CD_CONTA": cod,
                           "DS_CONTA": ds, "VL_CONTA": float(v), "DENOM_CIA": "EMPRESA TESTE SA"})
    return pd.DataFrame(linhas)


def test_tabela_e_indicadores():
    t = fd.tabela_anual(cvm_sintetico())
    assert t.loc["capex", 2021] == pytest.approx(-80)
    assert t.loc["dividendos_pagos", 2021] == pytest.approx(-40)
    i = fd.indicadores(t)
    assert i.loc[2021, "margem_ebit"] == pytest.approx(150 / 800)
    assert i.loc[2021, "aliquota_efetiva"] == pytest.approx(0.25)
    assert i.loc[2021, "divida_liquida"] == pytest.approx(260 - 120)
    assert i.loc[2021, "fcf"] == pytest.approx(50)
    assert i.loc[2022, "crescimento_receita"] == pytest.approx(0.10)
    assert fd.cagr(i["receita_liquida"]) == pytest.approx(0.10)
    # ROE com PL médio
    assert i.loc[2022, "roe"] == pytest.approx(85 * 1.1 / ((500 + 550) / 2))


def test_beneish_crescimento_uniforme():
    b = fd.beneish(fd.tabela_anual(cvm_sintetico()))
    # crescimento uniforme -> índices de variação = 1, SGI = 1.1
    assert b.loc[2022, "DSRI"] == pytest.approx(1.0)
    assert b.loc[2022, "SGI"] == pytest.approx(1.1)
    assert b.loc[2021, "sinal_triagem"] == "dados insuficientes"


def test_multiplos():
    t = fd.tabela_anual(cvm_sintetico())
    i = fd.indicadores(t)
    m = fd.multiplos(t, i, preco=10.0, acoes=100.0)
    lucro = 85 * 1.1 ** 3
    assert m["p_l"] == pytest.approx(1000 / lucro)
    assert m["valor_mercado"] == 1000


def test_detecta_financeira():
    df = cvm_sintetico()
    df.loc[(df.CD_CONTA == "3.01"), "DS_CONTA"] = "Receitas da Intermediação Financeira"
    assert fd.eh_financeira(df)


@pytest.fixture
def retornos():
    rng = np.random.default_rng(0)
    idx = pd.bdate_range("2020-01-01", periods=1000)
    m = rng.normal(0.0004, 0.012, len(idx))
    R = pd.DataFrame({"^BVSP": m,
                      "AAA": 1.2 * m + rng.normal(0, 0.01, len(idx)),
                      "BBB": 0.5 * m + rng.normal(0.0003, 0.008, len(idx)),
                      "NOVO": rng.normal(0.0005, 0.015, len(idx))}, index=idx)
    return R


def test_estatisticas_beta(retornos):
    e = ct.estatisticas(retornos["AAA"], 0.0, retornos["^BVSP"])
    assert e["beta"] == pytest.approx(1.2, abs=0.1)
    assert e["drawdown_maximo"] < 0


def test_contribuicao_risco_soma_volatilidade(retornos):
    R = retornos[["AAA", "BBB"]]
    m = ct.metricas_carteira(np.array([0.6, 0.4]), R, 0.0, None)
    soma = sum(v["contribuicao"] for v in m["contribuicao_risco"].values())
    assert soma == pytest.approx(m["volatilidade_wsw"])


def test_inclusao_ativo_descorrelacionado_reduz_vol(retornos):
    r = ct.comparar_inclusao(retornos[["AAA", "BBB", "NOVO"]], {"AAA": 0.5, "BBB": 0.5}, "NOVO", 0.0, None)
    assert "B_com_10pct" in r
    assert r["C_grade"]["10%"]["volatilidade_anualizada"] < r["A_original"]["volatilidade_anualizada"]


def test_ledoit_wolf_bem_condicionada(retornos):
    S, d = ct.ledoit_wolf(retornos.values)
    assert 0 <= d <= 1
    assert np.all(np.linalg.eigvalsh(S) > 0)


def test_fronteira(retornos):
    f = ct.fronteira_monte_carlo(retornos[["AAA", "BBB", "NOVO"]], 0.1, n=2000)
    assert sum(f["max_sharpe"]["pesos"].values()) == pytest.approx(1, abs=1e-3)


PREMISSAS = {
    "ano_base": 2024, "receita_base": 1000.0, "anos_projecao": 5, "crescimento_receita": 0.05,
    "margem_ebit": 0.20, "aliquota_ir": 0.34, "da_sobre_receita": 0.04, "capex_sobre_receita": 0.05,
    "capital_giro_sobre_receita": 0.10, "crescimento_terminal": 0.03, "rf": 0.10, "beta": 1.0,
    "premio_risco_mercado": 0.05, "custo_divida_pre_ir": 0.12, "peso_divida": 0.3,
    "divida_liquida": 100.0, "acoes": 10.0,
}


def test_dcf_estado_estacionario_igual_gordon():
    # crescimento constante = g terminal -> DCF deve igualar Gordon do FCFF
    p = {**PREMISSAS, "crescimento_receita": 0.03}
    r = vl.dcf_fcff(p)
    w = r["wacc"]
    rec1 = 1000 * 1.03
    fcff1 = rec1 * 0.2 * 0.66 + rec1 * 0.04 - rec1 * 0.05 - (rec1 - 1000) * 0.10
    assert r["enterprise_value"] == pytest.approx(fcff1 / (w - 0.03), rel=1e-9)


def test_wacc_capm():
    ke = vl.capm(0.10, 1.0, 0.05)
    assert ke == pytest.approx(0.15)
    assert vl.wacc(ke, 0.12, 0.34, 0.3) == pytest.approx(0.15 * 0.7 + 0.12 * 0.66 * 0.3)


def test_premissas_ausentes():
    p = dict(PREMISSAS)
    del p["beta"]
    with pytest.raises(vl.PremissasIncompletas, match="beta"):
        vl.dcf_fcff(p)


def test_g_maior_que_wacc():
    with pytest.raises(vl.PremissasIncompletas):
        vl.dcf_fcff({**PREMISSAS, "crescimento_terminal": 0.5})


def test_sensibilidade_monotonica():
    s = vl.sensibilidade(PREMISSAS, "wacc_override", [0.11, 0.12, 0.13], "crescimento_terminal", [0.02, 0.03])
    col = s.iloc[:, 0].values
    assert col[0] > col[1] > col[2]


def test_reverse_dcf():
    alvo = vl.dcf_fcff({**PREMISSAS, "crescimento_receita": 0.08})["valor_por_acao"]
    g = vl.premissas_implicitas_no_preco(PREMISSAS, alvo)
    assert g == pytest.approx(0.08, abs=1e-4)


def test_lucro_residual_roe_igual_ke():
    # ROE = Ke -> valor = VPA
    assert vl.lucro_residual(10.0, [0.15] * 5, 0.5, 0.15, 0.03) == pytest.approx(10.0)


def test_cli_ponta_a_ponta_offline(tmp_path, monkeypatch, retornos):
    """Executa analisar.main() com as fontes substituídas por dados sintéticos."""
    import analisar
    import fontes as fx
    precos = (1 + retornos.rename(columns={"AAA": "ITUB4", "BBB": "BOVA11", "NOVO": "TESTE3"})).cumprod() * 10
    cdi = pd.Series(0.04, index=precos.index)
    monkeypatch.setattr(fx, "cvm_ticker_para_empresa", lambda t, *a: {"ticker": t, "cnpj": "00.000.000/0001-00", "nome": "EMPRESA TESTE SA"})
    monkeypatch.setattr(fx, "cvm_cadastro", lambda c: {"SETOR_ATIV": "Máquinas"})
    monkeypatch.setattr(fx, "cotacao_atual", lambda t: {"preco": 10.0, "moeda": "BRL", "horario": "agora", "atraso_aviso": ""})
    monkeypatch.setattr(fx, "cvm_demonstracoes", lambda *a, **k: cvm_sintetico())
    monkeypatch.setattr(fx, "cvm_fre_acoes", lambda c: {"total": 100.0})
    monkeypatch.setattr(fx, "bcb_sgs", lambda s, *a, **k: cdi if s == "cdi_diario" else pd.Series([10.5, 10.5], index=precos.index[-2:]))
    monkeypatch.setattr(fx, "bcb_focus", lambda k: pd.DataFrame({"Data": ["2026-11-01"], "DataReferencia": ["2026"], "Mediana": [4.5]}))
    monkeypatch.setattr(fx, "precos", lambda s, a: precos)
    monkeypatch.setattr(fx, "rf_longo", lambda *a: {"rf": 0.15, "titulo": "Tesouro Prefixado com Juros Semestrais",
                                                    "vencimento": "2037-01-01", "data_base": "2026-11-05", "juro_real_ipca": 0.078})
    monkeypatch.setattr(fx, "damodaran_erp", lambda *a: {"rating": "Ba1", "spread_default": 0.0213, "crp": 0.0324,
                                                         "erp_total": 0.0747, "erp_maduro": 0.0423, "atualizado": "January 5, 2026"})
    monkeypatch.setattr(fx, "damodaran_beta_setor", lambda *a: None)
    prem = tmp_path / "p.json"
    prem.write_text(json.dumps({**PREMISSAS, "acoes": None,
                                "cenarios": {"pessimista": {"margem_ebit": 0.15}, "base": {}, "otimista": {"margem_ebit": 0.25}}}))
    monkeypatch.setattr(sys, "argv", ["analisar.py", "--ticker", "TESTE3", "--carteira", "ITUB4:0.5,BOVA11:0.5",
                                      "--premissas", str(prem), "--saida", str(tmp_path)])
    assert analisar.main() == 0
    pasta = next(tmp_path.glob("TESTE3_*"))
    md = (pasta / "relatorio_quantitativo.md").read_text(encoding="utf-8")
    for trecho in ("Indicadores fundamentalistas", "Beneish", "Markowitz", "Sensibilidade", "Margem de segurança"):
        assert trecho in md, trecho
    dados = json.loads((pasta / "dados.json").read_text(encoding="utf-8"))
    assert dados["valuation"]["valor_por_acao"] > 0


def test_banco_ltm_e_pvp_justificado():
    import bancos as bk

    def linha(dem, cod, ds, v, fim, ini=None, ordem="ÚLTIMO", ref=None):
        return {"demonstracao": dem, "DT_REFER": ref or fim, "DT_INI_EXERC": ini, "DT_FIM_EXERC": fim,
                "ORDEM_EXERC": ordem, "CD_CONTA": cod, "DS_CONTA": ds, "VL_CONTA": v}
    dfp = pd.DataFrame([
        linha("BPA", "1", "Ativo Total", 1000.0, "2025-12-31"),
        linha("BPP", "2.07", "Patrimônio Líquido Consolidado", 100.0, "2025-12-31"),
        linha("DRE", "3.03", "Resultado Bruto de Intermediação Financeira", 50.0, "2025-12-31", "2025-01-01"),
        linha("DRE", "3.04.01", "Despesa de Provisão para Perda Esperada", -20.0, "2025-12-31", "2025-01-01"),
        linha("DRE", "3.11", "Lucro ou Prejuízo Líquido Consolidado do Período", 12.0, "2025-12-31", "2025-01-01"),
    ])
    itr = pd.DataFrame([
        linha("BPA", "1", "Ativo Total", 1100.0, "2026-06-30", ref="2026-06-30"),
        linha("BPP", "2.07", "Patrimônio Líquido Consolidado", 110.0, "2026-06-30", ref="2026-06-30"),
        linha("DRE", "3.11", "Lucro ou Prejuízo Líquido Consolidado do Período", 8.0, "2026-06-30", "2026-01-01", ref="2026-06-30"),
        linha("DRE", "3.11", "Lucro ou Prejuízo Líquido Consolidado do Período", 5.0, "2025-06-30", "2025-01-01", "PENÚLTIMO", "2026-06-30"),
    ])
    t = bk.tabela_anual_banco(dfp)
    i = bk.indicadores_banco(t)
    assert i.loc[2025, "pdd_sobre_margem"] == pytest.approx(0.4)
    ltm = bk.ltm_banco(t, itr)
    assert ltm["lucro_liquido"] == pytest.approx(12 + 8 - 5)   # anual + acumulado atual − acumulado anterior
    assert ltm["lucro_controladores"] == pytest.approx(15)     # sem segregação -> usa o total
    assert ltm["ativo_total"] == pytest.approx(1100)           # saldo do último ITR
    assert bk.pvp_justificado(0.15, 0.15, 0.05) == pytest.approx(1.0)



def test_ke_brasil():
    k = vl.ke_brasil(0.15, 1.0, 0.0747, 0.0213, 0.0423)
    assert k["ke_metodo_a"] == pytest.approx(0.15 - 0.0213 + 0.0747)
    assert k["ke_metodo_b"] == pytest.approx(0.15 + 0.0423)


def test_valuation_banco_roe_igual_ke_vale_vpa():
    r = vl.valuation_banco(10.0, 10.0, 0.15, 0.05, 0.3, {"base": [0.15, 0.15]})
    assert r["cenarios"]["base"]["valor_por_acao"] == pytest.approx(10.0)
    assert r["roe_implicito_2_estagios"] == pytest.approx(0.15, abs=1e-6)
    assert r["roe_implicito_gordon"] == pytest.approx(0.15)


def test_b3_ajuste_desdobramento_e_provento():
    import b3
    idx = pd.to_datetime(["2024-04-12", "2024-04-15", "2024-04-16", "2024-09-02"])
    fech = pd.Series([56.0, 56.0, 28.0, 27.0], index=idx)   # desdobramento 1:2 após 15/04
    ev = {"stockDividends": [{"isinCode": "X", "lastDatePrior": "15/04/2024", "factor": "100,00000000000",
                              "label": "DESDOBRAMENTO"}],
          "cashDividends": [{"isinCode": "X", "lastDatePrior": "16/04/2024", "rate": "0,28000000000",
                             "label": "DIVIDENDO", "relatedTo": "1T24"}]}
    aj = fech * b3._fatores(ev, {"X"}, fech)
    assert aj["2024-04-15"] == pytest.approx(28.0 * 0.99)     # metade × fator do provento (1 − 0,28/28)
    assert aj["2024-04-16"] == pytest.approx(28.0 * 0.99)
    assert aj["2024-09-02"] == pytest.approx(27.0)
    assert not b3.checar_saltos(aj.to_frame("X"))["X"]


def test_nota_travas_e_consenso():
    import nota
    dados = {"instituicao_financeira": True,
             "custo_capital": {"ke": {"ke_base": 0.20}},
             "ltm": {"lucro_controladores": 12.0, "pl_controlador": 186.0, "pdd": -69.0, "margem_bruta_intermediacao": 102.0},
             "estatisticas_ativo": {"drawdown_maximo": -0.44, "volatilidade_anualizada": 0.31},
             "valuation": {"cenarios": {"base": {"variacao_vs_preco": -0.16, "margem_seguranca": -0.196}}}}
    pareceres = [{"analista": "valor", "nota": 5.0, "notas_dimensoes": {"gestao": 4.5}},
                 {"analista": "macro", "nota": 4.0, "notas_dimensoes": {"gestao": 4.0}},
                 {"analista": "risco", "nota": 2.0, "notas_dimensoes": {"gestao": 3.0}}]
    r = nota.consolidar(dados, pareceres)
    assert 0 <= r["nota_final"] <= 10
    assert r["dimensoes"]["valuation"]["nota"] == pytest.approx(3.0)      # −16% no intervalo −40%..+40%
    assert r["dimensoes"]["negocio"]["nota"] < 2.5                         # ROE 6,5% vs Ke 20%
    assert any("≤ 2" in t for t in r["travas"])                            # PDD/margem ~68% -> saúde ~2
    assert r["nota_final"] <= 5.0
    assert r["nota_conselho"] == pytest.approx(3.7, abs=0.05)
    assert r["consenso"] == "media"                                        # desvio ~1,25


def test_relatorio_html_gera_pagina(tmp_path):
    import relatorio_html
    (tmp_path / "dados.json").write_text(json.dumps({"empresa": {"ticker": "TESTE3", "nome": "EMPRESA TESTE"},
                                                     "cotacao": {"preco": 10.0, "horario": "2026-11-05"}}))
    (tmp_path / "nota.json").write_text(json.dumps({"nota_final": 6.2, "leitura": "Neutra / preço justo", "nota_quant": 6.0,
                                                    "nota_conselho": 6.4, "desvio_analistas": 0.5, "consenso": "alta",
                                                    "travas": [], "dimensoes": {"valuation": {"nota": 6.0, "regra": "x", "peso": 0.3}}}))
    (tmp_path / "parecer_valor.json").write_text(json.dumps({"analista": "valor", "nota": 6.4, "conviccao": "media",
                                                             "veredito": "ok", "tese": ["[DADO] a"], "riscos": ["b"]}))
    (tmp_path / "RELATORIO.md").write_text("# T\n\n## 1. Resumo\n\n| a | b |\n|---|---|\n| 1 | 2 |\n")
    out = relatorio_html.main(tmp_path).read_text()
    assert "<title>TESTE3" in out and "Fundamentalista de Valor" in out and "<table>" in out
    assert out.count("<div") == out.count("</div>")
