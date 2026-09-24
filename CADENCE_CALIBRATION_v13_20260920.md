# Calibração do ritmo e ambiente — 20/09/2026

Motor geral v1.3. Base remota `5438d4521cfe49ea723e063c0f2766e044363294`.

## Mudanças

O fator aleatório de ritmo da partida passa de lognormal mu=−0,04, sigma=0,32 para mu=−0,065, sigma=0,24 no adaptador geral v1.3. Isso reduz moderadamente o ritmo médio e sua dispersão, preservando o efeito de tempo tático, pressão, fadiga e contexto. Limites 0,35–1,65 mantidos. O motor base conserva os parâmetros históricos por padrão. Partidas salvas mantêm o ritmo já registrado, sem recalcular seu passado.

O ambiente sorteado usa agora os nomes dos dois times em ordem canônica. Inverter a listagem do mesmo confronto, com a mesma seed, não muda mais clima, vento, temperatura ou gramado. Configurações explícitas e restauração de partidas continuam preservadas. A versão anterior mudava o ambiente ao inverter os times, portanto seus diagnósticos invertidos incluíam essa diferença adicional.

Não há quotas de gols, chutes ou empates. Permanecem os alvos bilaterais, meio alto, variedade de técnicas, passes criativos e separação entre xG da situação e execução. Nenhum parâmetro de conversão foi alterado nesta revisão.

## Protocolo

Um candidato, definido antes do piloto, sem busca posterior: piloto de 100 jogos por versão nas seeds 96000–96099; validação em seeds inéditas 97000–97299. Os 300 confrontos de validação foram executados nas duas ordens: 600 partidas por versão, correspondentes a 300 pares, não 600 confrontos independentes. Total incluindo piloto: 1.400 simulações. Nenhuma seed descartada.

A análise conjunta das duas ordens foi definida antes do resultado da validação. O índice é recalculado sobre todas as partidas, não a média dos índices. Bootstrap reamostra os pares inteiros, preservando dependência entre as duas ordens. Referência: 5.329 partidas reais, cinco grandes ligas, 2022/23–2024/25, [Football-Data via football-datasets](https://github.com/datasets/football-datasets). São ligas, não uma amostra exclusivamente neutra. O índice exclui métricas direcionais de mando, xG e cronologia.

## Resultado conjunto

| Métrica por jogo | Real | Antes | Depois |
|---|---:|---:|---:|
| Gols | 2.825 | 2.992 | 2.783 |
| Finalizações | 25.275 | 26.720 | 26.133 |
| No alvo | 8.878 | 9.300 | 8.900 |
| Escanteios | 9.688 | 9.835 | 9.767 |
| Faltas | 23.839 | 24.972 | 24.653 |
| Amarelos | 4.138 | 3.778 | 3.792 |
| Vermelhos | 0.194 | 0.213 | 0.188 |
| Empates | 25.20% | 25.83% | 24.33% |
| 0–0 | 6.06% | 7.67% | 5.83% |
| Ambas marcam | 54.85% | 57.00% | 50.33% |
| Mais de 2,5 gols | 53.48% | 54.83% | 49.33% |

Índice combinado: **87,01 → 89,95**. Piloto: 74,80 → 85,34. Ordem original na validação: **88,11 → 82,86**; ordem invertida: **79,86 → 93,14**. A melhora conjunta não é uniforme entre as duas ordens. Não comparar diretamente esses valores com índices de outras seeds como se a diferença fosse toda causada pelo código.

## Incerteza e pendências

Bootstrap de 5.000 reamostragens dos pares, seed 20260920: diferença de chutes −0,587/jogo [−1,120; −0,083], no alvo −0,400 [−0,732; −0,078], gols −0,208 [−0,410; −0,010]. Esses intervalos descrevem a população sintética examinada, não garantias universais.

Empates mudaram −1,50 ponto percentual, intervalo de 95% [−6,17; +3,17]; 0–0 −1,83 ponto, intervalo [−4,33; +0,83]. Portanto, não há evidência suficiente para declarar redução robusta desses dois indicadores, embora as taxas observadas estejam próximas da referência. Amarelos continuam baixos e faltas/chutes acima da referência. Ambas marcam e mais de 2,5 gols ficaram abaixo da referência e mais distantes que antes.

Após a correção ambiental, diferença média de gols entre slots +0,030, intervalo [−0,107; +0,168]. Não mostra vantagem clara nem prova simetria perfeita. Resultados individuais não precisam ser idênticos ao inverter a ordem.

Como ritmo e ambiente foram corrigidos juntos, os efeitos de cada mudança não são isolados por este experimento. A integração se apoia no resultado conjunto e nos testes causais específicos.

## Testes e reprodução

776 execuções de testes aprovadas, incluindo igualdade ambiental sob inversão, redução da dispersão sem ritmo determinístico e preservação de ritmo/clima em partidas salvas. A contagem inclui sete casos reaproveitados por importação da suíte de benchmark. Log e todos os resultados em `audits/cadence_20260920/`.

```bash
python compare_general_engine_v13.py --baseline /caminho/base --cache /caminho/cache --output audits/repro/holdout/comparison.json --matches 300 --start-seed 97000 --workers 3 --neutral
python compare_general_engine_v13.py --baseline /caminho/base --cache /caminho/cache --output audits/repro/mirrored/comparison.json --matches 300 --start-seed 97000 --workers 3 --neutral --mirror
python pool_neutral_calibration_v13.py --root audits/repro --cache /caminho/cache
python audit_neutral_order_v13.py --normal audits/repro/holdout --mirrored audits/repro/mirrored --output audits/repro/order.json
```

Para reproduzir o piloto: 100 jogos, seed inicial 96000, outra pasta de saída.
