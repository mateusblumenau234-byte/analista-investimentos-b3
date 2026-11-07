"""Testes da memória do investidor e das fórmulas complementares (offline)."""
import importlib
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import carteira as ct  # noqa: E402
import fundamentos as fd  # noqa: E402

CSV = """# atualizado_em: {data}
ativo,classe,cotas,preco_medio,status,observacao
BBAS3,Ações BR,20,"27,40",Congelada,
ITUB4,Ações BR,10,30.00,Ativa,
SPXI11,Internacional,?,?,Ativa,
TESOURO-IPCA-2032,Renda fixa,1,1500,Pausada,
VALE3,Ações BR,0,,Excluída,
"""


@pytest.fixture
def mem(tmp_path, monkeypatch):
    monkeypatch.setenv("ANALISE_DADOS", str(tmp_path))
    import memoria
    m = importlib.reload(memoria)
    (tmp_path / "carteira.csv").write_text(CSV.format(data="2026-11-01"), encoding="utf-8")
    (tmp_path / "perfil.md").write_text("# Perfil\n\nAtualizado em: 07/11/2026\n- Objetivo: renda\n", encoding="utf-8")
    return m


def test_leitura_e_numeros_brasileiros(mem):
    linhas, data = mem.ler_carteira()
    assert data == "2026-11-01"
    bb = mem.posicao("bbas3", linhas)
    assert bb["cotas_num"] == 20 and bb["preco_medio_num"] == pytest.approx(27.40)
    assert mem.posicao("SPXI11", linhas)["cotas_num"] is None


def test_status(mem):
    assert mem.status_do_ticker("BBAS3") == "congelada"
    assert mem.status_do_ticker("ITUB4") == "na carteira"
    assert mem.status_do_ticker("VALE3") == "excluida"
    assert mem.status_do_ticker("WEGE3") == "nova"
    assert "voltar a aportar" in mem.pergunta_central("congelada")


def test_pesos_por_valor(mem):
    pesos, avisos = mem.pesos_por_valor({"BBAS3": 15.0, "ITUB4": 30.0})
    assert pesos == pytest.approx({"BBAS3": 300 / 600, "ITUB4": 300 / 600})
    assert any("SPXI11" in a for a in avisos)          # sem cotas
    assert any("TESOURO" in a for a in avisos)         # sem cotação em bolsa
    assert "VALE3" not in pesos
    # sem cotação, cai no preço médio e avisa
    pesos2, avisos2 = mem.pesos_por_valor({"ITUB4": 30.0})
    assert pesos2["BBAS3"] == pytest.approx(548 / 848)
    assert any("preço médio" in a for a in avisos2)


def test_compra_recalcula_preco_medio(mem):
    mem.cmd_compra("ITUB4", 10, 40.0)
    r = mem.posicao("ITUB4")
    assert r["cotas_num"] == 20 and r["preco_medio_num"] == pytest.approx(35.0)
    mem.cmd_compra("ITUB4", -5, 50.0)                  # venda não muda o PM
    r = mem.posicao("ITUB4")
    assert r["cotas_num"] == 15 and r["preco_medio_num"] == pytest.approx(35.0)
    mem.cmd_compra("WEGE3", 4, 50.0)                   # ativo novo
    assert mem.posicao("WEGE3")["cotas_num"] == 4


def test_resumo_lista_perguntas(mem):
    txt = mem.cmd_resumo("BBAS3")
    assert "congelada" in txt and "Continua assim?" in txt
    assert "Quanto pretende aportar" in txt
    txt_novo = mem.cmd_resumo("WEGE3")
    assert "Você já tem cotas de WEGE3?" in txt_novo
    assert "excluído" in mem.cmd_resumo("VALE3")


def test_registrar_historico(mem):
    import argparse
    mem.cmd_registrar(argparse.Namespace(ticker="bbas3", motivo="manter", conclusao="Pouco atrativa",
                                         preco=16.49, nota=4.2, decisao="aguardar", pasta=None))
    mem.cmd_registrar(argparse.Namespace(ticker="ITUB4", motivo="aumentar", conclusao="Preço justo",
                                         preco=None, nota=None, decisao=None, pasta=None))
    h = mem.ler_historico()
    assert [x["ticker"] for x in h] == ["BBAS3", "ITUB4"] and h[0]["nota"] == "4.2"


