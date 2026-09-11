# Calibration — 🦆 Amiguinhos U21 v1.2 STABLE

Data: 2026-09-11

**Status:** APROVADA E CONGELADA  
**Release commit:** `7d938a4aa9d152c8a3c3689d08c1a81c84944f13`

## Objetivo

A v1.2 foi criada para atacar os dois pontos encontrados na calibração v1.1 sem dar qualquer bônus específico aos Amiguinhos:

1. aumentar moderadamente a sensibilidade global à diferença de qualidade técnica entre os jogadores envolvidos na fase do jogo;
2. fazer `overlap_left` / `overlap_right` influenciar de verdade a presença dos laterais na progressão e no terço final.

As mudanças foram primeiro isoladas em `engine_experiment_v12.py`, comparadas com a v1.1 e, após aprovação, expostas como versão estável por `stable_engine.py`.

## Validação final

A bateria final foi executada novamente a partir do entrypoint estável, em Python 3.11 e 3.12. Em ambos:

- JSON dos elencos válido;
- compilação concluída;
- **23 testes unitários/regressivos aprovados**;
- smoke test de 100 partidas aprovado;
- calibração de **4.000 partidas** concluída com sucesso.

Os resultados da calibração estável reproduziram exatamente os valores da candidata v1.2.

## v1.1 x v1.2

| Rival | W v1.1 | W v1.2 | D v1.1 | D v1.2 | L v1.1 | L v1.2 | GD v1.1 | GD v1.2 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| OVR 75 | 43,3% | **44,7%** | 25,8% | 26,5% | 30,9% | **28,8%** | +0,32 | **+0,37** |
| OVR 80 | 34,3% | **30,1%** | 24,4% | 25,2% | 41,3% | **44,7%** | -0,14 | **-0,34** |
| OVR 83 | 27,5% | **23,2%** | 24,2% | 23,0% | 48,3% | **53,8%** | -0,46 | **-0,74** |
| OVR 84 | 26,2% | **21,9%** | 23,7% | 23,2% | 50,1% | **54,9%** | -0,60 | **-0,86** |

A curva ficou mais aberta sem transformar diferença de qualidade em resultado obrigatório. Contra OVR 84, o adversário vence 54,9%, os Amiguinhos vencem 21,9% e 23,2% terminam empatados em 90 minutos: a zebra continua perfeitamente possível em jogo único.

## Produção por faixa — v1.2

| OVR rival | GF | GA | xGF | xGA | Chutes | Chutes contra | Grandes chances | Grandes contra | Posse |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 75 | 1,75 | 1,39 | 1,71 | 1,30 | 16,42 | 14,46 | 1,00 | 0,36 | 49,7% |
| 80 | 1,35 | 1,69 | 1,38 | 1,64 | 14,09 | 16,63 | 0,73 | 0,58 | 49,3% |
| 83 | 1,25 | 1,98 | 1,21 | 1,82 | 12,69 | 17,74 | 0,66 | 0,76 | 49,2% |
| 84 | 1,18 | 2,04 | 1,19 | 1,91 | 12,37 | 18,23 | 0,63 | 0,83 | 49,3% |

A progressão é monotônica: ao subir a força do rival, caem os chutes/xG dos Amiguinhos e sobem os chutes/xG sofridos. A posse praticamente não muda, de modo que a vantagem de qualidade emerge da eficiência espacial e dos duelos, não de uma posse artificial atribuída ao time mais forte.

## Qualidade das chances

- xG < 0,05: 40,6% (v1.1: 40,8%)
- xG 0,05–0,14: 33,6% (v1.1: 33,2%)
- xG 0,15–0,29: 20,1% (v1.1: 20,4%)
- xG >= 0,30: 5,7% (v1.1: 5,6%)

A correção da curva de força não foi obtida criando chances grandes artificialmente nem eliminando chutes ruins.

## White x Jorge

| Jogador | Envolvimento v1.1 | Envolvimento v1.2 | Criação v1.1 | Criação v1.2 | Chutes v1.2 |
|---|---:|---:|---:|---:|---:|
| Rodrigo White | 0,709 | **0,789** | 0,316 | **0,355** | 0,624 |
| Jorge Henrique | 0,760 | **0,686** | 0,380 | **0,349** | 0,493 |

A hierarquia espacial agora aparece na simulação: White participa mais de situações ofensivas e chega mais à finalização; Jorge aparece menos no terço final. A diferença nasce da instrução de overlap e da seleção espacial de atores/alvos, não de um bônus nominal a White.

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

Félix permanece em aproximadamente 4,08 finalizações por jogo, praticamente idêntico à v1.1. Valverde permanece o maior participante/criador de perigo, enquanto Adib e Mike mantêm perfil de criação mais forte que de volume de chutes.

## Origem das finalizações

Cruzamentos: 21,9% (v1.1: 21,6%). A mudança de overlap não provocou explosão artificial de cruzamentos, e as demais origens permaneceram próximas da distribuição anterior.

## Conclusão

A **v1.2 está oficialmente congelada como versão estável**. Ela melhora a curva de diferença de qualidade e diferencia corretamente White/Jorge sem regressão relevante na distribuição das chances, no papel de Félix ou na variedade ofensiva.

Para partidas oficiais, inclusive a final **🦆 Amiguinhos U21 x Flamengo U21**, o entrypoint canônico é `stable_engine.py`. Qualquer mudança futura deverá gerar uma nova revisão e passar novamente pela bateria de regressão/calibração antes de substituir esta versão.
