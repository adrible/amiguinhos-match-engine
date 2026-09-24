# Calibração de contato e disciplina — 20/09/2026

Aplicação: motor geral v1.3. Base remota `0b11d414824f00fa380a24bcbb0d5d2317bec769`.

## Decisão

Integrar uma melhora específica de contato e disciplina. Não há melhora uniforme do índice global: piloto 73,38 → 70,46; validação principal 85,01 → 84,06; diagnóstico invertido 77,76 → 76,36. Todos esses resultados estão preservados. O índice composto depende de muitas métricas e da amostra; não representa uma porcentagem de realismo. Não comparar os 84,06 desta amostra diretamente com os 79,84 da revisão anterior como ganho de código. A comparação correta usa antes/depois nas mesmas seeds.

## Mudanças

A chance de contato faltoso comum passa a considerar espaço livre: fator `1 - 0.35 * space * (1 - pressure)`. A bola pode sair antes da chegada do defensor em ações pouco pressionadas. Intervenções totalmente disputadas mantêm a chance anterior. Não há meta de faltas consultada durante a partida.

Na decisão de amarelo, reincidência passa de peso 0,17 para 0,27 e aviso anterior de 0,09 para 0,13. A primeira infração sem aviso mantém a fórmula anterior. A chance de vermelho direto não é elevada por esse ajuste. O comportamento mais cauteloso do jogador já amarelado continua ativo.

xG, dispersão, conversão dos chutes e contrato de campo neutro permanecem os da revisão anterior. Não foi acrescentado mecanismo para evitar 0–0 ou produzir um resultado específico.

## Referência e protocolo

5.329 jogos reais com estatísticas completas das cinco grandes ligas europeias, temporadas 2022/23–2024/25, [Football-Data via football-datasets](https://github.com/datasets/football-datasets). Essa referência é de ligas, não exclusivamente de jogos neutros. O índice exclui mando, xG e cronologia.

Piloto de 100 jogos por versão, seeds 93000–93099; candidato único. Parâmetros mantidos para 300 jogos por versão, seeds 94000–94299. Diagnóstico adicional de 100 jogos por versão nas seeds 94000–94099, invertendo os mesmos times. São 1.000 simulações nesta revisão, sem descarte de seeds.

| Métrica por jogo | Real | Antes | Depois |
|---|---:|---:|---:|
| Gols | 2.825 | 2.740 | 2.890 |
| Finalizações | 25.275 | 26.950 | 27.120 |
| No alvo | 8.878 | 9.187 | 9.353 |
| Escanteios | 9.688 | 9.680 | 10.023 |
| Faltas | 23.839 | 26.577 | 25.010 |
| Amarelos | 4.138 | 3.533 | 3.913 |
| Vermelhos | 0.194 | 0.187 | 0.163 |
| Empates | 25.20% | 25.67% | 26.33% |
| 0–0 | 6.06% | 6.67% | 7.33% |
| Ambas marcam | 54.85% | 53.00% | 53.67% |
| Mais de 2,5 gols | 53.48% | 48.33% | 48.33% |

Bootstrap pareado (5.000 reamostragens de partidas, seed 20260920): diferença de faltas −1,567 por jogo, intervalo de 95% [−2,047; −1,100]; amarelos +0,380 [0,187; 0,583]. São estimativas condicionadas à população sintética, não uma garantia universal. As duas mudanças têm a mesma direção no piloto e no diagnóstico invertido.

No diagnóstico invertido: faltas 26,10 → 25,41; amarelos 3,62 → 3,83; gols 2,89 → 2,67; 0–0 8% → 13%. Isso limita a conclusão global. Ainda existem excesso de faltas e finalizações e desvios em cartões e distribuição de gols.

## Ordem dos times e 0–0

O novo script `audit_neutral_order_v13.py` reamostra pares do mesmo confronto nos dois sentidos. Para a calibração espacial anterior, vantagem média do primeiro slot −0,015 gol, intervalo [−0,280; 0,245]. Nesta revisão, −0,010 [−0,240; 0,215]. Ambos são inconclusivos; não demonstram vantagem clara nem provam simetria perfeita. Não se exige que trocar a ordem reproduza o mesmo placar.

A versão anterior apresentou 9,33% de 0–0 nas seeds 92000–92299, mas 6,67% nas novas seeds 94000–94299, sem mudança de código. Portanto, aquela taxa isolada não justifica elevar a conversão. Na validação anterior, os 28 jogos 0–0 tiveram em média 17,75 chutes e 4,93 no alvo, contra 27,70 e 9,96 nos demais jogos: há associação com menor criação, não prova de causalidade. Esta revisão termina com 7,33% de 0–0 na validação principal; não se declara esse desvio resolvido.

## Testes e reprodução

770 execuções de testes aprovadas, incluindo os três novos testes de espaço/pressão, reincidência e ausência de aumento artificial de vermelho direto. A contagem inclui sete casos de benchmark reaproveitados por importação. Log em `audits/contact_calibration_20260920/tests.txt`.

```bash
python compare_general_engine_v13.py --baseline /caminho/base --cache /caminho/cache --output audits/repro/holdout/comparison.json --matches 300 --start-seed 94000 --workers 4 --neutral
python compare_general_engine_v13.py --baseline /caminho/base --cache /caminho/cache --output audits/repro/mirrored/comparison.json --matches 100 --start-seed 94000 --workers 2 --neutral --mirror
python audit_neutral_order_v13.py --normal audits/repro/holdout --mirrored audits/repro/mirrored --output audits/repro/order.json
```

Piloto: mesmo benchmark com `--matches 100 --start-seed 93000`, em pasta separada. Dados por partida, hashes das fontes e do runtime e diagnósticos estão em `audits/contact_calibration_20260920/`.
