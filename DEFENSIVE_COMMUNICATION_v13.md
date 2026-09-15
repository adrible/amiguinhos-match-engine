# v1.3 — Comunicação defensiva contextual

A comunicação defensiva não é um bônus coletivo e não cria uma segunda ação defensiva. Ela coordena **relações que já existem** no plano do lance.

## Escopo desta camada

A comunicação é ativada apenas quando existe uma relação concreta que precisa de coordenação:

- **handoff_call** — um marcador entrega um corredor para outro defensor;
- **cover_call** — um segundo defensor já foi escolhido para cobrir o espaço criado pela ação principal.

Sem handoff e sem cobertura ativa, a camada não concede qualquer ganho defensivo.

## Quem fala e quem recebe

O motor escolhe um comunicador contextual entre os defensores em campo, usando atributos existentes — principalmente antecipação, posicionamento, compostura e disciplina — além da função e da zona do campo.

Não foi criado um atributo oculto de “comunicação”.

O receptor é sempre o defensor que já faz parte da relação existente: o novo marcador em um handoff ou o defensor de cobertura.

## Qualidade da comunicação

A qualidade depende de:

- leitura defensiva do comunicador;
- prontidão do receptor;
- compactação e disponibilidade estrutural;
- transição;
- dificuldade/ocultação da corrida em handoffs;
- fadiga contextual já refletida nos atributos efetivos.

## Efeito mecânico

A comunicação só **modula levemente** o efeito da relação existente.

- comunicação limpa pode preservar um pouco mais do controle já produzido pelo handoff/cobertura;
- comunicação ruim pode degradar levemente esse controle;
- jamais cria uma marcação, cobertura, pressão ou bloqueio que não existia no plano;
- não altera atributos dos jogadores.

Isso evita o problema de empilhamento defensivo que a v1.3 foi desenhada para eliminar.

## Pipeline atualizado

localização
→ movimentação sem bola
→ antecipação
→ orientação corporal
→ geração de opções
→ criatividade
→ ousadia/contexto
→ decisão
→ resposta defensiva principal
→ marcação/handoff
→ cobertura
→ **comunicação da relação ativa**
→ execução
→ novo estado

## Próximo passo

A linha de impedimento poderá usar esta camada como fundação, porque uma subida coordenada da linha exige uma chamada compartilhada. A implementação futura deve continuar evitando tratar “comunicação” como bônus mágico de defesa.
