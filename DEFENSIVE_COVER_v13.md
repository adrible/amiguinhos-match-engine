# v1.3 candidate — coberturas defensivas contextuais

## Conceito

Cobertura não é um segundo "bônus defensivo" e não substitui a intenção primária.
Ela descreve a relação entre o defensor que sai para a ação e um segundo defensor
que protege especificamente o espaço criado por essa saída.

Fluxo:

`intenção defensiva principal -> organização de marcação -> cobertura estrutural -> execução`

Exemplos:

- volante pressiona o portador -> zagueiro protege profundidade;
- lateral contém o ponta -> volante/zagueiro fecha o corredor interno;
- lateral salta para bloquear cruzamento -> outro defensor protege cutback/área;
- zagueiro acompanha uma corrida -> companheiro protege a zona abandonada.

## Regras de segurança

- continua existindo exatamente uma intenção defensiva principal;
- existe no máximo uma cobertura contextual por beat;
- o cobridor precisa ser diferente do defensor principal e do marcador ativo;
- se a intenção primária já for uma ação de segurança (`cover_depth`, `protect_box`,
  `block_shot`, `close_cutback`, `delay`), nenhuma segunda cobertura é empilhada;
- cobertura depende de compactação, disponibilidade de jogadores, transição e
  organização de marcação;
- marcação individual estrita reduz a disponibilidade para coberturas;
- uma troca de marcação em andamento cobra pequeno custo de coordenação;
- cobertura nunca modifica atributos de atacantes ou defensores.

## Trade-offs

A cobertura tenta reparar um custo criado pela ação principal, não transformar a
defesa em uma barreira sem custo:

- cobertura de profundidade reduz parte da exposição criada pela pressão;
- cobertura interna fecha passe por dentro, mas concede um pouco de largura;
- proteção de cutback melhora o corredor de retorno/área, mas tira pressão direta
  do portador e desloca um defensor;
- proteção da zona abandonada melhora o equilíbrio, mas reduz pressão imediata.

## Estado

A camada estende `MatchEngineV13Marking` em `engine_experiment_v13_cover.py`.
A v1.2 estável permanece intocada.
