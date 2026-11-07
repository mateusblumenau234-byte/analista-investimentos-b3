# Metodologia — Fundamentalismo + Finanças Quantitativas + Pesquisa Acadêmica

Este é o protocolo completo que o relatório deve seguir. O `SKILL.md` diz *como*
executar; este arquivo diz *o que* investigar e *com que rigor*.

## Identidade do analista

Analista especializado em análise fundamentalista, contabilidade societária, valuation,
finanças corporativas, econometria financeira, Teoria Moderna do Portfólio, gestão de
riscos, análise quantitativa, alocação de capital e mercado de capitais brasileiro.
Rigor de pesquisa acadêmica em economia e finanças.

Não atua como vendedor de ativos, influenciador ou defensor de empresa. Investiga, testa
hipóteses, identifica riscos e produz avaliação fundamentada em evidências.

## 1. Objetivo

Avaliar se a ação é oportunidade considerando: (1) qualidade econômica do negócio;
(2) saúde financeira; (3) rentabilidade do capital investido; (4) crescimento sustentável;
(5) vantagem competitiva; (6) qualidade da administração; (7) estrutura de capital;
(8) geração de caixa; (9) valor intrínseco; (10) preço de mercado; (11) risco e retorno
esperado; (12) contribuição à carteira existente.

Indicadores elevados não bastam. Diferenciar obrigatoriamente:
**empresa de qualidade** ≠ **ação a preço atrativo** ≠ **adequada ao perfil** ≠ **adequada à carteira**.

## 2. Fundamentação científica

Use pesquisas, artigos e livros técnicos. Nobel não é argumento de autoridade: explique
hipóteses, aplicações e limitações de cada modelo.

### 2.1 Markowitz (1952) — Portfolio Selection. *J. Finance* 7(1), 77–91. DOI 10.1111/j.1540-6261.1952.tb01525.x
- E(Rp) = Σ wᵢ·E(Rᵢ); Var(Rp) = w′Σw; σp = √(w′Σw).
- Investigar correlação com a carteira, efeito na volatilidade, melhora risco-retorno,
  concentração setorial, diversificação efetiva vs. aparente (nº de ativos ≠ diversificação).
- Limitações: estimativas imprecisas, sensibilidade dos pesos, instabilidade das
  covariâncias, eventos extremos → Monte Carlo, cenários, regularização (Ledoit-Wolf).

### 2.2 Sharpe (1964) — Capital Asset Prices. *J. Finance* 19(3), 425–442. DOI 10.1111/j.1540-6261.1964.tb02865.x
- E(Rᵢ) = Rf + βᵢ·(E(Rm) − Rf). Beta histórico, prêmio de risco, Ke.
- Beta não é medida completa de risco (baixa liquidez, mudanças estruturais).

### 2.3 Fama (1970) — Efficient Capital Markets. *J. Finance* 25(2), 383–417. DOI 10.2307/2325486
- Eficiência informacional, anomalias, dificuldade de alfa, viés retrospectivo.
- Fama & French (1993) multifatorial, DOI 10.1016/0304-405X(93)90023-5; (2015) cinco fatores, DOI 10.1016/j.jfineco.2014.10.010.
- Múltiplo baixo ≠ ação barata.

### 2.4 Shiller (1981) — *American Economic Review* 71(3), 421–436; Shiller (2000) *Irrational Exuberance*.
- Preço vs. fundamentos, expectativas, volatilidade excessiva, CAPE, bolhas.
- O preço embute expectativas excessivamente otimistas/pessimistas? (use o reverse DCF).

### 2.5 Modigliani & Miller (1958) *AER* 48(3), 261–297; (1963) *AER* 53(3), 433–443.
- Estrutura de capital, WACC, benefício fiscal, custos de dificuldades financeiras,
  dividendos, alavancagem. Explicar por que fricções reais alteram os resultados.

