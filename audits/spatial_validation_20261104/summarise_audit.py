"""Summarise retained paired samples and real reference data, without tuning."""
from collections import Counter, defaultdict
import csv
import hashlib
import gzip
import json
import math
from pathlib import Path
import statistics as st
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from real_match_benchmark_v13 import load_real_collection, SOURCE_FILE, summarise_matches, compare

HERE = Path(__file__).resolve().parent
real_rows, datasets = load_real_collection(SOURCE_FILE, ROOT / '.cache/real_match_benchmark')
real = summarise_matches(real_rows)

def read_json(path):
    if path.exists():
        return json.loads(path.read_text())
    return json.loads(gzip.decompress(path.with_suffix('.json.gz').read_bytes()))


def per_match(row):
    h, a = row['home_goals'], row['away_goals']
    return {
        'goals_per_match': h+a, 'home_goals_per_match': h, 'away_goals_per_match': a,
        'shots_per_match': row['home_shots']+row['away_shots'],
        'sot_per_match': row['home_sot']+row['away_sot'],
        'fouls_per_match': row['home_fouls']+row['away_fouls'],
        'corners_per_match': row['home_corners']+row['away_corners'],
        'yellow_per_match': row['home_yellow']+row['away_yellow'],
        'red_per_match': row['home_red']+row['away_red'],
        'home_win_rate': int(h>a), 'draw_rate': int(h==a), 'away_win_rate': int(h<a),
        'zero_zero_rate': int(h==0 and a==0), 'btts_rate': int(h>0 and a>0),
        'over_2_5_rate': int(h+a>=3), 'clean_sheet_rate': int(h==0 or a==0),
    }


def interval(values):
    mean = st.mean(values)
    margin = 1.96*st.stdev(values)/math.sqrt(len(values)) if len(values)>1 else 0.
    return {'mean': mean, 'low95': mean-margin, 'high95': mean+margin, 'n': len(values)}


def distribution(values):
    if not values:
        return {'n': 0}
    values = sorted(values)
    return {'n': len(values), 'mean': st.mean(values), 'median': st.median(values),
            'p95': values[math.floor(.95*(len(values)-1))], 'max': max(values)}


all_data = {}
for label in ('baseline', 'spatial'):
    chunks = [read_json(HERE / f'{label}_{i}.json') for i in range(4)]
    records = sorted([r for c in chunks for r in c['matches']], key=lambda r:r['seed'])
    failures = [r for c in chunks for r in c['failures']]
    expected_seeds = list(range(108000, 108600))
    if failures or [r['seed'] for r in records] != expected_seeds:
        raise RuntimeError(f'{label}: incomplete sample; failures={failures}')
    if not chunks[0]['parity_checked']:
        raise RuntimeError('Observer parity was not verified')
    counts = Counter()
    if label == 'spatial':
        for key in ('invalid_player_point','invalid_ball_xyz','speed_limit_violation',
                    'active_frame_count_mismatch','inactive_ball_owner','owner_ball_gap_over_2m'):
            counts[key] = 0
    distances = defaultdict(list)
    groups, cells = defaultdict(Counter), defaultdict(Counter)
    for c in chunks:
        for name, value in c['spatial_counts'].items():
            counts[name] = max(counts[name], value) if name.startswith('max_') else counts[name]+value
        for name, values in c['spatial_distances'].items():
            distances[name].extend(values)
        for key, value in c['shot_groups'].items(): groups[key].update(value)
        for key, value in c['shot_cells'].items(): cells[key].update(value)
    summary = summarise_matches([r['stats'] for r in records])
    extra_keys = sorted({k for r in records for k in r['extra']})
    extras = {key: interval([r['extra'].get(key, 0) for r in records]) for key in extra_keys}
    body = {}
    for part, g in groups.items():
        n = g['attempts']
        body[part] = {**g, 'sot_rate': g['sot']/n, 'goal_rate': g['goals']/n,
                      'goal_share': g['goals']/max(1., summary['metrics']['goals_per_match']*len(records)), 'mean_xg': g['xg']/n}
    combined_cells = defaultdict(lambda: defaultdict(Counter))
    for name, values in cells.items():
        body_part, cell = name.split('|', 1)
        if body_part in ('head', 'foot', 'left_foot', 'right_foot'):
            combined_cells[cell]['head' if body_part=='head' else 'foot'].update(values)
    matched_n = head_sot = head_goals = weighted_foot_sot = weighted_foot_goals = 0.
    for by_body in combined_cells.values():
        h, f = by_body['head'], by_body['foot']
        if h['attempts'] >= 8 and f['attempts'] >= 8:
            matched_n += h['attempts']
            head_sot += h['sot']
            head_goals += h['goals']
            weighted_foot_sot += h['attempts']*f['sot']/f['attempts']
            weighted_foot_goals += h['attempts']*f['goals']/f['attempts']
    matched = {'matched_headers': matched_n,
               'header_sot_rate': head_sot/matched_n if matched_n else None,
               'matched_foot_sot_rate': weighted_foot_sot/matched_n if matched_n else None,
               'header_goal_rate': head_goals/matched_n if matched_n else None,
               'matched_foot_goal_rate': weighted_foot_goals/matched_n if matched_n else None}
    all_data[label] = {'commit': chunks[0]['engine_commit'], 'records': records,
                       'summary': summary, 'comparison': compare(real, summary, datasets),
                       'extras': extras, 'spatial_counts': counts,
                       'distances': {k:distribution(v) for k,v in distances.items()},
                       'body_parts': body, 'cells': cells, 'matched_box_headers':matched,
                       'examples': [r for c in chunks for r in c['spatial_examples']][:40]}

