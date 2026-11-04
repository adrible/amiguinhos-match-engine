# Calibração espacial — 4 de novembro de 2026

Motor em eventos com movimentação limitada por tempo e velocidade; não é um simulador contínuo de colisões.

## Referências e separação das amostras

- Football-Data.co.uk, via datasets/football-datasets: 5.329 jogos das cinco grandes ligas, temporadas 2022/23, 2023/24 e 2024/25. Totais de gols, chutes, alvo, faltas, escanteios, cartões e resultados.
- **StatsBomb Open Data**: Copa do Mundo 2022, 64 partidas. Origem, distância, abertura do gol, corpo, pressão e xG dos chutes. Sem disputas por pênaltis; pênaltis separados do ajuste geométrico. Dados: https://github.com/statsbomb/open-data. Marca e atribuição: https://statsbomb.com/media-pack/.
- Escala StatsBomb 120×80 normalizada para 105×68: distâncias aproximadas, não medições do estádio. Copa e ligas são populações diferentes; não há garantia de igualdade das distribuições.
- Modelo: 48 partidas para ajuste de entropia cruzada com xG StatsBomb como rótulo contínuo; sinais dos coeficientes restringidos. Outras 16 partidas usadas como diagnóstico. Não é uma réplica do modelo proprietário StatsBomb.
- Ajustes de movimentação/cadência: pilotos apenas em sementes 108000–108599, já disponíveis na auditoria anterior. Houve iterações; esses pilotos não são avaliação independente.
- Avaliação final: sementes **112000–112599**, contíguas, sem seleção por resultado; mesmos elencos, atributos, estilos e mando nas duas versões. Parâmetros congelados antes de ler os resultados dessa amostra. Semente oficial permanece em quarentena.

## Mudanças causais

A intenção de uma jogada orienta a corrida do ator e do receptor dentro do orçamento de deslocamento disponível. A posição física define a zona e a distância usadas na finalização, dispersão e resposta do goleiro. Peso de recepção considera se o jogador consegue chegar ao espaço pretendido. Distância e ângulo entram no xG; finalização e goleiro continuam na execução.

Cruzamentos preservam `creator`. Contato aéreo exige entrega identificada ou bola aérea fornecida por tracking; o voo consome tempo e o evento registra a altura de contato. Contatos corporais incompatíveis com a bola no chão viram finalizações de pé. Corredores de escanteio mantêm intenção até a cobrança, com jogadores de cobertura; alvos e rebotes ponderam proximidade física. A circulação usa 90% da duração anterior porque parte da preparação agora tem tempo explícito.

## Reprodução

```bash
python calibration/spatial_20261104/build_shot_reference.py
python -m unittest test_v13_coordinate_play test_v13_coordinates
python calibration/spatial_20261104/run_sensitivity.py /tmp/sensitivity.json
python calibration/spatial_20261104/run_audit.py --engine-root . --start-seed 112000 --count 150 --output /tmp/after_0.json --parity-check
```

O ajuste da referência requer NumPy/SciPy; o motor utiliza somente a biblioteca padrão e o JSON versionado. Os eventos brutos StatsBomb ficam em cache, sem serem incorporados ao repositório. Os hashes dos 64 arquivos usados acompanham o modelo. O relatório final, dados comprimidos e scripts de agregação ficam nesta pasta.
