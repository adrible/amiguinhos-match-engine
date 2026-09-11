# Calibration — 🦆 Amiguinhos U21 v1.1

Data: 2026-09-11

## Método

Foram simuladas 4.000 partidas, 1.000 por faixa de força adversária: OVR 75, 80, 83 e 84. Os estilos adversários foram alternados entre balanced, attacking, defensive, pressing e direct. O lado casa/fora também foi alternado. A mesma bateria foi executada no CI em Python 3.11 e 3.12 e ambos os jobs concluíram com sucesso.

## Resultado por faixa

| OVR rival | W | D | L | GF | GA | xGF | xGA | Chutes | Chutes contra | Grandes chances | Grandes contra | Posse |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 75 | 43,3% | 25,8% | 30,9% | 1,69 | 1,36 | 1,63 | 1,31 | 16,06 | 14,62 | 0,90 | 0,35 | 49,7% |
| 80 | 34,3% | 24,4% | 41,3% | 1,43 | 1,57 | 1,40 | 1,59 | 14,09 | 16,48 | 0,75 | 0,52 | 49,4% |
| 83 | 27,5% | 24,2% | 48,3% | 1,32 | 1,78 | 1,29 | 1,69 | 13,22 | 17,12 | 0,74 | 0,63 | 49,2% |
| 84 | 26,2% | 23,7% | 50,1% | 1,23 | 1,83 | 1,23 | 1,73 | 12,79 | 17,39 | 0,64 | 0,67 | 49,3% |

## Qualidade das finalizações dos Amiguinhos

- xG < 0,05: 40,8%
- xG 0,05–0,14: 33,2%
- xG 0,15–0,29: 20,4%
- xG >= 0,30: 5,6%

A distribuição não indica retorno do antigo problema de “ataques que morrem sempre em circulação neutra”. Há uma mistura real de tentativas fracas, médias e claras, e a qualidade varia de acordo com o contexto.

## Origem das finalizações

- open play: 36,4%
- cruzamentos: 21,6%
- bolas enfiadas: 11,1%
- cutbacks: 8,0%
- rebotes: 6,1%
- progressão: 4,2%
- faltas: 3,2%
- escanteios: 2,9%
- transições: 2,9%
- conduções: 2,2%
- segunda bola: 0,8%
- pênaltis: 0,4%
- drible direto: 0,1%

## Perfil ofensivo individual

Valores por partida, somando todas as faixas de adversário.

| Jogador | Chutes | xG | Gols | Envolvimento em perigo | Perigos criados |
|---|---:|---:|---:|---:|---:|
| Gabriel Félix | 4,081 | 0,406 | 0,474 | 1,972 | 0,650 |
| Pedro Valverde | 2,312 | 0,225 | 0,266 | 2,314 | 1,133 |
| Remo | 1,782 | 0,177 | 0,211 | 1,977 | 0,787 |
| Mike Junior | 1,048 | 0,105 | 0,125 | 1,612 | 0,971 |
| Gabriel Adib | 1,082 | 0,104 | 0,124 | 1,709 | 1,070 |
| Rodrigo White | 0,546 | 0,062 | 0,065 | 0,709 | 0,316 |
| Jorge Henrique | 0,553 | 0,060 | 0,065 | 0,760 | 0,380 |
| Felipe | 0,459 | 0,045 | 0,051 | 0,719 | 0,438 |
| João Peixoto | 0,163 | 0,018 | 0,019 | 0,205 | 0,102 |
| Léo | 0,160 | 0,015 | 0,019 | 0,227 | 0,123 |
| Christian | 0,027 | 0,001 | 0,001 | 0,030 | 0,013 |

## Leitura técnica

### O que está funcionando

1. A engine diferencia a força do adversário: conforme o OVR rival sobe, caem xG, chutes e taxa de vitória dos Amiguinhos, enquanto aumentam xGA e chutes sofridos.
2. O time não depende de uma quota de chutes ou gols. A bateria produz distribuição de qualidade variada e resultados emergentes.
3. Valverde aparece como o jogador com maior envolvimento em situações perigosas e maior criação de perigo.
4. Adib aparece mais como criador do que finalizador, coerente com seu perfil híbrido.
5. Mike também aparece fortemente na criação, enquanto Remo participa bastante da fase final.
6. Félix é claramente a referência ofensiva e principal finalizador.
7. O perfil agressivo do time, em especial a presença de Felipe, se reflete em mais faltas/cartões que os adversários na média.

### Pontos a corrigir antes da final

1. **A curva global de diferença de força parece comprimida.** Um time nominalmente 75 ainda vence 26,2% das partidas contra OVR 84 e evita a derrota em 49,9%. A correção deve ser feita na sensibilidade global de atributos/duelos, não nerfando especificamente os Amiguinhos.
2. **White x Jorge ainda não está diferenciado o suficiente.** White deveria emergir como lateral claramente mais ofensivo e Jorge como lateral mais conservador/inteligente. No benchmark, Jorge ainda teve ligeiramente mais envolvimento e criação de perigo que White. Isso indica que overlap e perfil individual ainda influenciam pouco a seleção de atores por corredor.
3. **Félix concentra 4,08 finalizações por partida.** Como pivô e alvo aéreo isso é coerente em parte, mas deve ser acompanhado para garantir que ele não esteja absorvendo finalizações em excesso por causa dos pesos posicionais genéricos.
4. Cruzamentos representam 21,6% de todas as finalizações dos Amiguinhos. É compatível com Félix como alvo aéreo, mas merece teste específico por jogador e corredor antes de ser considerado definitivo.

## Conclusão

A v1.1 eliminou o comportamento de baixa produção ofensiva que motivou a troca do motor manual. O problema prioritário agora não é “falta de chances”, e sim refinar a curva global de força e a identidade espacial/funcional de jogadores específicos. A final contra o Flamengo não deve ser simulada oficialmente antes desses dois pontos serem revisados.