paired = {}
for key in per_match(all_data['spatial']['records'][0]['stats']):
    b = [per_match(r['stats'])[key] for r in all_data['baseline']['records']]
    s = [per_match(r['stats'])[key] for r in all_data['spatial']['records']]
    paired[key] = {'baseline': interval(b), 'spatial': interval(s),
                   'difference_spatial_minus_baseline': interval([y-x for x,y in zip(b,s)]),
                   'real': real['metrics'][key]}

controls = {}
for label in ('baseline', 'spatial'):
    raw = json.loads((HERE / f'controls_{label}.json').read_text())
    controls[label] = {}
    for mode in ('neutral', 'home_away'):
        rows = [r for r in raw['matches'] if r['mode']==mode]
        controls[label][mode] = {
            'matches': len(rows), 'home_goals': st.mean(r['score'][0] for r in rows),
            'away_goals': st.mean(r['score'][1] for r in rows),
            'home_win_rate': st.mean(r['score'][0]>r['score'][1] for r in rows),
            'away_win_rate': st.mean(r['score'][0]<r['score'][1] for r in rows),
            'first_added_played': interval([r['first_added_played'] for r in rows]),
            'second_added_played': interval([r['second_added_played'] for r in rows]),
            'second_added_announced': interval([r['second_added_announced'] for r in rows]),
            'late_goal_share_public': sum(r['goals_90plus_public'] for r in rows)/sum(sum(r['score']) for r in rows),
        }

