# Fontes de dados e como consultá-las em tempo real

## Automatizadas pelos scripts (`scripts/fontes.py`)

| Dado | Fonte | Endpoint |
|---|---|---|
| DFP / ITR (BP, DRE, DFC) | CVM — Dados Abertos | `https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/{DFP,ITR}/DADOS/{dfp,itr}_cia_aberta_<ANO>.zip` |
| Ticker → CNPJ | CVM — FCA (valores mobiliários) | `.../DOC/FCA/DADOS/fca_cia_aberta_<ANO>.zip` |
| Cadastro (setor, auditor, controle) | CVM | `.../CAD/DADOS/cad_cia_aberta.csv` |
| Nº de ações | CVM — FRE (capital social) | `.../DOC/FRE/DADOS/fre_cia_aberta_<ANO>.zip` |
| Selic, CDI, IPCA, PTAX, PIB, desemprego | BCB — SGS | `https://api.bcb.gov.br/dados/serie/bcdata.sgs.<COD>/dados?formato=json` (432, 12, 433, 1, 4380, 24369) |
| Expectativas (Focus) | BCB — Olinda | `https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/ExpectativasMercadoAnuais` |
| Preços ajustados, Ibovespa | Yahoo Finance (1ª tentativa) | `https://query1.finance.yahoo.com/v8/finance/chart/<TICKER>.SA` (`^BVSP`) |
| Preços oficiais (fallback, sem token) | B3 — COTAHIST | `https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A<ANO>.ZIP` |
| Desdobramentos, grupamentos, proventos | B3 — eventos corporativos | `https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall/GetListedSupplementCompany/<base64>` |
| Taxa livre de risco (NTN-F, IPCA+) | Tesouro Transparente | CSV `precotaxatesourodireto.csv` (dataset "taxas dos títulos ofertados pelo Tesouro Direto") |
| ERP, risco-país, betas setoriais | Damodaran | `ctryprem.html`, `Betas.html` |
| Verificação de referências | Crossref | `https://api.crossref.org/works/<DOI>` |

Valores da CVM são convertidos para R$ (coluna `ESCALA_MOEDA`). Apenas a versão mais
recente de cada documento (reapresentações) é usada.

## Consultadas pelo agente (WebSearch / WebFetch) durante a análise

| O quê | Onde procurar |
|---|---|
| Release de resultados, apresentação, guidance, teleconferência | Site de RI da companhia (buscar "<empresa> relações com investidores") |
| Fatos relevantes, comunicados, atas, FRE completo (remuneração, partes relacionadas) | CVM — `https://www.rad.cvm.gov.br/` e `https://sistemas.cvm.gov.br/` (ENET) |
| Notas explicativas, parecer do auditor (ressalvas, PAAs) | PDF das DFs no RI ou RAD/CVM |
| Composição acionária, proventos declarados, free float, liquidez | B3 (`https://www.b3.com.br`) e RI |
| Prêmio de risco de mercado, betas setoriais | Damodaran Online (`https://pages.stern.nyu.edu/~adamodar/`) |
| Curva de juros (NTN-B, prefixados) para Rf | Tesouro Direto / ANBIMA |
| Dados setoriais | Agências reguladoras (ANEEL, ANP, ANATEL, ANS, SUSEP), associações setoriais, IBGE (SIDRA) |
| Literatura acadêmica | Scite (`search_literature`, `verify_papers`), DOI.org, SSRN, NBER, SciELO |
| Notícias e riscos recentes | Valor Econômico, Reuters, Bloomberg Línea, InfoMoney (sempre confrontar com fonte primária) |

## Agregadores e opinião do mercado (WebSearch / WebFetch, sempre consultados)

| O quê | Onde | Uso |
|---|---|---|
| Indicadores, histórico de 10 anos, proventos, comparação com o setor | Investidor10 (`investidor10.com.br/acoes/<ticker>/`), Status Invest (`statusinvest.com.br/acoes/<ticker>`), Fundamentus (`fundamentus.com.br/detalhes.php?papel=<TICKER>`) | triagem e **conferência cruzada** dos números do motor |
| FIIs: P/VP, DY, vacância, relatório gerencial | Investidor10 (`/fiis/<ticker>/`), Status Invest (`/fundos-imobiliarios/<ticker>`), Funds Explorer, site da gestora | relatório gerencial da gestora é a fonte primária |
| Agenda de proventos (data-com, pagamento, valor) | RI e B3; Investidor10 e Status Invest para conferência | |
| Recomendações e preço-alvo das casas (BTG, XP, Itaú BBA, Safra, Genial etc.) | imprensa que resume os relatórios: InfoMoney, Valor, Money Times, Exame, Brazil Journal, E-Investidor | registrar **consenso** (quantas compram, mantêm, vendem; preço-alvo médio, data) |
| Teses e críticas de outros analistas | artigos e entrevistas de gestores e analistas; transcrição da teleconferência (perguntas dos analistas) | registrar os melhores argumentos a favor e contra |

Regras:
- Relatórios completos das casas costumam ser pagos: use só o que é público e cite a data.
- Opinião de analista é contexto, nunca prova. Primeiro registre o consenso; depois faça a análise
  própria e, se discordar, explique por quê (regra antimanada).
- Se o agregador divergir do motor ou do RI, vale a fonte primária, e a divergência entra no relatório.
- Se um site bloquear o acesso, tente outro da lista e registre a falha. Nunca contorne bloqueio
  anti-robô (mirror, cache, troca de user-agent).

## Hierarquia de confiança
1. Documento oficial arquivado na CVM / DF auditada
2. Material de RI da companhia (informação da própria parte interessada — ler com ceticismo)
3. Dados oficiais (BCB, IBGE, B3)
4. Literatura revisada por pares
5. Imprensa especializada
6. Agregadores (Status Invest, Fundamentus etc.) — apenas para conferência cruzada, nunca como fonte única

## Defasagens típicas
- DFP: até 3 meses após o fim do exercício. ITR: até 45 dias após o trimestre.
- Yahoo: cotação com atraso de ~15 min; preços ajustados podem divergir da B3 em eventos corporativos.
- FRE: atualizado anualmente (e em eventos); confirmar ações em tesouraria no RI.