def test_resultado_posicao(mem):
    r = mem.resultado_posicao("ITUB4", 33.0, 1.5)
    assert r["resultado_pct"] == pytest.approx(0.10)
    assert r["yield_on_cost"] == pytest.approx(0.05)
    assert mem.resultado_posicao("WEGE3", 10.0) is None


def test_formulas_complementares():
    assert fd.numero_graham(2, 10) == pytest.approx(math.sqrt(450))
    assert fd.numero_graham(-1, 10) is None
    assert fd.preco_teto_bazin(0.6) == pytest.approx(10.0)
    assert fd.preco_teto_bazin(0.6, 0.15) == pytest.approx(4.0)
    assert fd.earnings_yield(2.0, 20.0) == pytest.approx(0.10)
    assert fd.peg(10, 0.12) == pytest.approx(10 / 12)
    z = fd.altman_z_emergentes(100, 50, 80, 400, 600, 1000)
    assert z["z"] == pytest.approx(3.25 + 0.656 + 0.163 + 0.5376 + 0.7) and z["zona"] == "cinzenta"


def test_inclusao_de_ativo_que_ja_esta_na_carteira():
    rng = np.random.default_rng(0)
    R = pd.DataFrame(rng.normal(0.0005, 0.01, (500, 3)), columns=["A", "B", "C"],
                     index=pd.bdate_range("2024-01-01", periods=500))
    res = ct.comparar_inclusao(R, {"A": 0.5, "B": 0.3, "C": 0.2}, "C", 0.0, None)
    assert "0%" in res["C_grade"] and "20%" in res["C_grade"]
    assert "vender tudo" in res["aviso"]


def test_primeiro_uso_cria_memoria_em_branco(tmp_path, monkeypatch):
    destino = tmp_path / "novo"
    monkeypatch.setenv("ANALISE_DADOS", str(destino))
    import memoria
    m = importlib.reload(memoria)
    assert m.garantir_dados() == ["perfil.md", "carteira.csv", "historico.csv"]
    assert m.perfil_vazio()
    assert m.ler_carteira() == ([], None)
    assert "Entrevista de perfil completa" in m.cmd_resumo("WEGE3")
    assert m.garantir_dados() == []          # segunda vez não sobrescreve nada


def test_modelos_nao_tem_dados_pessoais():
    modelos = SCRIPTS.parent / "modelos"
    linhas = (modelos / "carteira.csv").read_text(encoding="utf-8").strip().splitlines()
    assert len(linhas) == 2                  # só a data e o cabeçalho
    assert "[PREENCHER]" in (modelos / "perfil.md").read_text(encoding="utf-8")


def test_explorar_dados_gera_resumo_alertas_e_graficos(tmp_path):
    import explorar_dados as ex
    pasta = tmp_path / "WEGE3_2026-11-07"
    pasta.mkdir()
    rng = np.random.default_rng(3)
    idx = pd.bdate_range("2023-01-02", periods=400)
    px = pd.DataFrame({c: 20 * np.exp(np.cumsum(rng.normal(0, 0.01, 400))) for c in ["WEGE3", "EMBR3", "^BVSP"]}, index=idx)
    px.iloc[200:, 1] *= 0.5                  # salto artificial de -50%: deve virar alerta
    px.to_csv(pasta / "precos.csv")
    px.pct_change().corr().to_csv(pasta / "correlacao.csv")
    pd.DataFrame({"roe": [0.2, 0.21, 0.22, 0.05], "margem_ebit": [0.15, 0.16, 0.15, 0.14]},
                 index=[2022, 2023, 2024, 2025]).to_csv(pasta / "indicadores.csv")
    assert ex.main([str(pasta)]) == 0
    txt = (pasta / "exploracao.md").read_text(encoding="utf-8")
    assert "EMBR3: variação de -50," in txt and "desdobramento" in txt
    assert "roe do último ano" in txt          # ROE 5% contra média ~17%: fora do padrão
    assert "| roe |" in txt
    for g in ("precos_base100", "drawdown", "volatilidade", "correlacao", "indicadores"):
        assert (pasta / "graficos" / f"{g}.png").exists()
