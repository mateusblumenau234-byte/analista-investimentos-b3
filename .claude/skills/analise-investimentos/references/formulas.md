# Fórmulas registradas

Regra: todo número do relatório sai de uma função dos scripts. Nada é calculado de cabeça.
Cada linha diz o que a fórmula mede, onde ela está no código e quando não usar.

## 1. Crescimento
| Fórmula | O que mede | Código |
|---|---|---|
| CAGR = (final / inicial)^(1/n) − 1 | crescimento médio anual composto | `fundamentos.cagr` |
| Crescimento da receita, do lucro | variação ano a ano | `fundamentos.indicadores` |

## 2. Rentabilidade (empresas não financeiras)
| Fórmula | O que mede | Código |
|---|---|---|
| ROE = Lucro líquido / PL médio | retorno do dinheiro dos sócios | `fundamentos.indicadores` |
| ROA = Lucro líquido / Ativo médio | retorno sobre tudo que a empresa tem | `fundamentos.indicadores` |
| ROIC = NOPAT / Capital investido médio; NOPAT = EBIT × (1 − T) | retorno do capital usado na operação | `fundamentos.indicadores` |
| Margens bruta, EBIT, EBITDA, líquida | quanto sobra de cada R$ vendido | `fundamentos.indicadores` |

Cria valor só quando ROIC > WACC (Modigliani e Miller, 1958). Crescer com ROIC abaixo do custo de capital destrói valor.

## 3. Endividamento e liquidez (não usar em bancos)
| Fórmula | Código |
|---|---|
| Dívida líquida = Dívida bruta − Caixa e aplicações | `fundamentos.indicadores` |
| Dívida líquida / EBITDA; Dívida líquida / PL | `fundamentos.indicadores` |
| Liquidez corrente = AC / PC | `fundamentos.indicadores` |
| Cobertura de juros = EBIT / Despesa financeira | `fundamentos.indicadores` |
| Altman Z'' (emergentes) = 3,25 + 6,56·X1 + 3,26·X2 + 6,72·X3 + 1,05·X4; zonas: > 5,85 segura, 4,35 a 5,85 cinzenta, < 4,35 risco | `fundamentos.altman_z_emergentes` |

## 4. Caixa e qualidade dos lucros
| Fórmula | O que mede | Código |
|---|---|---|
| FCF = FCO − CAPEX | caixa que sobra depois de investir | `fundamentos.indicadores` |
| FCFF = NOPAT + D&A − CAPEX − ΔCapital de giro | caixa da firma para DCF | `valuation.dcf_fcff` |
| Conversão = FCO / Lucro | lucro virou caixa? | `fundamentos.indicadores` (`fco_sobre_lucro`) |
| Accruals = Lucro − FCO (sobre o ativo) | lucro "de papel" | `fundamentos.indicadores` |
| Beneish M-Score (8 variáveis), limiar −1,78 | triagem de manipulação, nunca prova | `fundamentos.beneish` |

## 5. Múltiplos
| Fórmula | Código |
|---|---|
| P/L = Preço / LPA; P/VP = Preço / VPA | `fundamentos.multiplos`, `bancos.multiplos_banco` |
| EV = Valor de mercado + Dívida líquida + Minoritários; EV/EBITDA; EV/EBIT | `fundamentos.multiplos` |
| P/FCF = Valor de mercado / FCF | `fundamentos.multiplos` |
| Earnings yield = LPA / Preço (comparar com Selic e Tesouro IPCA+) | `fundamentos.earnings_yield` |
| PEG = P/L ÷ crescimento esperado do lucro (em pontos) | `fundamentos.peg` |

Múltiplo baixo não prova oportunidade (Fama, 1970): pode ser o mercado precificando lucro menor no futuro.

## 6. Proventos
| Fórmula | Código |
|---|---|
| Dividend yield = Proventos pagos em 12 meses / Preço | `fundamentos.multiplos` (`dividend_yield_caixa`) |
| Payout = Proventos / Lucro | `fundamentos.indicadores`, `bancos.indicadores_banco` |
| Yield on cost = Proventos por ação em 12 meses / Seu preço médio | `memoria.resultado_posicao` |
| JCP líquido = JCP bruto × (1 − 15%) | aplicar no texto ao comparar com dividendos |

## 7. Custo de capital
| Fórmula | Referência | Código |
|---|---|---|
| CAPM: Ke = Rf + β × (Rm − Rf) | Sharpe (1964) | `valuation.capm` |
| Ke Brasil (método A: Rf − spread + β × ERP total; método B: Rf + β × ERP maduro) | Damodaran | `valuation.ke_brasil` |
| β por regressão contra o Ibovespa, ajuste de Blume (0,67β + 0,33) | Blume (1971) | `carteira.estatisticas` |
| WACC = Ke·E/V + Kd·(1 − T)·D/V | Modigliani e Miller (1963) | `valuation.wacc` |

