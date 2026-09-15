# 🦆 Amiguinhos Match Engine — v1.2 Stable

Motor de futebol orientado a eventos para simulação interativa no chat. A versão estável atual é **1.2**.

## Uso oficial

Para novas partidas, use o entrypoint estável:

```python
from stable_engine import MatchEngine
from team_loader import load_team

amiguinhos = load_team("amiguinhos_u21")
flamengo = load_team("flamengo_u21")

engine = MatchEngine(amiguinhos, flamengo, seed=12345)
```

`engine.py` contém a base estrutural da v0.2. As duas correções calibradas da v1.2 — sensibilidade moderada à diferença de qualidade e influência real de overlap dos laterais — são aplicadas pela implementação promovida em `stable_engine.py`.

## Princípios

1. O placar nunca é escolhido previamente.
2. Não existe meta por partida de gols, chutes ou chutes no alvo.
3. Situação, espaço e tática criam a chance; a finalização é resolvida depois.
4. Qualidade da chance importa mais que quantidade de finalizações.
5. xG descreve a situação; qualidade do finalizador e do goleiro influencia a conversão.
6. Tática altera espaço e risco; não existem bônus defensivos abstratos empilhados sem custo.
7. Pressão alta pode recuperar a bola, mas aumenta exposição quando é quebrada.
8. Linha alta comprime o campo, mas oferece profundidade.
9. Compactação fecha o centro, mas entrega largura.
10. Overlap aumenta a presença ofensiva do lateral e tem consequências espaciais.
11. Fadiga e cartões modificam jogadores, não o placar.
12. OVR influencia os duelos e o contexto, mas nunca determina sozinho o vencedor.
13. Seed reproduz exatamente a partida.
14. Estatísticas surgem dos eventos; elas nunca guiam a engine para uma meta.
15. O script gera os fatos; a narração fica fora do motor.
16. `advance_until_relevant()` implementa a lógica do comando `p`.

## Como funciona o `p`

```python
event = engine.advance_until_relevant()
```

Sem lance vivo, o motor processa internamente até o próximo evento relevante. Se existe `pending` ou `restart`, resolve apenas o próximo beat do mesmo lance.

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

## Intervenção do usuário

Durante um `pending`:

```python
engine.override_pending("cross", target="Gabriel Félix")
```

A ordem muda a decisão pretendida, não o resultado. A execução continua sendo calculada pela engine.

Ações suportadas incluem `shoot`, `cross`, `cutback`, `through_ball` e `dribble`.

## Alteração tática

```python
engine.set_tactics(
    0,
    pressing=0.75,
    defensive_line=0.62,
    mentality=0.35,
)
```

A mudança não reinicia o estado nem recalcula o passado.

## Elencos

Os times ficam em um único banco:

```text
data/teams.json
```

Carregamento:

```python
from team_loader import load_team, list_teams

team = load_team("amiguinhos_u21")
print(list_teams())
```

O banco atualmente contém os 16 clubes do Regional Internacional U21. Times com elenco conhecido usam jogadores explícitos; os demais podem usar geração genérica baseada na força cadastrada.

## Persistência

```python
payload = engine.export_json()
engine2 = MatchEngine.from_json(payload)
```

O estado completo inclui RNG, placar, posse, zona, fase, ações pendentes, estatísticas, energia, cartões, lesões e elencos em campo. A continuação restaurada é reproduzível se receber os mesmos comandos.

## Testes

```bash
python -m unittest -v test_engine.py test_engine_v12.py test_team_loader.py
```

O CI roda em Python 3.11 e 3.12, valida o JSON, compila as fontes, executa os testes e roda smoke simulations.

## Calibração v1.2

A v1.2 foi validada em uma bateria de **4.000 partidas** dos 🦆 Amiguinhos contra adversários OVR 75, 80, 83 e 84, repetida nos dois ambientes de Python do CI.

Contra OVR 84, o time OVR 75 ficou em aproximadamente:

- 21,9% vitórias;
- 23,2% empates;
- 54,9% derrotas.

A diferença de força é relevante, mas a zebra permanece possível em jogo único. A distribuição de qualidade das chances permaneceu praticamente igual à v1.1.

Detalhes completos: `CALIBRATION_AMIGUINHOS_v12.md`.

## Correções estruturais herdadas da v0.2

- formação altera ocupação, pressão e apoio;
- inferioridade numérica reduz cobertura e apoio;
- transições perdem força com o tempo;
- fadiga tem efeito real no fim da partida;
- inversão de perspectiva troca também esquerda/direita;
- bola enfiada preserva corredor/alvo entre impedimento e execução;
- defensor do lance é preservado durante a resolução quando ainda está em campo;
- segundo tempo começa com o lado oposto ao kickoff inicial;
- cartões, vermelho direto e lesões simples são persistentes;
- fases de jogo integram o estado;
- adaptação tática automática é opcional;
- estado pode ser salvo/restaurado exatamente via JSON.

### Decisão mantida conscientemente

O relógio pode ultrapassar levemente 45/90/120 antes do encerramento do período. Isso é intencional nesta versão e representa tolerância para conclusão do lance; não é tratado como erro estrutural.

## Status

**v1.2 = congelada para partidas oficiais.**

Arquivo `VERSION`: `1.2`.
