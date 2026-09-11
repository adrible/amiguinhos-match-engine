# Calibration — 🦆 Amiguinhos U21 v1.2 candidate

Data: 2026-09-11

## Objetivo

A v1.2 candidata foi criada para atacar os dois pontos encontrados na calibração v1.1 sem dar qualquer bônus específico aos Amiguinhos:

1. aumentar moderadamente a sensibilidade global à diferença de qualidade técnica entre os jogadores envolvidos na fase do jogo;
2. fazer a instrução de `overlap_left` / `overlap_right` influenciar de verdade a presença dos laterais na progressão e no terço final.

As mudanças foram implementadas primeiro em `engine_experiment_v12.py`, preservando `engine.py` intacto até a validação estatística.

## Método

Foram repetidas exatamente as mesmas 4.000 partidas da v1.1: 1.000 contra cada faixa OVR 75, 80, 83 e 84, alternando estilos e mando e reutilizando a mesma lógica de seeds. A bateria foi executada em Python 3.11 e 3.12; os dois jobs concluíram com sucesso.

## v1.1 x v1.2

| Rival | W v1.1 | W v1.2 | D v1.1 | D v1.2 | L v1.1 | L v1.2 | GD v1.1 | GD v1.2 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| OVR 75 | 43,3% | **44,7%** | 25,8% | 26,5% | 30,9% | **28,8%** | +0,32 | **+0,37** |
| OVR 80 | 34,3% | **30,1%** | 24,4% | 25,2% | 41,3% | **44,7%** | -0,14 | **-0,34** |
| OVR 83 | 27,5% | **23,2%** | 24,2% | 23,0% | 48,3% | **53,8%** | -0,46 | **-0,74** |
| OVR 84 | 26,2% | **21,9%** | 23,7% | 23,2% | 50,1% | **54,9%** | -0,60 | **-0,86** |

A curva ficou mais aberta sem transformar diferença de qualidade em resultado obrigatório. Contra OVR 84, por exemplo, o adversário agora vence 54,9% e os Amiguinhos 21,9%, ainda preservando uma probabilidade real de zebra em jogo único.

## Produção por faixa — v1.2

| OVR rival | GF | GA | xGF | xGA | Chutes | Chutes contra | Grandes chances | Grandes contra | Posse |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 75 | 1,75 | 1,39 | 1,71 | 1,30 | 16,42 | 14,46 | 1,00 | 0,36 | 49,7% |
| 80 | 1,35 | 1,69 | 1,38 | 1,64 | 14,09 | 16,63 | 0,73 | 0,58 | 49,3% |
| 83 | 1,25 | 1,98 | 1,21 | 1,82 | 12,69 | 17,74 | 0,66 | 0,76 | 49,2% |
| 84 | 1,18 | 2,04 | 1,19 | 1,91 | 12,37 | 18,23 | 0,63 | 0,83 | 49,3% |

A progressão é monotônica: ao subir a força do rival, caem os chutes/xG dos Amiguinhos e sobem os chutes/xG sofridos. A posse praticamente não muda, o que é desejável: a vantagem de qualidade aparece sobretudo na eficiência espacial e na capacidade de transformar posse em situações melhores, não por uma posse artificialmente atribuída ao time mais forte.

## Qualidade das chances

A distribuição permaneceu praticamente estável em relação à v1.1:

- xG < 0,05: 40,6% (v1.1: 40,8%)
- xG 0,05–0,14: 33,6% (v1.1: 33,2%)
- xG 0,15–0,29: 20,1% (v1.1: 20,4%)
- xG >= 0,30: 5,7% (v1.1: 5,6%)

Isto é importante: a correção da curva de força não foi obtida criando mais chances grandes de forma artificial nem eliminando chutes ruins.

## White x Jorge

| Jogador | Envolvimento v1.1 | Envolvimento v1.2 | Criação v1.1 | Criação v1.2 | Chutes v1.2 |
|---|---:|---:|---:|---:|---:|
| Rodrigo White | 0,709 | **0,789** | 0,316 | **0,355** | 0,624 |
| Jorge Henrique | 0,760 | **0,686** | 0,380 | **0,349** | 0,493 |

A hierarquia espacial agora aparece na simulação: White participa mais de situações ofensivas e chega mais à finalização; Jorge aparece menos no terço final, preservando seu perfil mais conservador/inteligente. A diferença foi obtida pela instrução de overlap e pela seleção espacial de atores/alvos, não por um bônus nominal a White.

## Perfil ofensivo v1.2

| Jogador | Chutes | xG | Gols | Envolvimento em perigo | Perigos criados |
|---|---:|---:|---:|---:|---:|
| Gabriel Félix | 4,077 | 0,403 | 0,470 | 1,945 | 0,628 |
| Pedro Valverde | 2,251 | 0,221 | 0,255 | 2,235 | 1,119 |
| Remo | 1,731 | 0,174 | 0,207 | 1,901 | 0,745 |
| Gabriel Adib | 1,087 | 0,106 | 0,125 | 1,695 | 1,049 |
| Mike Junior | 1,016 | 0,098 | 0,116 | 1,564 | 0,954 |
| Rodrigo White | 0,624 | 0,070 | 0,079 | 0,789 | 0,355 |
| Jorge Henrique | 0,493 | 0,053 | 0,055 | 0,686 | 0,349 |
| Felipe | 0,452 | 0,045 | 0,045 | 0,704 | 0,416 |

Félix continua em 4,08 finalizações por jogo, praticamente idêntico à v1.1 (4,081). Portanto a correção não aumentou a dependência do centroavante. Valverde permanece o maior participante/criador de perigo, enquanto Adib e Mike continuam com perfil de criação mais forte do que de volume de chutes.

## Origem das finalizações

Os cruzamentos ficaram em 21,9% (v1.1: 21,6%), portanto a mudança de overlap não provocou explosão artificial de cruzamentos. As demais origens também permaneceram próximas da distribuição anterior.

## Conclusão

A candidata v1.2 melhora os dois pontos que motivaram a revisão:

- a diferença de qualidade entre equipes passa a ter efeito mais nítido, sem definir previamente o vencedor;
- White e Jorge passam a ocupar funções ofensivas claramente diferentes.

Não houve regressão relevante na distribuição de qualidade das chances, no papel de Félix ou na variedade das origens das finalizações. A candidata pode ser promovida para a engine principal após a incorporação das mudanças e uma última bateria de regressão.