sources = [
    {'name': 'Match-level results/statistics, five leagues 2022/23–2024/25',
     'url': 'https://github.com/datasets/football-datasets', 'upstream': 'https://www.football-data.co.uk/',
     'matches': len(real_rows)},
    {'name': 'Premier League headed shots, 2019/20–2023/24', 'url':'https://www.premierleague.com/en/news/4029745',
     'attempts':7198, 'on_target':2713, 'goals':841},
    {'name':'Premier League completed passes, 90+ goals and played added time in 2024/25',
     'url':'https://www.premierleague.com/en/news/4461793/what-are-the-biggest-trends-from-202526-so-far',
     'completed_passes_per_match':748,'late_goal_share':.084,'second_added_played':6+32/60},
    {'name':'Premier League speed tracking after 29 matchweeks of 2024/25',
     'url':'https://www.premierleague.com/en/news/4272290','fastest_observed_kmh':37.1},
    {'name':'IFAB Laws, field and goal geometry', 'url':'https://www.theifab.com/laws/latest/the-field-of-play/',
     'goal_width_m':7.32,'goal_height_m':2.44,'penalty_area_depth_m':16.5},
]
physics = json.loads((HERE/'physics_controls.json').read_text())
bootstrap_path = HERE/'index_bootstrap.json'
bootstrap = json.loads(bootstrap_path.read_text()) if bootstrap_path.exists() else None
result = {'date':'2026-11-04', 'seed_range':[108000,108599], 'matches_per_runtime':600,
          'controlled_matches_total':96, 'reference':real,
          'reference_by_league_season':datasets, 'sources':sources,
          'paired_comparison':paired,
          'engines':{k:{field:value for field,value in v.items() if field!='records'} for k,v in all_data.items()},
          'controls':controls, 'physics_controls':physics, 'index_bootstrap':bootstrap,
          'real_csv_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in (ROOT/'.cache/real_match_benchmark').glob('*.csv')},
          'limits':[
              'Synthetic strength/style populations, not replays of real clubs.',
              'Scalar 95% intervals are descriptive normal approximations, not adjusted for multiple testing.',
              'The realism index is the repository diagnostic, not a probability of a realistic match.',
              'Headers/added-time/speed references have narrower league/season scopes than the core sample.',
              'Recorded engine pass events are not a complete completed-pass statistic.',
              'No external player/ball tracking collection validates path or height distributions.',
              'Speed measured over event clock increments underestimates instantaneous peak speed.',
              'Both the original announced/raw-clock timing and corrected public/played-time controls are retained.',
          ]}
(HERE/'summary.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')

names = {
 'goals_per_match':'Gols/jogo','shots_per_match':'Chutes/jogo','sot_per_match':'No alvo/jogo',
 'fouls_per_match':'Faltas/jogo','corners_per_match':'Escanteios/jogo','yellow_per_match':'Amarelos/jogo',
 'red_per_match':'Vermelhos/jogo','home_goals_per_match':'Gols mandante/jogo','away_goals_per_match':'Gols visitante/jogo',
 'home_win_rate':'Vitória mandante','draw_rate':'Empate','away_win_rate':'Vitória visitante',
 'zero_zero_rate':'0–0','btts_rate':'Ambos marcam','over_2_5_rate':'3 ou mais gols','clean_sheet_rate':'Ao menos um time sem sofrer gol'}
lines = ['# Auditoria da camada espacial — 04/11/2026','',
         '**Conclusão:** as métricas finais da camada espacial ficaram menos próximas da base real nesta amostra e há incoerências concretas entre setores, coordenadas de finalização e altura de cabeceio. A camada precisa dessas correções antes da validação espacial. A queda do índice, isoladamente, não é estatisticamente conclusiva.', '',
         'Amostra retida: 600 partidas por runtime, seeds contíguas 108000–108599, mesmos elencos, forças, estilos e mando; mais 96 controles de força igual. Nenhuma seed foi filtrada. A seed oficial não foi utilizada.', '',
         f"Referência principal: {len(real_rows)} partidas reais, cinco ligas, temporadas 2022/23 a 2024/25.", '',
         f"Baseline: `{all_data['baseline']['commit']}`. Espacial: `{all_data['spatial']['commit']}`.", '',
         '| Parâmetro | Real | Anterior | Espacial | Espacial − real |','|---|---:|---:|---:|---:|']
for key, name in names.items():
    b, s, r = all_data['baseline']['summary']['metrics'][key], all_data['spatial']['summary']['metrics'][key], real['metrics'][key]
    rate = key.endswith('_rate')
    f = (lambda v:f'{100*v:.2f}%') if rate else (lambda v:f'{v:.3f}')
    delta = f'{100*(s-r):+.2f} p.p.' if rate else f'{s-r:+.3f}'
    lines.append(f'| {name} | {f(r)} | {f(b)} | {f(s)} | {delta} |')
lines += ['', '## Índice e mudança pareada','',
          f"Índice diagnóstico: anterior {all_data['baseline']['comparison']['realism_index']:.2f}/100; espacial {all_data['spatial']['comparison']['realism_index']:.2f}/100. Não é uma porcentagem de acerto nem certificação física.",'',
          '| Métrica | Espacial − anterior | IC 95% da diferença pareada |','|---|---:|---:|']