## 8. Valor intrínseco
| Fórmula | Quando usar | Código |
|---|---|---|
| DCF: Σ FCFF_t/(1+WACC)^t + VT/(1+WACC)^n; VT = FCFF_(n+1)/(WACC − g) | empresas não financeiras | `valuation.dcf_fcff` |
| Sensibilidade WACC × g e cenários | sempre junto com o DCF | `valuation.sensibilidade`, `valuation.cenarios` |
| Reverse DCF: crescimento implícito no preço | teste de Shiller: o preço embute otimismo demais? | `valuation.premissas_implicitas_no_preco` |
| Gordon: P = D1 / (Ke − g), exige Ke > g | empresas maduras pagadoras | `valuation.gordon` |
| DDM em dois estágios | pagadoras com transição | `valuation.ddm_dois_estagios` |
| Lucro residual (Ohlson, 1995): V = VPA + Σ (ROE − Ke)·VPA_(t−1)/(1+Ke)^t | bancos e seguradoras | `valuation.lucro_residual`, `valuation.valuation_banco` |
| P/VP justo = (ROE − g) / (Ke − g) | bancos | `bancos.pvp_justificado` |
| Margem de segurança = (Valor justo − Preço) / Valor justo | sempre | `valuation.margem_seguranca` |

Heurísticas de triagem (servem para conferir os agregadores, não para decidir):
| Fórmula | Código |
|---|---|
| Número de Graham = √(22,5 × LPA × VPA) | `fundamentos.numero_graham` |
| Preço teto de Bazin = Dividendo médio por ação / 6% (mostrar também com a Selic) | `fundamentos.preco_teto_bazin` |

## 9. Bancos e seguradoras
| Indicador | Código ou fonte |
|---|---|
| ROE, ROA, alavancagem (Ativo/PL), PDD sobre margem, índice de eficiência, payout | `bancos.indicadores_banco` |
| Lucro dos últimos 12 meses (DFP + ITR) | `bancos.ltm_banco` |
| Índice de Basileia, capital principal, inadimplência > 90 dias, cobertura | release de resultados do RI (copiar com fonte) |
| Índice combinado de seguradoras = (Sinistros + Despesas) / Prêmios ganhos | release do RI ou SUSEP |

## 10. FIIs (fora do motor automático: calcular no relatório com fonte)
- P/VP = Preço da cota / Valor patrimonial da cota (relatório gerencial)
- DY mensal e em 12 meses; vacância física e financeira; inadimplência
- Cap rate = Receita operacional líquida anual / Valor dos imóveis
- LTV = Dívida / Valor dos ativos (fundos alavancados)

## 11. Risco e carteira
| Fórmula | Referência | Código |
|---|---|---|
| Retorno e volatilidade anualizados (252 pregões) | | `carteira.estatisticas` |
| Sharpe = (R − Rf)/σ; Sortino = (R − Rf)/σ dos retornos negativos | Sharpe (1966); Sortino | `carteira.estatisticas` |
| Drawdown máximo | | `carteira.drawdown_maximo` |
| VaR e beta rolante | | `carteira.estatisticas`, `carteira.beta_rolante` |
| E(Rp) = Σ wᵢ·E(Rᵢ); σp = √(w'Σw) | Markowitz (1952) | `carteira.metricas_carteira` |
| Contribuição ao risco = wᵢ·(Σw)ᵢ / σp | | `carteira.metricas_carteira` |
| Covariância encolhida | Ledoit e Wolf (2004) | `carteira.ledoit_wolf` |
| Cenários A/B/C (original, com 10%, grade de pesos; 0% e peso atual se já tiver) | | `carteira.comparar_inclusao` |
| Fronteira eficiente, estabilidade dos pesos, Monte Carlo do patrimônio | | `carteira.fronteira_monte_carlo`, `carteira.estabilidade_pesos`, `carteira.monte_carlo_patrimonio` |
| Pesos da carteira real = cotas × último preço / total | | `memoria.pesos_por_valor` |

## Limites que valem para todas
- Retorno histórico não é retorno esperado. Correlação não é causalidade.
- Preços podem ficar longe dos fundamentos por muito tempo (Shiller, 1981 e 2000).
- Todo modelo é sensível às premissas: mostrar sempre a sensibilidade.
- Referências acadêmicas só entram no relatório depois de conferidas (`fontes.crossref`).