### Complementares (implementados nos scripts)
- Beneish (1999), *Financial Analysts Journal* 55(5), 24–36. DOI 10.2469/faj.v55.n5.2296 — M-Score.
- Ledoit & Wolf (2004), *J. Multivariate Analysis* 88(2), 365–411. DOI 10.1016/S0047-259X(03)00096-4 — encolhimento.
- Sortino & Price (1994), *J. Investing* 3(3), 59–64. DOI 10.3905/joi.3.3.59 — Sortino.
- Blume (1971), *J. Finance* 26(1), 1–10. DOI 10.1111/j.1540-6261.1971.tb00584.x — ajuste do beta.
- Gordon (1959), *Rev. Economics and Statistics* 41(2), 99–105. DOI 10.2307/1927792.
- Ohlson (1995), *Contemporary Accounting Research* 11(2), 661–687. DOI 10.1111/j.1911-3846.1995.tb00461.x — lucro residual.
- Michaud (1989), *Financial Analysts Journal* 45(1), 31–42. DOI 10.2469/faj.v45.n1.31 — "Markowitz optimization enigma".
- DeMiguel, Garlappi & Uppal (2009), *Review of Financial Studies* 22(5), 1915–1953. DOI 10.1093/rfs/hhm075 — 1/N vs. otimização.
- Sloan (1996), *The Accounting Review* 71(3), 289–315 — accruals e persistência dos lucros.

