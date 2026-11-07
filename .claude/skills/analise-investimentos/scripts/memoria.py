#!/usr/bin/env python3
"""Memória do investidor: perfil, carteira e histórico de análises.

Arquivos (pasta dados/ da skill, criada na primeira execução a partir de modelos/;
fica fora do Git para que a carteira de cada pessoa não seja publicada):
  perfil.md      tipo de investidor, objetivo, alocação alvo e regras pessoais (texto)
  carteira.csv   último registro da carteira (uma linha por ativo)
  historico.csv  uma linha por análise feita

Comandos:
  python memoria.py iniciar
      Cria dados/ a partir dos modelos em branco (é chamado automaticamente pelos outros comandos).
  python memoria.py resumo --ticker BBAS3
      Mostra o que já se sabe e lista as perguntas que ainda precisam ser feitas.
  python memoria.py pesos
      Pesos atuais da carteira por valor de mercado (formato aceito por analisar.py --carteira).
  python memoria.py atualizar --ativo BBAS3 --cotas 20 --preco-medio 27.40 [--classe "Ações BR"] [--status Congelada]
      Grava a posição informada pelo investidor e atualiza a data do registro.
  python memoria.py compra --ativo CXSE3 --cotas 5 --preco 14.10
      Soma uma compra à posição e recalcula o preço médio.
  python memoria.py registrar --ticker BBAS3 --motivo manter --conclusao "Pouco atrativa" [--nota 4.2] [--decisao "..."] [--pasta ...]
      Acrescenta a análise ao histórico.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
DADOS = Path(os.environ.get("ANALISE_DADOS", SKILL / "dados"))
MODELOS = SKILL / "modelos"
CAMPOS_CARTEIRA = ["ativo", "classe", "cotas", "preco_medio", "status", "observacao"]
CAMPOS_HIST = ["data", "ticker", "motivo", "preco", "conclusao", "nota", "decisao", "pasta"]
DIAS_CARTEIRA_VELHA = 30
DIAS_PERFIL_VELHO = 180
# classes que não têm cotação em bolsa (ficam fora do Markowitz, mas contam na alocação)
SEM_COTACAO = ("renda fixa", "tesouro", "caixa", "reserva")


# ---------------------------------------------------------------- leitura e escrita
def _num(v):
    if v is None:
        return None
    s = str(v).strip().replace("R$", "").replace(" ", "")
    if s in ("", "?", "n/a", "-"):
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def caminho(nome: str) -> Path:
    return DADOS / nome


def garantir_dados() -> list[str]:
    """Cria dados/ copiando os modelos em branco que faltarem. Devolve os arquivos criados."""
    import shutil
    DADOS.mkdir(parents=True, exist_ok=True)
    criados = []
    for nome in ("perfil.md", "carteira.csv", "historico.csv"):
        destino = DADOS / nome
        if not destino.exists() and (MODELOS / nome).exists():
            shutil.copyfile(MODELOS / nome, destino)
            criados.append(nome)
    return criados


def perfil_vazio() -> bool:
    """Perfil inexistente ou ainda igual ao modelo (objetivo não preenchido)."""
    txt = perfil_texto()
    linha = next((ln for ln in txt.splitlines() if ln.strip().lower().startswith("- objetivo principal")), "")
    return not txt.strip() or "[PREENCHER]" in linha


def ler_carteira() -> tuple[list[dict], str | None]:
    """Devolve (linhas, data_do_registro). A data fica na primeira linha: '# atualizado_em: AAAA-MM-DD'."""
    p = caminho("carteira.csv")
    if not p.exists():
        return [], None
    data = None
    linhas_txt = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        if ln.startswith("#"):
            if "atualizado_em" in ln:
                v = ln.split(":", 1)[1].strip()
                data = v if v and not v.startswith("[") else None
            continue
        if ln.strip():
            linhas_txt.append(ln)
    linhas = []
    for r in csv.DictReader(linhas_txt):
        r = {k: (v or "").strip() for k, v in r.items() if k}
        r["ativo"] = r.get("ativo", "").upper()
        r["cotas_num"] = _num(r.get("cotas"))
        r["preco_medio_num"] = _num(r.get("preco_medio"))
        linhas.append(r)
    return linhas, data


def salvar_carteira(linhas: list[dict], data: str | None = None) -> None:
    DADOS.mkdir(parents=True, exist_ok=True)
    data = data or dt.date.today().isoformat()
    with caminho("carteira.csv").open("w", encoding="utf-8", newline="") as f:
        f.write(f"# atualizado_em: {data}\n")
        w = csv.DictWriter(f, fieldnames=CAMPOS_CARTEIRA, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in linhas:
            w.writerow({k: r.get(k, "") for k in CAMPOS_CARTEIRA})


def ler_historico() -> list[dict]:
    p = caminho("historico.csv")
    if not p.exists():
        return []
    with p.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def perfil_texto() -> str:
    p = caminho("perfil.md")
    return p.read_text(encoding="utf-8") if p.exists() else ""


def perfil_data() -> str | None:
    for ln in perfil_texto().splitlines():
        if ln.lower().startswith("atualizado em:"):
            v = ln.split(":", 1)[1].strip()
            for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
                try:
                    return dt.datetime.strptime(v, fmt).date().isoformat()
                except ValueError:
                    pass
    return None


def _idade_dias(data_iso: str | None) -> int | None:
    if not data_iso:
        return None
    try:
        return (dt.date.today() - dt.date.fromisoformat(data_iso)).days
    except ValueError:
        return None


# ---------------------------------------------------------------- consultas
def posicao(ticker: str, linhas: list[dict] | None = None) -> dict | None:
    linhas = linhas if linhas is not None else ler_carteira()[0]
    return next((r for r in linhas if r["ativo"] == ticker.upper()), None)


def status_do_ticker(ticker: str) -> str:
    """'nova' | 'na carteira' | 'congelada' | 'excluida' | 'pausada'."""
    r = posicao(ticker)
    if not r:
        return "nova"
    s = r.get("status", "").lower()
    for chave in ("congelad", "exclu", "pausad"):
        if chave in s:
            return {"congelad": "congelada", "exclu": "excluida", "pausad": "pausada"}[chave]
    return "na carteira" if (r["cotas_num"] or 0) > 0 else "nova"


def pergunta_central(status: str) -> str:
    return {
        "nova": "Vale comprar, e com qual peso na carteira?",
        "na carteira": "Manter, aumentar ou reduzir a posição?",
        "congelada": "O cenário mudou o bastante para voltar a aportar? (regra do investidor: manter, sem novos aportes)",
        "excluida": "Ativo excluído pelas regras do perfil: avisar antes e perguntar se quer analisar mesmo assim.",
        "pausada": "Classe pausada para aportes: analisar como manutenção, não como compra.",
    }[status]


def pesos_por_valor(precos: dict[str, float] | None = None) -> tuple[dict[str, float], list[str]]:
    """Pesos dos ativos com cotação, por valor de mercado (ou preço médio, se faltar cotação).

    Devolve (pesos, avisos). Ativos sem cotas informadas ou sem cotação em bolsa ficam de fora,
    e cada exclusão vira um aviso para a seção de lacunas.
    """
    linhas, _ = ler_carteira()
    precos = {k.upper(): v for k, v in (precos or {}).items()}
    valores, avisos = {}, []
    for r in linhas:
        a = r["ativo"]
        if "exclu" in r.get("status", "").lower():
            continue
        if any(s in r.get("classe", "").lower() for s in SEM_COTACAO):
            avisos.append(f"{a}: sem cotação em bolsa, fora do Markowitz (conta só na alocação por classe)")
            continue
        q = r["cotas_num"]
        if not q:
            avisos.append(f"{a}: quantidade de cotas não informada, fora do cálculo")
            continue
        px = precos.get(a)
        if px is None:
            px = r["preco_medio_num"]
            if px is None:
                avisos.append(f"{a}: sem cotação nem preço médio, fora do cálculo")
                continue
            avisos.append(f"{a}: peso calculado pelo preço médio (cotação atual indisponível)")
        valores[a] = q * px
    total = sum(valores.values())
    return ({a: v / total for a, v in valores.items()} if total else {}), avisos


def alocacao_por_classe(precos: dict[str, float] | None = None) -> dict[str, float]:
    """Valor por classe, usando cotação quando houver e preço médio × cotas como aproximação."""
    linhas, _ = ler_carteira()
    precos = {k.upper(): v for k, v in (precos or {}).items()}
    tot: dict[str, float] = {}
    for r in linhas:
        q, pm = r["cotas_num"], r["preco_medio_num"]
        if not q:
            continue
        px = precos.get(r["ativo"]) or pm
        if px:
            tot[r.get("classe") or "?"] = tot.get(r.get("classe") or "?", 0.0) + q * px
    return tot


def resultado_posicao(ticker: str, preco_atual: float | None, dpa_12m: float | None = None) -> dict | None:
    """Situação do investidor no ativo: valor, resultado % e yield on cost."""
    r = posicao(ticker)
    if not r or not r["cotas_num"]:
        return None
    q, pm = r["cotas_num"], r["preco_medio_num"]
    out = {"cotas": int(q) if float(q).is_integer() else q, "preco_medio": pm, "status": r.get("status")}
    if preco_atual and pm:
        out.update(valor_atual=q * preco_atual, custo=q * pm, resultado_pct=preco_atual / pm - 1)
    if dpa_12m and pm:
        out["yield_on_cost"] = dpa_12m / pm
    return out


# ---------------------------------------------------------------- comandos
def cmd_resumo(ticker: str) -> str:
    tk = ticker.upper()
    linhas, data = ler_carteira()
    idade = _idade_dias(data)
    perf = perfil_texto()
    hist = [h for h in ler_historico() if h.get("ticker", "").upper() == tk]
    st = status_do_ticker(tk)
    r = posicao(tk, linhas)
    out = [f"# Memória do investidor para {tk}", ""]

    out.append("## Perfil")
    if perfil_vazio():
        out.append("- AINDA NÃO PREENCHIDO: fazer a entrevista de perfil completa antes de tudo.")
    else:
        pend = [ln.strip("- ").strip() for ln in perf.splitlines() if "[PREENCHER]" in ln]
        idade_p = _idade_dias(perfil_data())
        out.append(f"- Atualizado em: {perfil_data() or 'sem data'}"
                   + (f" ({idade_p} dias)" if idade_p is not None else ""))
        if pend:
            out.append("- Campos a preencher: " + "; ".join(pend))
    out.append("")

    out.append("## Carteira")
    preenchidas = [x for x in linhas if x["cotas_num"]]
    out.append(f"- Registro de: {data or 'sem data'}" + (f" ({idade} dias atrás)" if idade is not None else ""))
    out.append(f"- Ativos listados: {len(linhas)}; com quantidade informada: {len(preenchidas)}")
    for x in linhas:
        q = x["cotas_num"]
        pm = x["preco_medio_num"]
        out.append(f"  - {x['ativo']} ({x.get('classe', '')}): "
                   f"{'?' if q is None else f'{q:g}'} cotas, PM {'?' if pm is None else f'R$ {pm:.2f}'}"
                   f"{' [' + x['status'] + ']' if x.get('status') else ''}")
    out.append("")

    out.append(f"## {tk}")
    out.append(f"- Situação: {st}")
    if r:
        q, pm = r["cotas_num"], r["preco_medio_num"]
        out.append(f"- Registro: {'?' if q is None else f'{q:g}'} cotas, "
                   f"preço médio {'?' if pm is None else f'R$ {pm:.2f}'}")
    out.append(f"- Pergunta central da análise: {pergunta_central(st)}")
    if hist:
        u = hist[-1]
        out.append(f"- Última análise: {u.get('data')} | motivo {u.get('motivo')} | {u.get('conclusao')}"
                   f" | nota {u.get('nota') or 'n/d'} | decisão {u.get('decisao') or 'n/d'}")
    out.append("")

    perguntas = []
    if perfil_vazio():
        perguntas.append("Entrevista de perfil completa (ver SKILL.md), uma pergunta por vez.")
    elif any("[PREENCHER]" in ln for ln in perf.splitlines()):
        perguntas.append("Completar os campos [PREENCHER] do perfil.")
    elif (_idade_dias(perfil_data()) or 0) > DIAS_PERFIL_VELHO:
        perguntas.append("Perfil tem mais de 6 meses: algo mudou no objetivo, horizonte ou regras?")
    if st == "excluida":
        perguntas.append(f"{tk} está excluído pelas suas regras. Quer analisar mesmo assim?")
    if r and r["cotas_num"]:
        perguntas.append(f"Seu registro mostra {r['cotas_num']:g} cotas de {tk} a PM "
                         f"{'?' if r['preco_medio_num'] is None else 'R$ %.2f' % r['preco_medio_num']}. Continua assim?")
    else:
        perguntas.append(f"Você já tem cotas de {tk}? Se sim, quantas e a que preço médio?")
    if not preenchidas:
        perguntas.append("Você já investe? Se sim, informe cada ativo com cotas e preço médio; se está começando do zero, diga isso.")
    elif idade is None or idade > DIAS_CARTEIRA_VELHA:
        perguntas.append(f"O registro da carteira é de {data or 'data desconhecida'}. Comprou ou vendeu algo desde então?")
    perguntas.append("Quanto pretende aportar nesta compra ou neste mês?")
    perguntas.append("Motivo: comprar pela primeira vez, aumentar, decidir se mantém, decidir se vende ou só estudar?")
    out.append("## Perguntas a fazer antes da análise")
    out += [f"{i}. {p}" for i, p in enumerate(perguntas, 1)]
    return "\n".join(out)


def cmd_atualizar(ativo: str, cotas: float | None, preco_medio: float | None,
                  classe: str | None, status: str | None, obs: str | None) -> str:
    linhas, _ = ler_carteira()
    a = ativo.upper()
    r = posicao(a, linhas)
    if r is None:
        r = {"ativo": a, "classe": classe or "", "cotas": "", "preco_medio": "", "status": status or "Ativa",
             "observacao": ""}
        linhas.append(r)
    if cotas is not None:
        r["cotas"] = f"{cotas:g}"
    if preco_medio is not None:
        r["preco_medio"] = f"{preco_medio:.2f}"
    if classe:
        r["classe"] = classe
    if status:
        r["status"] = status
    if obs is not None:
        r["observacao"] = obs
    salvar_carteira(linhas)
    return f"Carteira atualizada: {a} = {r['cotas'] or '?'} cotas a PM {r['preco_medio'] or '?'} ({r['status']})."


def cmd_compra(ativo: str, cotas: float, preco: float) -> str:
    linhas, _ = ler_carteira()
    r = posicao(ativo, linhas)
    q0 = (r or {}).get("cotas_num") or 0.0
    pm0 = (r or {}).get("preco_medio_num") or 0.0
    q1 = q0 + cotas
    if q1 <= 0:
        raise SystemExit("Quantidade final não positiva: use 'atualizar' para zerar ou corrigir a posição.")
    # vendas (cotas negativas) não alteram o preço médio
    pm1 = (q0 * pm0 + cotas * preco) / q1 if cotas > 0 else pm0
    return cmd_atualizar(ativo, q1, pm1, None, None, None)


def cmd_registrar(a: argparse.Namespace) -> str:
    p = caminho("historico.csv")
    DADOS.mkdir(parents=True, exist_ok=True)
    novo = not p.exists() or not p.read_text(encoding="utf-8").strip()
    with p.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS_HIST, lineterminator="\n")
        if novo:
            w.writeheader()
        w.writerow({"data": dt.date.today().isoformat(), "ticker": a.ticker.upper(), "motivo": a.motivo,
                    "preco": "" if a.preco is None else f"{a.preco:.2f}", "conclusao": a.conclusao,
                    "nota": "" if a.nota is None else f"{a.nota:.1f}", "decisao": a.decisao or "",
                    "pasta": a.pasta or ""})
    return f"Histórico: análise de {a.ticker.upper()} registrada."


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("iniciar")
    s = sub.add_parser("resumo"); s.add_argument("--ticker", required=True)
    sub.add_parser("pesos")
    s = sub.add_parser("atualizar")
    s.add_argument("--ativo", required=True); s.add_argument("--cotas", type=float)
    s.add_argument("--preco-medio", type=float); s.add_argument("--classe"); s.add_argument("--status")
    s.add_argument("--obs")
    s = sub.add_parser("compra")
    s.add_argument("--ativo", required=True); s.add_argument("--cotas", type=float, required=True)
    s.add_argument("--preco", type=float, required=True)
    s = sub.add_parser("registrar")
    s.add_argument("--ticker", required=True); s.add_argument("--motivo", required=True)
    s.add_argument("--conclusao", required=True); s.add_argument("--preco", type=float)
    s.add_argument("--nota", type=float); s.add_argument("--decisao"); s.add_argument("--pasta")
    a = ap.parse_args(argv)
    criados = garantir_dados()

    if a.cmd == "iniciar":
        print(f"Memória em {DADOS}: " + (f"criados {', '.join(criados)}" if criados else "já existia, nada alterado"))
    elif a.cmd == "resumo":
        print(cmd_resumo(a.ticker))
    elif a.cmd == "pesos":
        pesos, avisos = pesos_por_valor()
        print(",".join(f"{k}:{v:.4f}" for k, v in pesos.items()) or "(carteira sem quantidades)")
        for x in avisos:
            print("aviso:", x, file=sys.stderr)
    elif a.cmd == "atualizar":
        print(cmd_atualizar(a.ativo, a.cotas, a.preco_medio, a.classe, a.status, a.obs))
    elif a.cmd == "compra":
        print(cmd_compra(a.ativo, a.cotas, a.preco))
    elif a.cmd == "registrar":
        print(cmd_registrar(a))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
