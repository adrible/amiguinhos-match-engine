# v1.3 — Linha de impedimento contextual

A v1.3 substitui, somente na candidata, a probabilidade simplificada de impedimento usada pela base em bolas enfiadas por uma decisão estrutural da linha defensiva.

## Respostas possíveis

Para uma ameaça de profundidade, a linha escolhe uma resposta coerente com o estado do lance:

- **step_up** — sobe coordenadamente para tentar deixar o corredor impedido;
- **hold_line** — mantém a linha e controla timing sem uma armadilha agressiva;
- **drop_and_track** — recua e acompanha a profundidade, praticamente abrindo mão do ganho de impedimento.

A escolha não usa quota de impedimentos. Ela emerge de altura da linha, compactação, coordenação dos defensores, pressão sobre o passador, transição, espaço nas costas e características da corrida.

## Coordenação da linha

A coordenação deriva dos jogadores que realmente formam a última linha — normalmente zagueiros e laterais, com volante como apoio quando necessário — considerando:

- posicionamento;
- antecipação;
- compostura;
- disciplina;
- velocidade;
- energia/fadiga;
- qualidade média;
- elo mais fraco;
- dispersão entre os membros da linha;
- compactação coletiva;
- disponibilidade defensiva.

Um zagueiro ou goleiro pode assumir a chamada de linha conforme leitura e função. Não foi criado atributo oculto de “impedimento” ou “comunicação”.

## Corrida do atacante

A linha reage ao corredor concreto. O timing ofensivo usa atributos existentes e, quando disponível, a movimentação sem bola que já foi gerada pelo pipeline:

- off-ball;
- antecipação;
- velocidade;
- compostura;
- timing da corrida;
- hiddenness / ataque ao ponto cego;
- projeção de curto horizonte.

Assim, um corredor inteligente pode atacar a mesma linha de modo muito diferente de um jogador que parte cedo ou lê mal o espaço.

## Risco real da armadilha

`step_up` não é bônus gratuito.

Se a chamada funciona, existe chance contextual de impedimento. Se o atacante fica em condição, a subida fracassada:

- aumenta o espaço nas costas;
- aumenta levemente o espaço imediato do ataque;
- reduz a pressão instantânea.

Ou seja, a mesma decisão defensiva que pode encerrar o lance também pode piorar a situação se for batida.

`hold_line` e `drop_and_track` não recebem esse ganho artificial de proteção: são respostas diferentes, com riscos diferentes.

## Integração com a v1.3

Pipeline defensivo relevante:

resposta defensiva principal
→ marcação/handoff
→ cobertura
→ comunicação
→ **decisão da linha de impedimento para ameaça de profundidade**
→ execução

A camada só substitui o tratamento de impedimento de `through_ball` na candidata. `engine.py` e a v1.2 congelada permanecem inalterados.

## Próximo passo

Depois de validar CI e smoke, a evolução natural é reação a **overloads 2x1 / 3x2**, usando a mesma filosofia: redistribuir responsabilidades e espaço, nunca empilhar bônus defensivos abstratos.
