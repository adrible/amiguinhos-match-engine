# Calibração geral e campo neutro — 19/09/2026

Base remota: `c6648b57dc9540ae745b0c97ebc00247a09a0174`, branch geral `v1.3-spatial-creativity-boldness`. Não depende do torneio Interdimensional.

## Mudanças causais

A dispersão no plano do gol passa de 1,45 para 1,80. A conversão condicional usa uma referência geométrica de acerto no gol, compatível com a distribuição espacial, em lugar da antiga precisão escalar. A referência integra uma mistura aproximada de alvos com execução comum; não usa a habilidade nem o alvo efetivamente escolhido, preservando seus riscos. Pressão, distância, técnica e resposta espacial do goleiro continuam atuando. O xG da situação não é reescrito e não há cotas de gols ou finalizações.

`mode="neutral"` impõe familiaridade igual, torcida dividida e ausência de carga diferencial de viagem, mesmo quando recebe metadados assimétricos antigos. Os campos internos home/away continuam como identificadores por compatibilidade; não conferem vantagem de mando. O índice neutro exclui métricas direcionais e usa placares sem ordem. `home_away` continua disponível para jogos com mando explícito.

## Protocolo e comparação real

Referência: 5.329 partidas com estatísticas completas das cinco grandes ligas europeias, temporadas 2022/23–2024/25, Football-Data.co.uk via [football-datasets](https://github.com/datasets/football-datasets). São agregados de ligas, não uma amostra exclusivamente neutra. CSVs e versões têm hashes nos JSONs. xG e tempo dos eventos não entram neste índice. O índice é uma medida composta de proximidade, não uma porcentagem de realismo. Seus pesos diferem do índice anterior com mando.

Piloto: 100 partidas por versão, seeds 91000–91099. Único candidato de dispersão testado: 1,80. Parâmetros congelados antes da validação de 300 partidas por versão, seeds inéditas 92000–92299. Todas as seeds contíguas foram mantidas. Diagnóstico adicional: 100 partidas por versão nas seeds 92000–92099 com a ordem dos times invertida. Não houve nova escolha de parâmetros após esses resultados.

| Métrica por partida | Real | Antes neutro | Depois neutro |
|---|---:|---:|---:|
| Gols | 2.825 | 2.733 | 2.887 |
| Finalizações | 25.275 | 27.050 | 26.773 |
| No alvo | 8.878 | 10.837 | 9.487 |
| Escanteios | 9.688 | 10.213 | 10.367 |
| Faltas | 23.839 | 26.023 | 25.933 |
| Amarelos | 4.138 | 3.607 | 3.557 |
| Vermelhos | 0.194 | 0.183 | 0.160 |
| Empates | 25.20% | 29.00% | 27.00% |
| 0–0 | 6.06% | 9.33% | 9.33% |
| Ambas marcam | 54.85% | 49.67% | 53.67% |
| Mais de 2,5 gols | 53.48% | 50.67% | 53.67% |

Índice neutro no piloto: **65,69 → 74,15**. Na validação principal: **67,31 → 79,84**. No diagnóstico com ordem invertida: **75,95 → 72,34**. A regressão desse diagnóstico é mantida: gols 2,91 → 2,62, no alvo 11,10 → 9,14 e 0–0 6% → 11%. Portanto, a melhora na precisão é consistente entre as amostras; a melhora global não é uniforme.

Ainda há excesso de faltas, poucos amarelos e excesso de 0–0 na validação. Não se afirma calibração completa nem ausência estatística de qualquer viés de ordem. Os testes garantem os efeitos neutros de estádio e a invariância do índice à troca dos rótulos; jogos espelhados não precisam reproduzir o mesmo placar porque a sequência aleatória muda.

## Validação técnica

767 execuções de testes passaram (incluem sete casos reaproveitados pela importação da suíte de benchmark). Log em `audits/neutral_calibration_20260919/tests.txt`. A suíte inclui geometria espacial, criatividade, continuidade, regras e neutralidade.

Auditoria separada de 100 jogos genéricos: 2.389 chutes, 240 gols e 218,250 xG; razão gols/xG 1,100. Soma do ledger coincide com as estatísticas, dentro da precisão numérica. Isso verifica consistência contábil, não calibração perfeita por faixa de xG. Log e faixas em `xg_audit.txt`.

## Reprodução

Preparar um checkout da base remota acima e o cache dos CSVs listados nos JSONs. Executar no checkout desta revisão:

```bash
python compare_general_engine_v13.py --baseline /caminho/base --cache /caminho/cache --output audits/repro/holdout/comparison.json --matches 300 --start-seed 92000 --workers 3 --neutral
```

Para o piloto: `--matches 100 --start-seed 91000`. Para o diagnóstico invertido: `--matches 100 --start-seed 92000 --mirror`, em outra pasta de saída. O campo `mirrored` foi acrescentado ao relatório após as execuções apenas como metadado de proveniência, sem alterar a simulação.
