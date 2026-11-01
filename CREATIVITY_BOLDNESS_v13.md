# v1.3 Candidate — criatividade + ousadia (risk/reward)

## Princípio

A v1.3 separa duas capacidades que antes poderiam ser confundidas:

- **Criatividade**: perceber uma opção boa que não é óbvia.
- **Ousadia / boldness**: aceitar uma opção percebida que oferece mais recompensa, mas tem execução mais difícil.

Nenhum dos dois atributos melhora passe, técnica, drible ou finalização.

## Fluxo da decisão

1. A posição no campo e o contexto geram as opções normais.
2. O motor avalia receptores evidentes e possíveis corridas ocultas.
3. A criatividade define a probabilidade de **perceber** a melhor corrida oculta; essa percepção não recebe bônus de `risk`/ousadia.
4. Se ela for percebida, o **tipo da ação e o alvo ficam vinculados no mesmo lance** (ex.: passe em profundidade → Remo), evitando escolher a ideia criativa e depois mirar outro jogador.
5. Então o motor compara:
   - recompensa projetada;
   - chance estimada de execução;
   - custo de perder a bola naquela zona;
   - placar/minuto;
   - risco tático;
   - ousadia do jogador.
6. A ousadia pode aceitar um pequeno déficit de valor esperado quando a recompensa potencial é materialmente maior.
7. Existe uma trava rígida: uma opção claramente ruim continua rejeitada mesmo com ousadia 100.
8. A execução real permanece separada e usa os atributos técnicos normais.

## Exemplo

Félix e Valverde atraem a defesa. Remo ataca um espaço cego.

- Um jogador de criatividade baixa pode nem perceber Remo.
- Adib, Mike e Jorge podem percebê-lo.
- Adib, com ousadia alta, aceita com mais frequência uma janela apertada se o passe puder criar uma chance grande.
- Mike e Jorge podem enxergar exatamente o mesmo lance, mas preferir a solução mais segura quando o custo da perda for alto.

Isso não significa que Adib toma decisões estúpidas. A opção oculta precisa primeiro ser uma alternativa real de alto valor e precisa passar pela trava de sanidade de risco.

## Perfis iniciais sugeridos para calibração

Estes valores são ponto de partida, não quotas e ainda precisam de calibração:

| Jogador | Criatividade | Ousadia |
|---|---:|---:|
| Gabriel Adib | 88 | 86 |
| Mike Junior | 85 | 60 |
| Jorge Henrique | 80 | 52 |

A diferença desejada é comportamental, não um bônus oculto de resultado.

## Contexto

A tolerância ao risco é espacial e situacional:

- própria defesa: risco criativo praticamente bloqueado;
- meio: moderado;
- terço final: maior liberdade;
- área adversária: recompensa alta, mas decisões ainda dependem do ângulo e da pressão;
- perdendo no fim: tolerância aumenta;
- vencendo no fim: tolerância diminui.

## Persistência

`creativity`, `boldness` e o alias `ousadia` são preservados no `export_json()` / `from_json()` da engine candidata.

## Estado

A v1.2 oficial permanece intacta. Esta é uma candidata v1.3 e não deve substituir a versão estável antes de:
- integração com o banco real de equipes;
- calibração do elenco;
- testes sobre a engine v1.2 estável no CI;
- diagnóstico específico Amiguinhos x Flamengo.
