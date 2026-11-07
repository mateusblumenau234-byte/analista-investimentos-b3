#!/usr/bin/env python3
"""Análise exploratória dos dados coletados (roda depois de analisar.py, antes de redigir).

Uso: python explorar_dados.py relatorios/<TICKER>_<data>

Lê os CSVs que analisar.py gravou e produz, na mesma pasta:
  exploracao.md                 resumo de cada tabela: período, linhas, dados faltando, estatísticas,
                                tendências e alertas (saltos de preço, séries curtas, valores extremos)
  graficos/precos_base100.png   desempenho do ativo, pares e Ibovespa (base 100)
  graficos/drawdown.png         quedas a partir do pico
  graficos/volatilidade.png     volatilidade anualizada em janela móvel de 63 pregões
  graficos/correlacao.png       mapa de calor das correlações da carteira
  graficos/indicadores.png      evolução anual dos principais indicadores

Ideia inspirada no csv-data-summarizer (coffeefuelbump, MIT), reescrita para dados de mercado da B3.
Só lê arquivos locais da pasta da análise; não acessa a rede e não executa nada externo.
Os gráficos são em preto e cinza, para imprimir bem.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

DU = 252
INDICADORES = ["roe", "roic", "margem_ebit", "margem_liquida", "divida_liquida_ebitda", "crescimento_receita",
               "indice_eficiencia", "pdd_sobre_margem", "payout_caixa", "fco_sobre_lucro"]
ESTILOS = ["-", "--", ":", "-."]


def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"figure.figsize": (9, 4.5), "figure.dpi": 130, "axes.grid": True, "grid.alpha": 0.3,
                         "axes.spines.top": False, "axes.spines.right": False, "font.size": 9})
    return plt


def _pct(x) -> str:
    return "n/d" if x is None or pd.isna(x) else f"{x:.1%}".replace(".", ",")


def _num(x) -> str:
    return "n/d" if x is None or pd.isna(x) else f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ---------------------------------------------------------------- resumo genérico de tabela
def resumo_tabela(nome: str, df: pd.DataFrame) -> list[str]:
    out = [f"### {nome}", f"- Linhas × colunas: {df.shape[0]} × {df.shape[1]}"]
    if isinstance(df.index, pd.DatetimeIndex) and len(df):
        out.append(f"- Período: {df.index.min().date()} a {df.index.max().date()}")
    falt = df.isna().mean()
    falt = falt[falt > 0].sort_values(ascending=False)
    if len(falt):
        out.append("- Dados faltando: " + "; ".join(f"{c} {_pct(v)}" for c, v in falt.head(8).items()))
    else:
        out.append("- Dados faltando: nenhum")
    return out


# ---------------------------------------------------------------- preços
def analisar_precos(px: pd.DataFrame, pasta: Path, ticker: str | None) -> tuple[list[str], list[str]]:
    md, alertas = resumo_tabela("Preços (precos.csv)", px), []
    px = px.dropna(how="all")
    ret = px.pct_change(fill_method=None)
    linhas = ["| Ativo | Pregões | Retorno total | Retorno a.a. | Volatilidade a.a. | Pior dia | Melhor dia | Drawdown máx. |",
              "|---|---|---|---|---|---|---|---|"]
    for c in px.columns:
        s = px[c].dropna()
        r = ret[c].dropna()
        if len(s) < 2:
            alertas.append(f"{c}: série com menos de 2 preços")
            continue
        anos = len(s) / DU
        tot = s.iloc[-1] / s.iloc[0] - 1
        aa = (1 + tot) ** (1 / anos) - 1 if anos > 0 else np.nan
        dd = (s / s.cummax() - 1).min()
        linhas.append(f"| {c} | {len(s)} | {_pct(tot)} | {_pct(aa)} | {_pct(r.std() * np.sqrt(DU))} | "
                      f"{_pct(r.min())} | {_pct(r.max())} | {_pct(dd)} |")
        if len(s) < DU:
            alertas.append(f"{c}: só {len(s)} pregões (menos de 1 ano); estatísticas frágeis")
        saltos = r[r.abs() > 0.25]
        for d, v in saltos.items():
            alertas.append(f"{c}: variação de {_pct(v)} em {d.date()} (conferir desdobramento, grupamento ou provento não ajustado)")
        parado = (r == 0).mean()
        if parado > 0.2:
            alertas.append(f"{c}: {_pct(parado)} dos dias sem variação (baixa liquidez?)")
    md += ["", *linhas, ""]

    plt = _plt()
    g = pasta / "graficos"
    g.mkdir(exist_ok=True)
    base = px.ffill().dropna(how="any")
    if len(base) > 1:
        b100 = base / base.iloc[0] * 100
        fig, ax = plt.subplots()
        for i, c in enumerate(b100.columns):
            destaque = ticker and c == ticker.upper()
            ax.plot(b100.index, b100[c], color="black" if destaque else "0.45",
                    lw=2.0 if destaque else 1.0, ls="-" if destaque else ESTILOS[(i + 1) % 4], label=c)
        ax.set_title("Desempenho (base 100, preços ajustados)")
        ax.legend(ncol=4, fontsize=7, frameon=False)
        fig.tight_layout(); fig.savefig(g / "precos_base100.png"); plt.close(fig)

        fig, ax = plt.subplots()
        alvo = ticker.upper() if ticker and ticker.upper() in base else base.columns[0]
        dd = base[alvo] / base[alvo].cummax() - 1
        ax.fill_between(dd.index, dd * 100, 0, color="0.6")
        ax.set_title(f"Drawdown de {alvo} (% abaixo do pico anterior)")
        fig.tight_layout(); fig.savefig(g / "drawdown.png"); plt.close(fig)

        vol = ret[alvo].rolling(63).std() * np.sqrt(DU) * 100
        if vol.notna().any():
            fig, ax = plt.subplots()
            ax.plot(vol.index, vol, color="black", lw=1)
            ax.set_title(f"Volatilidade anualizada de {alvo}, janela de 63 pregões (%)")
            fig.tight_layout(); fig.savefig(g / "volatilidade.png"); plt.close(fig)
    return md, alertas


# ---------------------------------------------------------------- correlação
def analisar_correlacao(corr: pd.DataFrame, pasta: Path) -> tuple[list[str], list[str]]:
    md, alertas = ["### Correlação (correlacao.csv)"], []
    m = corr.where(~np.eye(len(corr), dtype=bool))
    pares = m.stack().sort_values()
    pares = pares[[a < b for a, b in pares.index]]
    if len(pares):
        md.append("- Par menos correlacionado: " + f"{pares.index[0][0]} × {pares.index[0][1]} = {_num(pares.iloc[0])}")
        md.append("- Par mais correlacionado: " + f"{pares.index[-1][0]} × {pares.index[-1][1]} = {_num(pares.iloc[-1])}")
        altos = pares[pares > 0.8]
        for (a, b), v in altos.items():
            alertas.append(f"{a} e {b} com correlação {_num(v)}: diversificação entre eles é pequena")
    plt = _plt()
    fig, ax = plt.subplots(figsize=(1.0 + 0.6 * len(corr), 0.8 + 0.6 * len(corr)))
    ax.imshow(corr.values, cmap="Greys", vmin=-1, vmax=1)
    ax.set_xticks(range(len(corr)), corr.columns, rotation=45, ha="right")
    ax.set_yticks(range(len(corr)), corr.index)
    ax.grid(False)
    for i in range(len(corr)):
        for j in range(len(corr)):
            v = corr.values[i, j]
            ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=7, color="white" if v > 0.55 else "black")
    ax.set_title("Correlação dos retornos diários")
    fig.tight_layout(); fig.savefig(pasta / "graficos" / "correlacao.png"); plt.close(fig)
    return md + [""], alertas


# ---------------------------------------------------------------- indicadores anuais
def analisar_indicadores(ind: pd.DataFrame, nome: str, pasta: Path) -> tuple[list[str], list[str]]:
    md, alertas = resumo_tabela(f"Indicadores anuais ({nome})", ind), []
    cols = [c for c in INDICADORES if c in ind.columns and ind[c].notna().sum() >= 2]
    if not cols:
        return md + ["- Poucos anos para analisar tendência.", ""], alertas
    md += ["", "| Indicador | Primeiro ano | Último ano | Média | Desvio-padrão | Tendência |", "|---|---|---|---|---|---|"]
    for c in cols:
        s = ind[c].dropna()
        x = np.arange(len(s))
        incl = np.polyfit(x, s.values, 1)[0] if len(s) >= 3 else s.iloc[-1] - s.iloc[0]
        tend = "subindo" if incl > 0.1 * (s.std() or 1) else ("caindo" if incl < -0.1 * (s.std() or 1) else "estável")
        f = _num if c == "divida_liquida_ebitda" else _pct
        md.append(f"| {c} | {s.index[0]}: {f(s.iloc[0])} | {s.index[-1]}: {f(s.iloc[-1])} | {f(s.mean())} | {f(s.std())} | {tend} |")
        ant = s.iloc[:-1]                      # compara o último ano com os anteriores, sem ele mesmo
        if len(ant) >= 3 and ant.std() and abs(s.iloc[-1] - ant.mean()) > 2 * ant.std():
            alertas.append(f"{c} do último ano ({f(s.iloc[-1])}) está a mais de 2 desvios da média dos anos "
                           f"anteriores ({f(ant.mean())}): investigar a causa")
    plt = _plt()
    sel = cols[:4]
    fig, axs = plt.subplots(1, len(sel), figsize=(3.2 * len(sel), 3))
    for ax, c in zip(np.atleast_1d(axs), sel):
        s = ind[c].dropna()
        ax.bar([str(i) for i in s.index], s.values * (1 if c == "divida_liquida_ebitda" else 100), color="0.4")
        ax.set_title(c + ("" if c == "divida_liquida_ebitda" else " (%)"), fontsize=8)
        ax.tick_params(axis="x", rotation=45, labelsize=7)
    fig.tight_layout(); fig.savefig(pasta / "graficos" / "indicadores.png"); plt.close(fig)
    return md + [""], alertas


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print(__doc__)
        return 1
    pasta = Path(argv[0])
    ticker = pasta.name.split("_")[0] if "_" in pasta.name else None
    md = [f"# Exploração dos dados: {ticker or pasta.name}", "",
          "Resumo automático dos dados coletados, para checar qualidade antes de redigir. "
          "Tudo aqui é [ESTIMATIVA] sobre dados observados; nada é previsão.", ""]
    alertas: list[str] = []
    (pasta / "graficos").mkdir(exist_ok=True)

    if (pasta / "precos.csv").exists():
        px = pd.read_csv(pasta / "precos.csv", index_col=0, parse_dates=True)
        m, a = analisar_precos(px, pasta, ticker); md += m; alertas += a
    if (pasta / "correlacao.csv").exists():
        m, a = analisar_correlacao(pd.read_csv(pasta / "correlacao.csv", index_col=0), pasta); md += m; alertas += a
    for nome in ("indicadores.csv", "indicadores_banco.csv"):
        if (pasta / nome).exists():
            m, a = analisar_indicadores(pd.read_csv(pasta / nome, index_col=0), nome, pasta); md += m; alertas += a

    outros = sorted(p for p in pasta.glob("*.csv") if p.name not in
                    {"precos.csv", "correlacao.csv", "indicadores.csv", "indicadores_banco.csv"})
    if outros:
        md.append("## Outras tabelas")
        for p in outros:
            try:
                md += resumo_tabela(p.name, pd.read_csv(p, index_col=0)) + [""]
            except Exception as e:  # tabela vazia ou malformada
                alertas.append(f"{p.name}: não foi possível ler ({type(e).__name__})")

    md += ["## Alertas de qualidade dos dados", *(f"- {x}" for x in alertas or ["Nenhum alerta."]), "",
           "## Gráficos", *(f"- graficos/{g.name}" for g in sorted((pasta / "graficos").glob("*.png")))]
    (pasta / "exploracao.md").write_text("\n".join(md), encoding="utf-8")
    print(f"OK -> {pasta / 'exploracao.md'} ({len(alertas)} alertas)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
