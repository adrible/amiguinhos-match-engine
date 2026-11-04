# Auditoria da camada espacial — 04/11/2026

**Conclusão:** as métricas finais da camada espacial ficaram menos próximas da base real nesta amostra e há incoerências concretas entre setores, coordenadas de finalização e altura de cabeceio. A camada precisa dessas correções antes da validação espacial. A queda do índice, isoladamente, não é estatisticamente conclusiva.

Amostra retida: 600 partidas por runtime, seeds contíguas 108000–108599, mesmos elencos, forças, estilos e mando; mais 96 controles de força igual. Nenhuma seed foi filtrada. A seed oficial não foi utilizada.

Referência principal: 5329 partidas reais, cinco ligas, temporadas 2022/23 a 2024/25.

Baseline: `d3c8d3dba8c8485cfbb6087ef33e645c7d2dd6dd`. Espacial: `1908af7076844bce72c25b776f37592fbe3ce7c6`.

| Parâmetro | Real | Anterior | Espacial | Espacial − real |
|---|---:|---:|---:|---:|
| Gols/jogo | 2.825 | 2.818 | 2.643 | -0.182 |
| Chutes/jogo | 25.275 | 25.978 | 26.143 | +0.869 |
| No alvo/jogo | 8.878 | 8.960 | 8.798 | -0.080 |
| Faltas/jogo | 23.839 | 23.772 | 23.502 | -0.337 |
| Escanteios/jogo | 9.688 | 9.420 | 9.910 | +0.222 |
| Amarelos/jogo | 4.138 | 3.522 | 3.455 | -0.683 |
| Vermelhos/jogo | 0.194 | 0.227 | 0.198 | +0.004 |
| Gols mandante/jogo | 1.550 | 1.520 | 1.403 | -0.147 |
| Gols visitante/jogo | 1.275 | 1.298 | 1.240 | -0.035 |
| Vitória mandante | 43.65% | 44.00% | 40.33% | -3.31 p.p. |
| Empate | 25.20% | 23.33% | 27.50% | +2.30 p.p. |
| Vitória visitante | 31.15% | 32.67% | 32.17% | +1.02 p.p. |
| 0–0 | 6.06% | 7.67% | 9.67% | +3.61 p.p. |
| Ambos marcam | 54.85% | 52.50% | 51.17% | -3.68 p.p. |
| 3 ou mais gols | 53.48% | 53.33% | 48.17% | -5.31 p.p. |
| Ao menos um time sem sofrer gol | 45.15% | 47.50% | 48.83% | +3.68 p.p. |

## Índice e mudança pareada

Índice diagnóstico: anterior 91.50/100; espacial 82.13/100. Não é uma porcentagem de acerto nem certificação física.

Bootstrap pareado descritivo do índice (1.000 reamostragens): IC percentil 95% da diferença espacial−anterior [-20.38; 4.12] pontos. Inclui zero; o tamanho amostral e a sensibilidade do índice impedem tratar a queda observada como prova isolada de regressão populacional.

| Métrica | Espacial − anterior | IC 95% da diferença pareada |
|---|---:|---:|
| Gols/jogo | -0.175 | [-0.356; +0.006] |
| Chutes/jogo | +0.165 | [-0.311; +0.641] |
| No alvo/jogo | -0.162 | [-0.477; +0.154] |
| Vitória mandante | -3.667 p.p. | [-8.950; +1.617] p.p. |
| Empate | +4.167 p.p. | [-0.682; +9.015] p.p. |
| Vitória visitante | -0.500 p.p. | [-5.316; +4.316] p.p. |

## Cabeçadas, conversão e xG

Referência suplementar PL 2019/20–2023/24: 2.713/7.198 cabeçadas no alvo (37.69%); 841/7.198 em gol (11.68%). Não representa o mesmo mix das cinco ligas.