if bootstrap:
    low, high = bootstrap['difference_spatial_minus_baseline_95_percentile']
    lines[-2:-2] = [f'Bootstrap pareado descritivo do índice (1.000 reamostragens): IC percentil 95% da diferença espacial−anterior [{low:.2f}; {high:.2f}] pontos. Inclui zero; o tamanho amostral e a sensibilidade do índice impedem tratar a queda observada como prova isolada de regressão populacional.', '']
for key in ('goals_per_match','shots_per_match','sot_per_match','home_win_rate','draw_rate','away_win_rate'):
    d = paired[key]['difference_spatial_minus_baseline']; factor = 100 if key.endswith('_rate') else 1
    suffix = ' p.p.' if factor==100 else ''
    lines.append(f"| {names[key]} | {factor*d['mean']:+.3f}{suffix} | [{factor*d['low95']:+.3f}; {factor*d['high95']:+.3f}]{suffix} |")
lines += ['', '## Cabeçadas, conversão e xG','',
          f"Referência suplementar PL 2019/20–2023/24: 2.713/7.198 cabeçadas no alvo ({2713/7198:.2%}); 841/7.198 em gol ({841/7198:.2%}). Não representa o mesmo mix das cinco ligas.", '',
          '| Corpo/versão | Tentativas observadas | No alvo | Em gol |','|---|---:|---:|---:|']
for label in ('baseline','spatial'):
    for body, row in all_data[label]['body_parts'].items():
        lines.append(f"| {label}/{body} | {row['attempts']} | {row['sot_rate']:.2%} | {row['goal_rate']:.2%} |")
for label in ('baseline','spatial'):
    d=all_data[label];m=d['summary']['metrics']; xg=d['extras']['xg']['mean']
    lines += ['',f"{label}: gols/chutes {m['goals_per_match']/m['shots_per_match']:.2%}; no alvo/chutes {m['sot_per_match']/m['shots_per_match']:.2%}; xG/jogo {xg:.3f}; gols/xG {m['goals_per_match']/xg:.3f}. Ledger validado em cada partida. xG não foi comparado a uma definição externa incompatível."]
    lines += ['',f"Controle de cabeçadas vs pés dentro da área, células de pressão/perigo/xG com pelo menos 8 tentativas de cada grupo: {json.dumps(d['matched_box_headers'], ensure_ascii=False)}. Comparação interna, sem referência real equivalente por célula."]
lines += ['', '## Coerência espacial e bola XYZ','', 'Contadores de diagnóstico; os nomes não implicam infração às regras em todos os casos. Cabeçadas baixas podem existir, mas prevalência elevada de z=0 sugere falta de vínculo entre altura e contato.', '', '| Observação | Contagem |','|---|---:|']
for key,value in all_data['spatial']['spatial_counts'].items():
    lines.append(f'| {key} | {value:.6f} |' if key.startswith('max_') else f'| {key} | {value} |')
for key,value in all_data['spatial']['distances'].items():
    lines += ['',f"{key}: {json.dumps(value, ensure_ascii=False)}"]
counts=all_data['spatial']['spatial_counts']
lines += ['',
          f"Diferença de distância superior a 10 m: {counts['shot_distance_proxy_gap_over_10m']/counts['shots_with_coordinates']:.2%} dos chutes com coordenadas.",
          f"Rótulo BOX fora da área física: {counts['box_label_outside_physical_penalty_area']/counts['box_labelled_shots']:.2%} dos chutes rotulados BOX.",
          f"Cabeçadas com altura abaixo de 0,5 m: {counts['header_ball_height_below_0_5m']/counts['headers_with_height']:.2%}; todas as alturas de contato monitoradas foram z=0.",
          f"Grade física: {physics['cases']} trajetórias rasteiras/aéreas, sem falhas de gravidade/altura; {physics['midflight_restore_cases']} restaurações de voo com estado idêntico. Essas verificações não validam o contato de cabeceio nem distribuições de altura do futebol real."]
