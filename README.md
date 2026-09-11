# Amiguinhos Match Engine — v0.2

Segunda versão funcional do motor de futebol pensado para uso interativo no chat, com correções estruturais de estabilidade após auditoria da v0.1.

## Princípios

1. O placar nunca é escolhido previamente.
2. Não existe meta por partida de gols, chutes ou chutes no alvo.
3. A situação cria a chance; depois a chance é finalizada.
4. Qualidade da chance importa mais que quantidade de finalizações.
5. xG descreve a situação; qualidade do finalizador e do goleiro ajustam a conversão depois.
6. Tática altera espaço e risco. Não existem "bônus defensivos" empilhados sem custo.
7. Pressão alta pode recuperar a bola, mas aumenta exposição quando é quebrada.
8. Linha alta comprime o campo, mas oferece profundidade.
9. Compactação fecha o centro, mas entrega largura.
10. Overlap cria apoio ofensivo, mas aumenta exposição em transição.
11. Fadiga afeta atributos gradualmente.
12. OVR não decide lances sozinho.
13. Seed reproduz exatamente a partida.
14. O script gera fatos; a narração fica fora do motor.
15. `advance_until_relevant()` implementa a lógica do comando `p`.

## Como funciona o `p`

```python
event = engine.advance_until_relevant()
```

Se não há lance vivo, o motor processa internamente até o próximo evento com relevância suficiente.

Se já existe `pending` ou `restart`, a chamada resolve somente o próximo "beat" do lance. Assim um perigo, rebote, escanteio ou falta não é pulado inteiro em uma única chamada.

Exemplo conceitual:

```text
p
-> DANGER: atacante recebe entrando na área
p
-> SAVE: goleiro defende e segura
```

ou:

```text
p
-> DANGER
p
-> REBOUND
p
-> GOAL / SAVE / BLOCK / MISS
```

## Uso mínimo

```python
from engine import MatchEngine, make_generic_team

a = make_generic_team("Azul", 75, "balanced", seed=1)
b = make_generic_team("Vermelho", 75, "attacking", seed=2)

engine = MatchEngine(a, b, seed=12345)

while not engine.state.ended:
    event = engine.advance_until_relevant()
    print(event)
```

## Alteração tática durante a partida

```python
engine.set_tactics(
    0,
    pressing=0.75,
    defensive_line=0.62,
    mentality=0.35,
)
```

A mudança não recalcula o passado nem reinicia o estado.

## Intervenção do usuário em lance vivo

Quando existe um `pending`:

```python
engine.override_pending("cross", target="Centroavante")
```

A ordem do usuário muda a decisão, mas o motor ainda calcula se a execução funciona.

Opções nesta versão:

- `shoot`
- `cross`
- `cutback`
- `through_ball`
- `dribble`

## Substituição

```python
engine.substitute(0, "Jogador A", "Jogador B")
```

Substituições são bloqueadas enquanto existe uma ação `pending` com a bola viva, evitando referências inválidas no meio do lance. Em prorrogação, a configuração padrão permite uma substituição adicional.

## Estatísticas e persistência

```python
print(engine.snapshot())
```

`snapshot()` é JSON-safe e inclui placar, posse, zona, fase, formação, xG, chutes, no alvo, grandes chances, escanteios, faltas, cartões, impedimentos, defesas, entradas no último terço e energia.

Para salvar e restaurar a partida exatamente, inclusive o estado do RNG:

```python
payload = engine.export_json()
engine2 = MatchEngine.from_json(payload)
```

A continuação de `engine2` será idêntica à de `engine` se ambos receberem os mesmos comandos.

## `match_flow`

Cada seed também gera um `match_flow`, exposto no snapshot.

Ele muda **a cadência dos acontecimentos**, não escolhe placar ou número de chutes. Isso permite que existam partidas naturalmente lentas ou caóticas sem impor uma quota estatística. Tática e decisões continuam determinando a qualidade das situações.

## Testes

```bash
python -m unittest -v test_engine.py
```

## Diagnóstico em lote

```bash
python diagnostics.py 1000
```

O diagnóstico observa o comportamento agregado sem usar essas médias como meta dentro de uma partida.

## Correções estruturais da v0.2

- formação passa a alterar ocupação de linhas, pressão e apoio;
- inferioridade numérica reduz cobertura e apoio de forma explícita;
- transições perdem força com o tempo, mesmo sem uma ação específica consumi-las;
- fadiga foi recalibrada para produzir efeito real no fim da partida;
- inversão de perspectiva troca também esquerda/direita;
- bola enfiada usa o mesmo corredor/alvo para impedimento e execução;
- defensor associado ao lance é preservado até a resolução, quando ainda está em campo;
- segundo tempo começa com o lado oposto ao kickoff inicial;
- cartões agora geram eventos próprios, com possibilidade de vermelho direto;
- lesões simples persistentes foram adicionadas;
- fases (`build_up`, `progression`, `final_third`, `chance_creation`, `transition`, `restart`) agora fazem parte do estado;
- adaptação tática automática opcional foi adicionada;
- persistência completa e reprodutível via JSON.

### Decisão mantida conscientemente

O relógio ainda pode ultrapassar levemente 45/90/120 antes de o motor encerrar o período. Isso foi mantido deliberadamente nesta versão: funciona como uma tolerância simples de encerramento do lance e não será tratado como erro estrutural por enquanto.

## Ainda fora do escopo

- notas individuais pós-jogo;
- roles específicas por jogador além da posição;
- clima, gramado e perfil detalhado do árbitro;
- elenco oficial dos Amiguinhos U21.