| Corpo/versão | Tentativas observadas | No alvo | Em gol |
|---|---:|---:|---:|
| baseline/head | 2113 | 33.70% | 4.35% |
| baseline/foot | 12788 | 33.81% | 11.44% |
| baseline/right_foot | 365 | 42.47% | 12.05% |
| baseline/left_foot | 186 | 44.09% | 13.98% |
| baseline/knee | 8 | 12.50% | 0.00% |
| baseline/chest | 12 | 41.67% | 0.00% |
| baseline/shin | 4 | 0.00% | 0.00% |
| baseline/thigh | 24 | 50.00% | 12.50% |
| baseline/shoulder | 1 | 0.00% | 0.00% |
| spatial/foot | 12808 | 33.14% | 10.59% |
| spatial/left_foot | 179 | 40.78% | 17.32% |
| spatial/head | 2125 | 32.47% | 3.15% |
| spatial/right_foot | 437 | 38.44% | 12.81% |
| spatial/knee | 7 | 42.86% | 0.00% |
| spatial/thigh | 22 | 31.82% | 9.09% |
| spatial/chest | 14 | 28.57% | 0.00% |
| spatial/shoulder | 3 | 66.67% | 0.00% |
| spatial/shin | 3 | 0.00% | 0.00% |

baseline: gols/chutes 10.85%; no alvo/chutes 34.49%; xG/jogo 2.828; gols/xG 0.997. Ledger validado em cada partida. xG não foi comparado a uma definição externa incompatível.

Controle de cabeçadas vs pés dentro da área, células de pressão/perigo/xG com pelo menos 8 tentativas de cada grupo: {"matched_headers": 2080.0, "header_sot_rate": 0.3350961538461538, "matched_foot_sot_rate": 0.35509903447152774, "header_goal_rate": 0.04326923076923077, "matched_foot_goal_rate": 0.05602185758442562}. Comparação interna, sem referência real equivalente por célula.

spatial: gols/chutes 10.11%; no alvo/chutes 33.65%; xG/jogo 2.740; gols/xG 0.965. Ledger validado em cada partida. xG não foi comparado a uma definição externa incompatível.

Controle de cabeçadas vs pés dentro da área, células de pressão/perigo/xG com pelo menos 8 tentativas de cada grupo: {"matched_headers": 2037.0, "header_sot_rate": 0.32498772704958273, "matched_foot_sot_rate": 0.3515503404229248, "header_goal_rate": 0.031418753068237604, "matched_foot_goal_rate": 0.04302819900711042}. Comparação interna, sem referência real equivalente por célula.

## Coerência espacial e bola XYZ

Contadores de diagnóstico; os nomes não implicam infração às regras em todos os casos. Cabeçadas baixas podem existir, mas prevalência elevada de z=0 sugere falta de vínculo entre altura e contato.

| Observação | Contagem |
|---|---:|
| invalid_player_point | 0 |
| invalid_ball_xyz | 0 |
| speed_limit_violation | 0 |
| active_frame_count_mismatch | 0 |
| inactive_ball_owner | 0 |
| owner_ball_gap_over_2m | 0 |
| movement_samples | 4028414 |
| max_speed_mps | 7.746036 |
| spatial_frames | 205124 |
| airborne_frames | 1450 |
| live_flight_frames | 449 |
| max_ball_height | 7.026004 |
| shots_with_coordinates | 15598 |
| shot_distance_proxy_gap_over_10m | 11016 |
| box_labelled_shots | 10032 |
| box_label_outside_physical_penalty_area | 7804 |
| headers_with_height | 2125 |
| header_ball_height_below_0_5m | 2125 |

shot_metres: {"n": 15598, "mean": 37.179649207228394, "median": 36.03115709233174, "p95": 75.31461811567767, "max": 97.32632926614708}

zone_distance_absolute_error: {"n": 15598, "mean": 22.756713131801323, "median": 18.313984810828014, "p95": 57.90360250962263, "max": 81.16485486499816}

header_ball_height: {"n": 2125, "mean": 0.0, "median": 0.0, "p95": 0.0, "max": 0.0}

Diferença de distância superior a 10 m: 70.62% dos chutes com coordenadas.
Rótulo BOX fora da área física: 77.79% dos chutes rotulados BOX.
Cabeçadas com altura abaixo de 0,5 m: 100.00%; todas as alturas de contato monitoradas foram z=0.
Grade física: 240 trajetórias rasteiras/aéreas, sem falhas de gravidade/altura; 20 restaurações de voo com estado idêntico. Essas verificações não validam o contato de cabeceio nem distribuições de altura do futebol real.

Os movimentos têm um teto teórico de 8 m/s (28,8 km/h) para pace efetivo 100 e energia 1. O registro oficial da PL consultado já inclui 37,1 km/h. O máximo observado entre beats não estima pico instantâneo; mesmo o teto atual não cobre esses sprints de elite.

