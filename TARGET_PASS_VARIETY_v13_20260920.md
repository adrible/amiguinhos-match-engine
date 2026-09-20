# Alvos do chute e passes criativos — 20/09/2026

Motor geral v1.3; base remota `13598c157a4420a14c3d715a514af9be71b6e39a`.

## O que mudou

O meio alto agora é uma intenção explícita, distinta do meio à meia-altura. Alvos altos, médios e baixos podem escolher ambos os lados: 72% das escolhas laterais desse grupo preferem o lado exposto pelo goleiro e 28% o outro. Esses pesos são parâmetros de decisão, não frequências reais medidas. Esquerda/direita são vistas pelo atacante. `intended_shot_region` registra a intenção e `actual_shot_region` o resultado da execução. A região escolhida afeta erro e distância da defesa; não é apenas narração.

A mistura geométrica de referência da conversão foi atualizada para contemplar o meio alto, mantendo a dispersão 1,80 e sem alterar o xG da situação. Cabeçada para baixo agora define também a coordenada horizontal coerente com seu alvo, evitando reaproveitar o x de uma intenção anterior.

Já existiam chutes colocados, fortes, rasteiros, cruzados, voleios, de primeira, coberturas, cabeçadas, bicos, trivelas e entre as pernas. A revisão amplia a escolha espacial; não torna essas técnicas garantias de gol.

Passes disponíveis: trivela, rabona, calcanhar, no-look, disfarçado, cavadinha, com efeito e de primeira. A devolução de calcanhar foi acrescentada. De primeira e devolução exigem plano de recepção do mesmo jogador e zona, com modo first_time. A rabona tem menor peso de escolha, especialmente com técnica baixa. As demais técnicas são ponderadas pela dificuldade, em vez de sorteio equiprovável. Criatividade e ousadia definem propensão; técnica, visão, composure e pressão afetam execução. Sucesso técnico modifica pressão/espaço/qualidade defensiva usados no lance, mas não garante passe completo. Corta-luz permanece uma ação sem toque própria do módulo de recepção.

A narração deve usar região pretendida como intenção, respeitar a posição real e o desfecho, e nunca transformar execução da técnica em passe completo automaticamente.

## Evidência de variedade

Teste controlado de 3.000 oportunidades com jogador habilidoso: oito regiões intencionais observadas, incluindo meio alto, dois ângulos, dois cantos baixos e meia-altura dos dois lados. Nove técnicas de passe observadas: 136 trivelas tentadas, 21 rabonas, 113 calcanhares, 112 devoluções de calcanhar, 153 de primeira, 118 no-look, 133 disfarçados, 121 cavadinhas e 124 com efeito. Foram observados 11 tipos de finalização neste cenário. São oportunidades sintéticas, não frequências por partida e não comparação com taxas reais dessas técnicas. Dados em `controlled_variety.json`.

## Comparação e limites

Referência: 5.329 jogos das cinco grandes ligas, 2022/23–2024/25, [Football-Data via football-datasets](https://github.com/datasets/football-datasets). São agregados de ligas; o índice neutro exclui métricas direcionais de mando, xG e cronologia.

Parâmetros definidos antes da execução, sem busca entre candidatos: 300 jogos por versão nas seeds 95000–95299, mais 100 por versão nas seeds 95000–95099 com a ordem dos mesmos times invertida. Todas as 800 simulações foram preservadas.

| Métrica por jogo | Real | Antes | Depois |
|---|---:|---:|---:|
| Gols | 2.825 | 2.777 | 2.777 |
| Chutes | 25.275 | 26.957 | 26.880 |
| No alvo | 8.878 | 9.183 | 9.060 |
| Faltas | 23.839 | 24.863 | 25.583 |
| Amarelos | 4.138 | 3.657 | 3.987 |
| Vermelhos | 0.194 | 0.233 | 0.210 |
| Empates | 25.20% | 23.00% | 31.67% |
| 0–0 | 6.06% | 8.33% | 9.67% |

Índice principal: **84,52 → 81,85**. Diagnóstico invertido: **76,69 → 71,45**, com gols 2,96 → 2,57 e 0–0 5% → 12%. A integração atende à variedade espacial e à coerência das técnicas; não constitui melhora global do índice. Empates, 0–0 e dispersão entre amostras continuam como limitações explícitas. Não se alterou a conversão após observar esses resultados.

773 execuções de testes passaram (incluem sete casos reaproveitados por importação). Novos testes garantem alvos intencionais dos dois lados, restrição das técnicas de primeira à recepção correta e raridade relativa da rabona.

## Reprodução

```bash
python compare_general_engine_v13.py --baseline /caminho/base --cache /caminho/cache --output audits/repro/holdout/comparison.json --matches 300 --start-seed 95000 --workers 4 --neutral
python compare_general_engine_v13.py --baseline /caminho/base --cache /caminho/cache --output audits/repro/mirrored/comparison.json --matches 100 --start-seed 95000 --workers 2 --neutral --mirror
python variety_diagnostics_v13.py --output audits/repro/controlled_variety.json
```

Hashes, partidas e testes: `audits/variety_20260920/`.