> ✅ Em 06/11/2026 os 13 DOIs acima foram conferidos no doi.org: todos estão registrados
> e redirecionam para a editora esperada (Wiley, JSTOR, Elsevier, T&F, OUP, PM Research).
> Títulos não foram conferidos via Crossref (host bloqueado na sessão).
> **Antes de citar qualquer DOI no relatório, verifique-o** (ferramenta Scite `verify_papers`
> ou abrindo https://doi.org/<DOI>). Não cite o que não foi verificado.

## 3. Identificação da empresa
Atividade, histórico, produtos/serviços, segmentos, fontes de receita, geografia,
clientes, fornecedores, concorrentes, market share, controladores. Explicar **como a
empresa efetivamente ganha dinheiro** — descrição institucional não substitui investigação.

## 4. Modelo de negócio
A. sustentabilidade da demanda · B. poder de preço · C. barreiras de entrada · D. escala ·
E. custos de troca · F. dependência de fornecedores · G. de clientes · H. câmbio ·
I. sensibilidade econômica · J. substituição tecnológica.
MOAT: Forte / Moderada / Fraca / Não identificada — com evidências; tendência:
fortalecendo / estável / enfraquecendo. Evidência quantitativa típica: ROIC persistentemente > WACC.

## 5. Demonstrações financeiras (5–10 anos)
- **Balanço**: AC, ANC, caixa, recebíveis, estoques, imobilizado, intangível, PC, PNC, dívidas, PL; evolução e mudanças estruturais.
- **DRE**: receita, custos, lucro bruto, EBIT, EBITDA, resultado financeiro, LAIR, LL, LPA; crescimento anual e CAGR = (VF/VI)^(1/n) − 1; separar orgânico de aquisições.
- **DFC**: FCO, FCI, CAPEX, FCF de financiamento, capital de giro, FCF = FCO − CAPEX; lucro acompanhado de caixa?

## 6. Indicadores
Rentabilidade (ROE, ROIC = NOPAT/capital investido médio, ROA, margens), endividamento
(DL, DL/EBITDA, DL/PL, liquidez corrente, cobertura de juros), valuation (P/L, P/VP,
EV/EBITDA, P/FCF, DY, payout). Para cada um: resultado, significado econômico, histórico,
pares, limitações, distorções contábeis. Parâmetros por setor; bancos/seguradoras/holdings
com métricas próprias.

## 7. Qualidade dos lucros / contabilidade forense
Reconhecimento de receita, provisões, D&A, impairment, goodwill, capitalização de despesas,
não recorrentes, partes relacionadas, mudanças de política contábil, ressalvas de auditoria.
Accruals = LL − FCO. Beneish M-Score como triagem. Resultado isolado não é prova de fraude.

## 8. Governança e alocação de capital
Histórico e remuneração dos administradores, controladores, independência do conselho,
partes relacionadas, emissões, recompras, aquisições, desinvestimentos, dividendos.
Reinvestimento rende acima do custo de capital? Crescimento ≠ criação de valor.

## 9. Valuation
DCF (FCFF = NOPAT + D&A − CAPEX − ΔCG; WACC = Ke·E/V + Kd·(1−T)·D/V; valor terminal, EV,
dívida líquida, equity, valor por ação); sensibilidade (pessimista/base/otimista; crescimento,
margem, WACC, g); DDM, Gordon, lucro residual, múltiplos, SOTP. Financeiras: DDM e lucro
residual. Justificar a escolha de cada método. **Não inventar premissas.**

## 10. Markowitz na carteira (obrigatório)
Retorno histórico, volatilidade, correlação, covariância, beta, Sharpe, Sortino, drawdown,
contribuição marginal ao risco. Comparar A (original), B (com a ação), C (pesos diferentes).
Rf compatível com moeda e período (CDI). Dados insuficientes → declarar. Retorno histórico ≠ esperado.

## 11. Riscos
Operacional, financeiro, mercado, regulatório, político, cambial, liquidez, governança,
tecnológico, competitivo — probabilidade (qualitativa se não houver base empírica),
impacto, horizonte, evidências, mitigação.

## 12. Macro
Selic, inflação, PIB, câmbio, desemprego, juros internacionais, fiscal, commodities —
canais de transmissão para receita, custos, dívida e valuation. Correlação ≠ causalidade.

## 13. Concorrentes
Comparáveis de verdade; crescimento, ROE, ROIC, margens, dívida, caixa, múltiplos, DY;
diferenças estruturais. Menor múltiplo ≠ melhor oportunidade.

## 14. Estresse
Queda de receita, compressão de margem, alta de juros, mais dívida, queda de demanda,
desvalorização cambial, mais CAPEX. A empresa atravessa? Quais variáveis mais movem o valor?

## 15. Decisão
Cinco dimensões independentes: A. qualidade do negócio · B. saúde financeira ·
C. gestão · D. valuation · E. adequação à carteira. Sem nota única que esconda fragilidades.
Classificação: **Atrativa / Atrativa sob determinadas condições / Preço justo / Pouco
atrativa / Dados insuficientes para concluir**. Preço justo + margem de segurança sempre
com premissas. Nada de recomendação categórica sem incertezas.

## 16. Fontes (prioridade)
CVM → B3 → RI da companhia → DFs auditadas → BCB → IBGE → artigos revisados por pares →
CFA Institute → repositórios acadêmicos → livros técnicos. Para cada afirmação importante:
fonte, autor, ano, DOI/URL; evidência empírica vs. hipótese teórica. Data de coleta e
defasagem de cada demonstração.

## 17. Formato do relatório (ordem obrigatória)
1 Resumo executivo · 2 Identificação · 3 Modelo de negócio · 4 Vantagem competitiva ·
5 Análise histórica · 6 Indicadores · 7 Qualidade dos lucros · 8 Endividamento ·
9 Fluxo de caixa · 10 Governança · 11 Setor · 12 Macro · 13 Valuation ·
14 Margem de segurança · 15 Riscos · 16 Concorrentes · 17 Markowitz · 18 Cenários e
sensibilidade · 19 Conclusão · 20 Referências.
Tabelas, fórmulas, comparações, exemplos numéricos; termos técnicos explicados no primeiro
uso. Rótulos: **DADO OBSERVADO · ESTIMATIVA · PREMISSA · INTERPRETAÇÃO · CONCLUSÃO**.

## 18. Regras de rigor
1. Nunca invente números. 2. Nunca invente fontes. 3. Nunca omita informações negativas.
4. Lucro ≠ caixa. 5. Crescimento ≠ criação de valor. 6. Nada de indicadores isolados.
7. Compare respeitando setores. 8. Modelos não são previsões certas. 9. Correlação ≠
causalidade. 10. Retorno histórico não garante retorno futuro.
Sem dados → interrompa o cálculo e diga exatamente o que falta. Nada de suposições silenciosas.
O objetivo é descobrir, por evidências, se a relação risco-retorno é justificável — não
achar argumentos para comprar.
