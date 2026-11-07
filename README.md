# Analista de investimentos (B3) para Claude Code

Uma **skill do Claude Code** que funciona como um analista de investimentos pessoal para ações e FIIs da B3.
Você manda um ticker e ele:

1. **Conhece você antes de analisar.** No primeiro uso faz uma entrevista de perfil (objetivo, horizonte,
   aportes, reação a quedas, alocação alvo, regras pessoais) e pede sua carteira. Nas próximas vezes só
   pergunta o que mudou: se você já tem cotas do ativo, se comprou algo, quanto vai aportar e o motivo.
2. **Pesquisa em tempo real**: CVM (DFP, ITR, FRE), B3, Banco Central (Selic, IPCA, Focus), Tesouro,
   site de RI da empresa, Investidor10, Status Invest, Fundamentus, notícias e opinião de outros analistas.
3. **Calcula com fórmulas registradas** (`references/formulas.md`): indicadores, qualidade dos lucros
   (accruals, Beneish), múltiplos, Graham, Bazin, CAPM, WACC, DCF com sensibilidade e reverse DCF, Gordon,
   DDM, lucro residual para bancos e Markowitz aplicado à **sua** carteira.
4. **Escreve um relatório de 20 seções**, separando dado observado, estimativa, premissa, interpretação e
   conclusão, com um conselho de três analistas independentes (valor, macro e risco) e nota de 0 a 10.
5. **Explora os dados antes de concluir**: resumo de cada tabela, dados faltando, alertas de qualidade
   (saltos de preço, séries curtas, indicadores fora do padrão) e gráficos em preto e cinza.
6. **Grava a memória**: carteira e histórico de análises ficam salvos para a próxima vez.

## Instalação

Requisitos: [Claude Code](https://docs.claude.com/en/docs/claude-code) e Python 3.10 ou mais novo.

**Opção 1: usar este repositório como projeto**
```bash
git clone https://github.com/<seu-usuario>/<este-repositorio>.git
cd <este-repositorio>
pip install -r .claude/skills/analise-investimentos/requirements.txt
claude
```

**Opção 2: instalar a skill para todos os seus projetos**
```bash
cp -r .claude/skills/analise-investimentos ~/.claude/skills/
pip install -r ~/.claude/skills/analise-investimentos/requirements.txt
```

## Como usar
No Claude Code, mande só o ticker:

> analisa WEGE3

Na primeira vez ele faz a entrevista de perfil. Depois disso, cada análise começa pelas perguntas
que faltam e termina gravando a carteira e o histórico.

Comandos da memória (o próprio Claude roda, mas você também pode):
```bash
python .claude/skills/analise-investimentos/scripts/memoria.py resumo --ticker WEGE3
python .claude/skills/analise-investimentos/scripts/memoria.py atualizar --ativo ITUB4 --cotas 50 --preco-medio 31.20 --classe "Ações BR"
python .claude/skills/analise-investimentos/scripts/memoria.py compra --ativo ITUB4 --cotas 10 --preco 33.00
python .claude/skills/analise-investimentos/scripts/memoria.py pesos
```

Só a base quantitativa, sem o Claude:
```bash
python .claude/skills/analise-investimentos/scripts/analisar.py --ticker WEGE3 --pares "EMBR3,RAIL3"
```

## Privacidade
Seu perfil, sua carteira e seu histórico ficam em `.claude/skills/analise-investimentos/dados/`,
que está no `.gitignore`. Eles **nunca** vão para o repositório. O que é publicado são só os modelos
em branco (`modelos/`). Os relatórios gerados (`relatorios/`) também ficam fora do Git.

Em sessões do Claude Code na nuvem, os arquivos somem quando a sessão termina. Para manter a memória
lá, use um fork **privado** e tire a linha de `dados/` do `.gitignore`.

## Segurança
Skills rodam comandos no seu computador, então **leia o código antes de instalar qualquer skill**,
inclusive esta. Esta skill:
- só executa os próprios scripts (`scripts/`), que você pode ler;
- acessa a rede apenas para baixar dados públicos (CVM, B3, Banco Central, Tesouro, Yahoo, Damodaran,
  Crossref) e páginas que o Claude pesquisa;
- não lê credenciais nem arquivos fora do projeto e só grava em `dados/` e `relatorios/`;
- não usa código de outras skills (créditos e inspirações em `references/creditos.md`).

Encontrou um problema de segurança? Abra uma issue.

## Permissões
`.claude/settings.json` libera, só dentro deste projeto, buscas na web, leitura de sites e a execução
dos scripts e testes da skill, para o Claude não pedir autorização a cada site. Se preferir aprovar um
por um, apague o arquivo. Sites que bloqueiam robôs continuam bloqueados: o analista usa outra fonte e
registra a falha no relatório.

## Testes
```bash
python -m pytest .claude/skills/analise-investimentos/tests -q
```

## Aviso
Material educacional e de pesquisa. **Não constitui recomendação de investimento** (CVM, Resolução
20/2021). Dados podem estar atrasados ou errados; confira nas fontes primárias antes de decidir.
Modelos são sensíveis às premissas e retorno passado não garante retorno futuro.

## Licença
MIT. Veja `LICENSE`.
