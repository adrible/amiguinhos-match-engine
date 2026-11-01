# Atualização geral da engine v1.3

O pacote de finalizações espaciais, criatividade e narração em lotes foi
integrado ao ramo geral `v1.3-spatial-creativity-boldness`. Ele se aplica a
qualquer partida construída com `engine_experiment_v13.MatchEngine` e aos
comandos de `runner_v13.MatchSessionV13`, independentemente de competição.

O ramo do Interdimensional recebeu o pacote primeiro (PR #3). Essa entrega
não substituía a integração no ramo geral. Esta revisão corrige o alcance da
entrega, sem trazer o cadastro ou os resultados daquele torneio para a engine
geral. O exemplo geral `live_brazil2002_danganlock.py` também suporta lotes.

## Uso geral

```python
from engine import make_generic_team
from engine_experiment_v13 import MatchEngine
from runner_v13 import MatchSessionV13

engine = MatchEngine(
    make_generic_team("Time A", 80, "balanced", seed=11),
    make_generic_team("Time B", 80, "attacking", seed=22),
    seed=33,
)
session = MatchSessionV13(engine)
for packet in session.press_p_batch(5):
    # Narrar cada pacote, na ordem retornada.
    print(packet["clock"], packet["main_event"])
```

O lote para no intervalo ou fim da partida. No CLI, use `p 5x` ou `p 10x`.
A narração conserva o resultado de ações pendentes, agrupa os desdobramentos
imediatos de faltas e distingue intenção da colocação efetivamente executada.

## Escopo da comparação com jogos reais

- Base real: 5.329 partidas completas em estatísticas de Premier League,
  Bundesliga, Serie A, La Liga e Ligue 1; temporadas 2022/23 a 2024/25.
- Origem: Football-Data.co.uk, pelo mirror datasets/football-datasets.
- Base mantida igual à avaliação anterior; não é uma amostra de 2026/27.
- Motor: 300 jogos antes e 300 depois, seeds 91000–91299, sem exclusão ou
  repetição seletiva. Mesmas forças, estilos e mando de campo nas duas versões.
- O checkout anterior 2444e4d tem arquivos de runtime e benchmark idênticos ao
  ramo geral 9b2aaa7. A versão nova tem os hashes de cada arquivo no relatório.
- O relatório contém hashes dos CSVs, quantidades por liga/temporada, métricas,
  distribuições e o índice diagnóstico calculado pelo mesmo método existente.
- xG e tempos suplementares não entram nesta comparação: não há xG equivalente
  na fonte e o suplemento de relógio exige normalização específica de períodos.
- Chutes no alvo, faltas e cartões dependem das definições do provedor. A
  população de jogadores é sintética; os totais não reproduzem elencos reais.
- O índice é uma pontuação interna de aderência estatística, não uma porcentagem
  de realismo nem uma probabilidade. Nenhum resultado é usado como quota dentro
  do motor. Com 300 jogos por versão, diferenças pequenas podem ser amostrais.

## Reprodução

No checkout atualizado, com o checkout anterior e o cache de CSVs disponíveis:

```bash
python compare_general_engine_v13.py \
  --baseline /caminho/checkout-anterior \
  --cache /caminho/cache-csvs \
  --output audits/general_spatial_20260919/comparison.json \
  --matches 300 --start-seed 91000 --workers 4
```

Os processos isolados impedem mistura de imports entre versões. Os 12 arquivos
em `chunks/` preservam os registros de todas as partidas simuladas, em lotes de
50. Não há arquivos brutos de partidas reais versionados nesta revisão.

## Resultado da comparação pareada

**748 testes locais passaram.** O benchmark é independente desses testes.

| Métrica | Real | Motor anterior | Motor atualizado |
|---|---:|---:|---:|
| Gols/jogo | 2,825 | 2,837 | 2,720 |
| Chutes/jogo | 25,275 | 26,863 | 26,873 |
| Chutes no alvo/jogo | 8,878 | 9,787 | 10,820 |
| Escanteios/jogo | 9,688 | 10,053 | 10,190 |
| Faltas/jogo | 23,839 | 26,403 | 26,430 |
| Amarelos/jogo | 4,138 | 3,693 | 3,590 |
| Vermelhos/jogo | 0,194 | 0,187 | 0,170 |
| Gols mandante/jogo | 1,550 | 1,470 | 1,297 |
| Gols visitante/jogo | 1,275 | 1,367 | 1,423 |
| Vitórias mandante | 43,65% | 38,00% | 31,33% |
| Empates | 25,20% | 22,67% | 30,00% |
| Vitórias visitante | 31,15% | 39,33% | 38,67% |
| 0–0 | 6,06% | 7,33% | 7,00% |
| Ambos marcam | 54,85% | 53,00% | 53,67% |
| Mais de 2,5 gols | 53,48% | 52,33% | 47,00% |
| Ao menos um time sem sofrer gol | 45,15% | 47,00% | 46,33% |

Índice diagnóstico: **77,40 → 66,29** (escala 0–100),

**A atualização piorou a aderência agregada nesta amostra.** Houve melhora pequena em 0–0, ambos marcam e jogos sem sofrer gol, mas pioras relevantes em chutes no alvo e vitórias/gols de mandantes. Os desvios de faltas e cartões também persistem.

Não houve ajuste para esconder essa regressão, escolha de seeds favoráveis ou mudança dos pesos do índice. A integração disponibiliza as funcionalidades solicitadas no motor geral; não declara a calibração concluída. A próxima investigação deve separar precisão da execução, resposta do goleiro e assimetria de mando, sem adicionar bônus artificiais de gols ou quotas de eventos.

A comparação usa o estado imediatamente anterior ao pacote espacial. Índices de commits anteriores a esse estado não são substitutos para esta coluna anterior.
