# v1.3 — Erro defensivo contextual

A camada de erro defensivo não existe para “criar gols”. O placar continua sendo consequência do lance.

## Princípio

O motor primeiro monta normalmente a defesa:

resposta principal
→ marcação/handoff
→ cobertura
→ comunicação
→ linha de impedimento
→ reação a overload

Somente depois é calculada a dificuldade real de execução do defensor concreto naquele momento.

## De onde surge o risco

O risco de falha emerge de fatores existentes no estado:

- posicionamento;
- antecipação;
- compostura;
- disciplina;
- desarme;
- velocidade;
- fadiga/energia;
- transição;
- espaço disponível ao ataque;
- espaço nas costas;
- apoio ofensivo;
- disponibilidade defensiva;
- inferioridade numérica local;
- qualidade de handoff;
- qualidade da comunicação;
- zona e tipo da ação;
- cartão amarelo e relação agressividade/disciplina em pequena escala.

Não foi criado um atributo oculto “erro”.

## Diagnóstico x realização

O perfil de risco é determinístico. Funções de diagnóstico não consomem RNG.

Durante uma ação viva, a janela defensiva usa no máximo **um único sorteio contextual**. Se o mesmo lance passa por várias subetapas, elas compartilham esse sorteio e no máximo uma falha pode ser realizada naquela janela. Isso impede cascatas artificiais de erros independentes no mesmo lance.

Seed igual continua devendo reproduzir a mesma partida.

## Tipos contextuais

O tipo mais coerente é escolhido pelo estado, não sorteado para produzir variedade:

- **bad_handoff** — troca de marcação mal executada;
- **lost_runner** — defensor perde o corredor;
- **overcommit** — defensor salta/pressiona e é batido;
- **wrong_lane_read** — leitura incorreta da linha de passe;
- **late_block** — chegada atrasada ao bloqueio;
- **poor_body_position** — orientação corporal ruim no duelo.

## O erro altera o duelo, não o resultado

Uma falha realizada pode, por exemplo:

- reduzir pressão;
- aumentar espaço;
- abrir profundidade;
- reduzir controle do corredor;
- reduzir controle da linha de passe;
- enfraquecer proteção de chute/cruzamento.

Ela **não** concede gol, chute, assistência, turnover ou vitória diretamente. Depois da falha, o motor ainda executa normalmente a decisão ofensiva e a resolução do lance.

## Comunicação e overload

Boa comunicação pode reduzir um pouco a incerteza de uma relação que já precisava de coordenação. Comunicação ruim, handoff difícil e overload aumentam a carga cognitiva/espacial e, portanto, podem elevar o risco de execução.

Isso não transforma comunicação em buff coletivo nem inferioridade numérica em penalidade fixa: tudo permanece contextual ao lance.

## Próximas etapas

Após CI e smoke, a candidata ainda precisa de:

- química/compreensão entre jogadores, se implementada como comportamento e não bônus mágico;
- adaptação tática durante o jogo;
- atributos específicos dos jogadores no banco;
- calibração ampla por comportamento;
- persistência/restore v1.3 e runner interativo `p` antes da final oficial.
