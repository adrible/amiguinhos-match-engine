# v1.3 Candidate — movimentação sem bola + antecipação espacial

Esta camada complementa adaptação espacial, criatividade e ousadia.

## Separação de responsabilidades

- **Movimentação sem bola**: cria a corrida ou ocupação de espaço.
- **Antecipação**: melhora o timing e permite que a corrida útil se forme mais cedo.
- **Criatividade**: permite ao portador perceber uma corrida boa que não é óbvia.
- **Ousadia**: decide se vale aceitar uma janela mais difícil em troca de recompensa maior.
- **Passe/técnica/finalização**: executam a ideia; não recebem bônus escondido.

## Regra estrutural

Cada jogador sem a bola recebe **uma única intenção ativa por beat**. Isso impede que um mesmo atleta cubra simultaneamente zonas desconectadas.

Intenções possíveis incluem apoio, aproximação, entrelinhas, profundidade, diagonal, corrida no ponto cego, terceiro homem, overlap, underlap, ataque à área, segundo pau, chegada tardia e apoio para cutback.

## Projeção curta

O motor projeta a posição útil aproximadamente **0,7 a 2,3 segundos à frente**. Jogadores com melhor `off_ball` e `anticipation` sincronizam a corrida mais cedo; pressão alta piora o timing.

## Exemplo

Félix e Valverde ocupam os defensores pelo centro. Remo, com bom `off_ball`, antecipação e velocidade, pode gerar uma `blind_side_run` para o espaço oposto. Essa corrida existe independentemente de Adib percebê-la.

Se Adib tiver criatividade alta, aumenta a chance de a opção entrar no conjunto percebido. Depois, ousadia/placar/risco avaliam se a janela vale ser usada. A execução continua dependendo dos atributos técnicos normais.

## Sem teleporte tático

No próprio terço defensivo, um atacante pode oferecer apoio ou iniciar progressão, mas não é projetado diretamente para a área adversária. A progressão respeita a banda atual do campo.

## Efeito no jogo

Movimento visível influencia levemente a escolha normal de receptor. Corridas muito escondidas são amortecidas na escolha comum e dependem da camada de criatividade para serem explicitamente descobertas.

Quando uma boa movimentação gera uma situação perigosa, ela pode melhorar modestamente a qualidade **da situação criada**, sem melhorar a execução do passe. `hiddenness` por si só não oferece bônus.

## Estado

Continua sendo candidata v1.3. A v1.2 estável permanece intocada até integração no repositório, CI e nova calibração.
