# v1.3 — Overloads locais 2x1 / 3x2

A camada de overloads trata superioridade numérica como um problema de geometria local, não como um modificador abstrato de ataque ou defesa.

## Como o overload nasce

O portador conta como o primeiro atacante. A partir daí, o motor consulta as movimentações sem bola que já existem no pipeline e identifica até dois apoios realmente relevantes para a mesma zona imediata.

Uma corrida só entra na conta se:

- sua projeção estiver na mesma faixa local ou em apoio interior coerente;
- ocorrer no horizonte imediato do lance;
- sua qualidade/timing forem suficientes para obrigar a defesa a respeitá-la.

Assim, um jogador parado longe da jogada não transforma artificialmente um lance em 2x1 ou 3x2.

## Quem conta como defensor

Só contam defensores que já estejam realmente comprometidos na geometria do plano:

- defensor primário;
- marcador, se for outro jogador;
- defensor de cobertura, se a cobertura estiver ativa.

O comunicador não vira um quarto defensor virtual. Comunicação apenas coordena uma relação existente.

## Respostas defensivas

Quando atacantes locais superam os defensores comprometidos, a defesa escolhe uma resposta:

- **split_difference** — o defensor divide a atenção entre portador e receptor;
- **pull_helper** — um jogador real e ainda não comprometido é puxado para ajudar;
- **delay_and_screen** — a defesa temporiza e protege linhas de progressão em vez de atacar imediatamente a bola.

A escolha depende da qualidade do defensor primário, compactação, transição, espaço em profundidade, pressão atual, gravidade da inferioridade e existência/qualidade de um helper real.

## Regra central: redistribuir, não empilhar

A inferioridade numérica primeiro reduz a capacidade de controlar simultaneamente portador, corredor, linha de passe, drible e área.

A resposta escolhida pode redistribuir parte desse controle, porém sempre cobra um preço espacial:

- menos pressão imediata;
- mais espaço para o portador;
- exposição de profundidade;
- ou abertura do corredor/área abandonada pelo helper.

Mesmo `pull_helper` não cria defesa grátis: o jogador sai de outra zona para equilibrar o local.

Portanto, um 2x1 ou 3x2 pode ser bem defendido, mas a defesa não pode melhorar todas as dimensões ao mesmo tempo apenas porque reconheceu o overload.

## Pipeline atualizado

resposta defensiva principal
→ marcação/handoff
→ cobertura
→ comunicação
→ linha de impedimento quando aplicável
→ **reconhecimento e redistribuição do overload local**
→ execução

## Próximo passo

Depois da validação em CI e smoke, o próximo sistema defensivo planejado é **erro defensivo contextual**, fazendo falhas emergirem de pressão, fadiga, dificuldade, orientação, comunicação e qualidade do jogador — sem sorteio arbitrário de “erro para gerar gol”.
