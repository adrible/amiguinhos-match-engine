# Auditoria de estabilidade — Amiguinhos Match Engine v0.1

## Status
A v0.1 compila e os 6 testes existentes passam, mas ainda não deve ser usada como versão oficial da final. A auditoria encontrou problemas estruturais reais.

## Achados críticos / alta prioridade

### P0 — `match_flow` controla volume demais
Em 3.000 partidas equilibradas (75 x 75):
- mínimo: 5 finalizações totais
- máximo: 66 finalizações totais
- 3,03% tiveram 50+ finalizações
- 1,93% tiveram 8+ gols
- jogos com `match_flow < 0.5`: média de 11,78 finalizações
- jogos com `match_flow > 1.5`: média de 45,51 finalizações

Conclusão: `match_flow` deixou de ser apenas ritmo e virou um multiplicador excessivo de volume.

### P0 — faltas em qualquer zona viram bola levantada para a área
`_resolve_restart()` trata quase toda falta que não seja cobrança direta como `cross`, inclusive faltas no terço defensivo e no meio-campo.

Em 500 partidas auditadas, ocorreram `free_kick_delivery_pending` após:
- 1.089 faltas no terço defensivo
- 1.678 faltas no meio
- 1.304 faltas no terço final

Isso cria perigo artificial e distorce volume de chances.

### P0 — defensor persistente é ignorado na resolução
`PendingAction.defender` é armazenado, mas `_resolve_pending()` e `_resolve_shot()` escolhem outro defensor com `_choose_defender()`.

Consequência: o zagueiro/lateral envolvido na jogada pode “sumir” e outro defensor aparecer na finalização.

### P1 — inversão de corredor está errada na troca de posse
`Zone.mirror()` inverte o terço, mas preserva `LEFT/RIGHT`. Como os corredores são relativos ao time atacante, uma perda no lado esquerdo deveria virar transição pelo lado direito do novo atacante.

### P1 — vazamento de estado tático entre partidas
`MatchEngine` guarda o mesmo objeto `Team` recebido. `set_tactics()` altera `team.tactics` no objeto original.

Teste:
- motor 1 altera pressing para `0.99`
- motor 2 criado depois com o mesmo `Team`
- motor 2 começa com pressing `0.99`

Isso contamina baterias de testes e partidas subsequentes.

### P1 — pênaltis de disputa usam `EventType.GOAL` sem mudar o placar
`take_shootout_penalty()` emite `GOAL`, mas não altera `TeamStats.goals`.

Isso é correto para não misturar disputa com placar da partida, porém cria inconsistência para consumidores que contem eventos `GOAL`.

### P1 — qualidade da finalização ainda é espacialmente grosseira
O xG usa principalmente:
- `Band` (DEF/MID/ATT/BOX)
- corredor
- origem da jogada
- danger
- pressure

Ainda não existem distância e ângulo explícitos. Duas finalizações muito diferentes dentro da área podem receber contexto parecido. Para um motor em que qualidade vale mais do que volume, isso precisa melhorar.

## Achados médios

- Restarts, rebotes e sequências de perigo praticamente não avançam o relógio.
- Não há adaptação automática do adversário ao placar/minuto.
- Não há lesões.
- Não há vermelho direto.
- `EventType.CARD` existe, mas atualmente não é usado como evento separado.
- Override do usuário permite alvos pouco plausíveis (inclusive o próprio ator/GK).
- A posição do jogador é uma string única, insuficiente para jogadores multi-posição dos Amiguinhos.
- Trocas na prorrogação não adicionam automaticamente uma substituição extra.
- Final-third entries não capturam todos os tipos de entrada por transição.

## Testes executados

- `python -m py_compile`: OK
- suíte existente: 6/6 OK
- 1.000 partidas com forças/estilos variados: 0 exceções / invariantes básicos OK
- 1.500 partidas em confrontos táticos específicos: 0 exceções

Exemplo — pressing 75 x balanced 75 (300 jogos):
- 3,71 gols/jogo
- 33,13 finalizações/jogo
- 3,55 xG/jogo
- apenas 1,7% de 0–0

Isso reforça que pressão + `match_flow` está inflando demais o ritmo em parte das seeds.

## Recomendação para v0.2

Corrigir antes de cadastrar os Amiguinhos:
1. reduzir/remodelar `match_flow`;
2. diferenciar reinícios profundos, intermediários e perigosos;
3. persistir defensor e geometria da jogada;
4. corrigir espelhamento dos corredores;
5. copiar estado de `Team/Tactics` ao iniciar uma partida;
6. criar eventos próprios para disputa de pênaltis;
7. introduzir `ShotContext` com distância, ângulo, pressão, equilíbrio, body part e tipo de assistência;
8. ampliar testes de propriedades e distribuição sem impor metas de chutes/gols.