## Controles de mando e tempo

24 seeds iguais por modo e runtime. Experimento pequeno de sensibilidade: não é uma meta de resultados nem prova de calibração do mando.

| Runtime/modo | Jogos | Gols casa | Gols fora | Vitória casa | Acresc. 2ºT jogados | Anunciados | Gols 90+ público |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline/neutral | 24 | 1.083 | 1.125 | 41.67% | 7.641 min | 6.208 min | 9.43% |
| baseline/home_away | 24 | 1.792 | 1.000 | 50.00% | 8.096 min | 6.542 min | 7.46% |
| spatial/neutral | 24 | 0.917 | 0.625 | 41.67% | 6.866 min | 5.750 min | 10.81% |
| spatial/home_away | 24 | 1.375 | 0.958 | 45.83% | 7.736 min | 6.417 min | 7.14% |

Referência suplementar PL 2024/25: 6min32s efetivamente jogados no 2ºT e 8,4% dos gols em 90+. Acrescimos anunciados não são equivalentes aos minutos efetivamente jogados; o relógio bruto da engine inclui o acréscimo do 1ºT. Os controles corrigem essas diferenças de definição.

## Limites e próximos passos

- Validar primeiro a correspondência entre x/y e o setor usado para perigo, distância e finalização; não compensar essa incoerência com quotas de gols.
- Vincular recepção/cabeceio/contato à altura da bola e ao tempo de chegada.
- Usar tracking real compatível para validar percursos, velocidade, linhas de passe e distribuições de z; estatísticas finais não certificam esses aspectos.
- O motor não registra uma contagem completa de passes concluídos comparável aos 748 passes/jogo da PL 2024/25; os eventos de passe não servem como substituto dessa estatística.
- xG, lesões, goleiro 1v1 e segundas bolas permanecem diagnósticos internos quando não há base real comparável.
- Intervalos descritivos não corrigem testes múltiplos. Cabeçadas/tempo/velocidade usam bases suplementares com populações diferentes.

## Fontes

- [Match-level results/statistics, five leagues 2022/23–2024/25](https://github.com/datasets/football-datasets)
- [Premier League headed shots, 2019/20–2023/24](https://www.premierleague.com/en/news/4029745)
- [Premier League completed passes, 90+ goals and played added time in 2024/25](https://www.premierleague.com/en/news/4461793/what-are-the-biggest-trends-from-202526-so-far)
- [Premier League speed tracking after 29 matchweeks of 2024/25](https://www.premierleague.com/en/news/4272290)
- [IFAB Laws, field and goal geometry](https://www.theifab.com/laws/latest/the-field-of-play/)

## Reprodução

```bash
git worktree add --detach /tmp/amiguinhos-spatial-baseline d3c8d3dba8c8485cfbb6087ef33e645c7d2dd6dd
# Para cada i=0..3, início=108000+150*i; executar ambos os roots:
python audits/spatial_validation_20261104/run_audit.py --engine-root . --start-seed 108000 --count 150 --parity-check --output audits/spatial_validation_20261104/spatial_0.json
python audits/spatial_validation_20261104/run_audit.py --engine-root /tmp/amiguinhos-spatial-baseline --start-seed 108000 --count 150 --parity-check --output audits/spatial_validation_20261104/baseline_0.json
python audits/spatial_validation_20261104/run_controls.py --engine-root . --output audits/spatial_validation_20261104/controls_spatial.json
python audits/spatial_validation_20261104/run_controls.py --engine-root /tmp/amiguinhos-spatial-baseline --output audits/spatial_validation_20261104/controls_baseline.json
python audits/spatial_validation_20261104/summarise_audit.py
```

Os arquivos brutos baseline_*.json.gz e spatial_*.json.gz retêm seeds, confrontos, resultados, falhas e exemplos; gzip é apenas compressão sem perdas. O sumarizador aceita as versões .json e .json.gz.

Para reproduzir o runtime espacial exato, executar a partir da árvore 1908af7076844bce72c25b776f37592fbe3ce7c6 com estes scripts de auditoria. Um observador canônico foi comparado ao motor instrumentado no primeiro seed de cada runtime; export_state completo, eventos e RNG foram idênticos. Nenhum parâmetro de comportamento foi alterado nesta auditoria.
