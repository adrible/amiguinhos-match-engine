# v1.3 communication integration notes

- Nova camada: `engine_experiment_v13_communication.py`.
- Herda `MatchEngineV13Cover`; portanto não substitui `engine.py` nem a v1.2 estável.
- O entrypoint canônico `engine_experiment_v13.py` passa a apontar para `MatchEngineV13Communication`.
- Comunicação só existe para uma relação defensiva já selecionada: handoff ou cobertura.
- Handoff tem precedência quando handoff e cobertura coexistem no mesmo beat, para não empilhar duas chamadas independentes.
- O efeito da comunicação é uma correção pequena do efeito existente, não um novo bônus defensivo.
- Não usa RNG adicional e não altera atributos; seeds continuam determinísticas.
- Testes específicos cobrem: cover call, handoff call, ausência de bônus gratuito, qualidade por leitura defensiva, limite de magnitude, imutabilidade de atributos e reprodutibilidade.
- CI v1.3 deve compilar e executar `test_defensive_communication.py` em Python 3.11 e 3.12 antes de qualquer promoção.