lines += ['', 'Os movimentos têm um teto teórico de 8 m/s (28,8 km/h) para pace efetivo 100 e energia 1. O registro oficial da PL consultado já inclui 37,1 km/h. O máximo observado entre beats não estima pico instantâneo; mesmo o teto atual não cobre esses sprints de elite.', '',
          '## Controles de mando e tempo','',
          '24 seeds iguais por modo e runtime. Experimento pequeno de sensibilidade: não é uma meta de resultados nem prova de calibração do mando.', '',
          '| Runtime/modo | Jogos | Gols casa | Gols fora | Vitória casa | Acresc. 2ºT jogados | Anunciados | Gols 90+ público |','|---|---:|---:|---:|---:|---:|---:|---:|']
for label, modes in controls.items():
    for mode, d in modes.items():
        lines.append(f"| {label}/{mode} | {d['matches']} | {d['home_goals']:.3f} | {d['away_goals']:.3f} | {d['home_win_rate']:.2%} | {d['second_added_played']['mean']:.3f} min | {d['second_added_announced']['mean']:.3f} min | {d['late_goal_share_public']:.2%} |")
lines += ['', 'Referência suplementar PL 2024/25: 6min32s efetivamente jogados no 2ºT e 8,4% dos gols em 90+. Acrescimos anunciados não são equivalentes aos minutos efetivamente jogados; o relógio bruto da engine inclui o acréscimo do 1ºT. Os controles corrigem essas diferenças de definição.', '',
          '## Limites e próximos passos','',
          '- Validar primeiro a correspondência entre x/y e o setor usado para perigo, distância e finalização; não compensar essa incoerência com quotas de gols.',
          '- Vincular recepção/cabeceio/contato à altura da bola e ao tempo de chegada.',
          '- Usar tracking real compatível para validar percursos, velocidade, linhas de passe e distribuições de z; estatísticas finais não certificam esses aspectos.',
          '- O motor não registra uma contagem completa de passes concluídos comparável aos 748 passes/jogo da PL 2024/25; os eventos de passe não servem como substituto dessa estatística.',
          '- xG, lesões, goleiro 1v1 e segundas bolas permanecem diagnósticos internos quando não há base real comparável.',
          '- Intervalos descritivos não corrigem testes múltiplos. Cabeçadas/tempo/velocidade usam bases suplementares com populações diferentes.', '',
          '## Fontes','']
for s in sources: lines.append(f"- [{s['name']}]({s['url']})")
lines += ['', '## Reprodução','', '```bash',
          'git worktree add --detach /tmp/amiguinhos-spatial-baseline d3c8d3dba8c8485cfbb6087ef33e645c7d2dd6dd',
          '# Para cada i=0..3, início=108000+150*i; executar ambos os roots:',
          'python audits/spatial_validation_20261104/run_audit.py --engine-root . --start-seed 108000 --count 150 --parity-check --output audits/spatial_validation_20261104/spatial_0.json',
          'python audits/spatial_validation_20261104/run_audit.py --engine-root /tmp/amiguinhos-spatial-baseline --start-seed 108000 --count 150 --parity-check --output audits/spatial_validation_20261104/baseline_0.json',
          'python audits/spatial_validation_20261104/run_controls.py --engine-root . --output audits/spatial_validation_20261104/controls_spatial.json',
          'python audits/spatial_validation_20261104/run_controls.py --engine-root /tmp/amiguinhos-spatial-baseline --output audits/spatial_validation_20261104/controls_baseline.json',
          'python audits/spatial_validation_20261104/summarise_audit.py', '```', '',
          'Os arquivos brutos baseline_*.json.gz e spatial_*.json.gz retêm seeds, confrontos, resultados, falhas e exemplos; gzip é apenas compressão sem perdas. O sumarizador aceita as versões .json e .json.gz.', '',
          'Para reproduzir o runtime espacial exato, executar a partir da árvore 1908af7076844bce72c25b776f37592fbe3ce7c6 com estes scripts de auditoria. Um observador canônico foi comparado ao motor instrumentado no primeiro seed de cada runtime; export_state completo, eventos e RNG foram idênticos. Nenhum parâmetro de comportamento foi alterado nesta auditoria.']
(HERE/'REPORT.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
print('baseline index',all_data['baseline']['comparison']['realism_index'])
print('spatial index',all_data['spatial']['comparison']['realism_index'])
print('spatial counts',all_data['spatial']['spatial_counts'])
