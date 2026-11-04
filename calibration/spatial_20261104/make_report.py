"""Render the retained validation evidence into a reviewable Portuguese report."""
from pathlib import Path
import json
HERE=Path(__file__).parent
s=json.loads((HERE/'summary.json').read_text());old=s['cohorts']['before'];new=s['cohorts']['after'];real=s['real'];ref=s['shot_reference']
count=new['n'];start=s['validation']['start_seed'];end=start+count-1
lines=[]
def add(text=''):lines.append(text)
def table(headers,rows):
 add('| '+' | '.join(headers)+' |');add('| '+' | '.join('---' for _ in headers)+' |')
 for row in rows:add('| '+' | '.join(str(v) for v in row)+' |')
 add()
def number(x):return f'{x:.2f}'
def percent(x):return f'{100*x:.1f}%'
add('# Validação da calibração espacial v1.3')
add()
add('A calibração corrige a ligação entre jogadas, posições e finalizações. A distância usada no chute passa a vir do campo, os receptores precisam alcançar o espaço pretendido e cabeceios exigem bola aérea. A conclusão estatística sobre proximidade com as ligas está abaixo; o índice do repositório é uma heurística, não uma porcentagem de acerto do futebol real.')
add()
add('## Amostras e versão congelada')
add()
add(f'- **{count} partidas novas em cada versão**, sementes {start}–{end}, pareadas por equipes, atributos, estilo, mando e semente. Nenhuma falha foi excluída; as duas versões completaram todas as {count} partidas.')
add('- Referência agregada: **5.329 jogos reais**, cinco ligas, três temporadas. Referência espacial: **1.430 chutes sem pênaltis**, 64 jogos da Copa 2022, incluindo prorrogações quando existentes. A comparação espacial descreve outra população; o motor foi avaliado em tempo regulamentar.')
add('- Desenvolvimento: pilotos 108000–108599 e primeira coorte pareada 112000–112599, arquivada em [round1/REPORT.md](round1/REPORT.md). A primeira revisão regrediu no índice agregado e não foi promovida. A revisão final foi congelada antes de ler a coorte 114000–114299. O modelo geométrico usou 48 partidas StatsBomb para ajuste e 16 para diagnóstico; esse diagnóstico foi consultado no desenvolvimento, portanto não é teste final intocado.')
add('- Runtime anterior: `1908af7`. Runtime congelado publicado: [`f93a445`](https://github.com/adrible/amiguinhos-match-engine/commit/f93a4458f2915eccedb188705cb2027855adbccb). Cabeçalhos brutos registram o commit publicado; árvore e hashes estão em [build_manifest.json](build_manifest.json). Nenhuma alteração do runtime após abrir a coorte final.')
add('- A semente oficial permaneceu em quarentena. `main`, o runtime estável v1.2 e o snapshot anterior de congelamento não foram modificados.')
add()
add('A revisão usa circulação com fator 0,96, intercepto contextual fixo de +0,14 no logit do xG e probabilidade de primeiro amarelo ×1,16. Esses parâmetros foram ajustados com a rodada 1. O motor continua resolvendo probabilidades por lance; o xG contextual resultante não é o modelo proprietário StatsBomb.')
add()
add('## Totais e resultados')
add()
keys=[('goals_per_match','Gols/jogo'),('shots_per_match','Chutes/jogo'),('sot_per_match','No alvo/jogo'),('fouls_per_match','Faltas/jogo'),('corners_per_match','Escanteios/jogo'),('yellow_per_match','Amarelos/jogo'),('red_per_match','Vermelhos/jogo'),('home_goals_per_match','Gols mandante/jogo'),('away_goals_per_match','Gols visitante/jogo'),('home_win_rate','Vitórias mandante'),('draw_rate','Empates'),('zero_zero_rate','0–0'),('btts_rate','Ambos marcam'),('over_2_5_rate','Mais de 2,5 gols')]
table(['Parâmetro','Real','Anterior','Calibrado'],[(label,*[(percent if key.endswith('_rate') else number)(v['metrics'][key]) for v in (real,old['summary'],new['summary'])]) for key,label in keys])
bi=old['comparison']['realism_index'];ni=new['comparison']['realism_index'];ci=s['index_delta_bootstrap']
add(f'Índice agregado do repositório: **{bi:.2f} → {ni:.2f}**. Variação observada: {ni-bi:+.2f} pontos; IC95% por 1.000 reamostragens pareadas de partidas: **[{ci["low95"]:+.2f}; {ci["high95"]:+.2f}]**. '+('O intervalo inclui zero: não demonstra melhora estatística do índice.' if ci['low95']<=0<=ci['high95'] else 'O intervalo não inclui zero nesta população sintética. Isso não valida todas as mecânicas do motor.'))
add()
table(['Mudança pareada por partida','Média','IC95% aproximado'],[(k,f'{v["delta"]:+.3f}',f'[{v["low95"]:+.3f}; {v["high95"]:+.3f}]') for k,v in s['paired'].items() if k in ('goals','shots','sot','home_goals','away_goals','home_win','draw')])
add('Os intervalos agrupam os lances por partida; chutes de uma mesma partida não são tratados como observações independentes. As referências reais são fixas neste benchmark; a incerteza de escolha de campeonato/temporada não está nesses intervalos.')
add()
add('## De onde saem os chutes')
add()
add('![Mapa de origem das finalizações](shot_origins.svg)')
add()
r=ref['all_nonpenalty'];oh=old['shots'];nh=new['shots']
table(['Medida espacial — sem pênaltis','StatsBomb','Anterior','Calibrado'],[
 ('Distância média (m)',number(r['distance_mean']),number(oh['distance']['mean']),number(nh['distance']['mean'])),
 ('Distância mediana (m)',number(r['distance_median']),number(oh['distance']['median']),number(nh['distance']['median'])),
 ('Dentro da área',percent(r['inside_box_share']),percent(oh['inside_box']),percent(nh['inside_box'])),
 ('Chutes acima de 35 m',percent(r['distance_bins']['35-120']),percent(oh['distance_bins']['35-120']),percent(nh['distance_bins']['35-120'])),
 ('Cabeceios / chutes',percent(r['header_share']),percent(oh['body_share'].get('head',0)/oh['n']),percent(nh['body_share'].get('head',0)/nh['n'])),
 ('Distância média de cabeceios (m)',number(ref['by_body']['Head']['distance_mean']),number(old['body']['head']['distance']['mean']),number(new['body']['head']['distance']['mean'])),
 ('xG médio por chute',f'{r["mean_xg"]:.3f}',f'{oh["mean_xg"]:.3f}',f'{nh["mean_xg"]:.3f}')])
table(['Distância','StatsBomb','Anterior','Calibrado'],[(k,percent(v),percent(oh['distance_bins'][k]),percent(nh['distance_bins'][k])) for k,v in r['distance_bins'].items()])
for label,title in [('before','Anterior'),('after','Calibrado')]:
 v=s['distance_effect_sizes'][label];add(f'{title}: distância de Wasserstein da distribuição real = **{v["wasserstein_metres"]:.2f} m**; diferença máxima entre distribuições acumuladas (KS) = **{v["ks_statistic"]:.3f}**. São tamanhos de diferença, não índices universais de realismo.')
add()
rows=[]
for name in sorted(set(old['origin'])|set(new['origin'])):
 o=old['origin'].get(name);n=new['origin'].get(name)
 rows.append((name,o['n'] if o else 0,n['n'] if n else 0,number(o['distance']['mean']) if o else '—',number(n['distance']['mean']) if n else '—',f'{n["mean_xg"]:.3f}' if n else '—',percent(n['goals']) if n else '—'))
table(['Origem do motor','n anterior','n novo','m anterior','m novo','xG novo','Conversão nova'],rows)
add('As categorias do motor não são uma tradução exata das categorias do provedor. Comparações auxiliares de entregas reais:')
table(['Assistência StatsBomb','n','Distância média (m)','xG médio'],[(k,v['n'],number(v['distance']),f'{v["xg"]:.3f}') for k,v in s['reference_assists'].items()])
add('Pênaltis têm um resolvedor separado e não entram nesses mapas nem nos grupos por chute. Contagem/conversão geral aparece nos totais; a origem XYZ e a trajetória de cada pênalti ainda precisam de uma auditoria própria.')
add()
add('## Corpo, pressão e qualidade da chance')
add()
table(['Corpo — calibrado','n','Distância média (m)','No alvo','Conversão','xG médio'],[(k,v['n'],number(v['distance']['mean']),percent(v['sot']),percent(v['goals']),f'{v["mean_xg"]:.3f}') for k,v in new['body'].items()])
hr=ref['by_body']['Head'];add(f'Referência de cabeceios da Copa: {hr["shots"]} chutes, {hr["distance_mean"]:.2f} m, {percent(hr["on_target_rate"])} no alvo, {percent(hr["goals_per_shot"])} convertidos. Não confundir com a referência anterior da Premier League 2019–24, outra população e período.')
add()
table(['Pressão do motor — calibrado','n','Distância média (m)','Bloqueados','No alvo','Conversão','xG'],[(k,v['n'],number(v['distance']['mean']),percent(v['blocked']),percent(v['sot']),percent(v['goals']),f'{v["mean_xg"]:.3f}') for k,v in new['pressure_bins'].items() if v['n']])
add('Esses estratos são descritivos: pressão, distância, origem e habilidade variam juntos. A comparação causal de pressão foi feita separadamente no experimento de sensibilidade.')
add()
table(['Faixa de xG — calibrado','n','xG médio','Gols / chutes','No alvo'],[(k,v['n'],f'{v["mean_xg"]:.3f}',percent(v['goals']),percent(v['sot'])) for k,v in new['xg_bins'].items() if v['n']])
add(f'No diagnóstico real de 16 partidas, o modelo geométrico previu xG médio {ref["validation_predicted_mean_xg"]:.4f}, contra {ref["validation"]["mean_xg"]:.4f} da StatsBomb; erro absoluto médio por chute **{ref["validation_xg_mae"]:.4f}**. Isso mede proximidade com as estimativas do provedor, não acerto de resultado de cada chute. Finalizador e goleiro não entram no xG geométrico; entram na execução.')
add()
diag=s['engine_reference_diagnostic']
add(f'Com o ajuste contextual aplicado, a média nas mesmas 16 partidas é {diag["mean_engine_xg_on_16_real_matches"]:.4f}, com MAE {diag["mae_to_statsbomb"]:.4f} para o xG do provedor. Esse aumento é um compromisso explícito da calibração de contexto; a correspondência bruta anterior não deve ser apresentada como resultado do motor já ajustado.')
add()
add('## Desvios concretos ainda presentes')
add()
add('A distribuição espacial melhorou muito; a validação não demonstrou melhora global do índice. O candidato permanece em revisão, sem promoção ao runtime principal.')
add()
farshare=new['shots']['distance_bins']['35-120'];realshare=ref['all_nonpenalty']['distance_bins']['35-120']
add(f'- **Cauda de distância:** {percent(farshare)} dos chutes novos ultrapassam 35 m, contra {percent(realshare)} na referência. Há 266 casos: 73 de through_ball, 60 de cross, 53 de cutback, 28 de free_kick, 28 de transition e 24 de outras origens. O caso extremo foi uma tentativa de falta a 105,01 m (semente 114000, xG 0,001, fora do alvo). O excesso em assistências aponta para decisões de finalização/receptores ainda resolvidas sem alcance suficiente; exige um teste próprio da recepção e do local da reposição, sem cortar distâncias apenas para ajustar um histograma.')
add(f'- **Resultados/mando:** vitória do mandante em {percent(new["summary"]["metrics"]["home_win_rate"])} dos jogos, contra {percent(real["metrics"]["home_win_rate"])} nas ligas. A diferença pareada para o runtime anterior tem intervalo amplo e inclui zero. Os controles pequenos mostram efeito positivo do mando, mas não comprovam a magnitude correta; o benefício de mando não está validado globalmente por esta amostra.')
add(f'- **Cabeceios:** {percent(new["body"]["head"]["sot"])} no alvo e {percent(new["body"]["head"]["goals"])} convertidos, contra {percent(ref["by_body"]["Head"]["on_target_rate"])} e {percent(ref["by_body"]["Head"]["goals_per_shot"])} na Copa. Diferenças de situação e população exigem comparação por distância, pressão e tipo de entrega, além da média geral.')
add('- **Altura:** o contato simulado de cabeça ainda tem alvo fixo de 1,6 m. A consistência Z foi testada; a distribuição de alturas e impulsão ainda não foi validada com tracking real.')
add()
add('## Integridade e testes')
add()
validation=json.loads((HERE/'validation_checks.json').read_text())
for text in validation['checks']:add('- '+text)
add()
table(['Verificação espacial','Anterior','Calibrado'],[(name,old['counts'].get(key,0),new['counts'].get(key,0)) for key,name in [
 ('box_label_outside_physical_penalty_area','Chute rotulado área fora da área física'),('header_ball_height_below_0_5m','Cabeceio com contato abaixo de 0,5 m'),('invalid_player_point','Jogador fora dos limites / não finito'),('invalid_ball_xyz','Bola XYZ inválida'),('inactive_ball_owner','Dono da bola fora de campo'),('owner_ball_gap_over_2m','Bola dominada a mais de 2 m do dono'),('speed_limit_violation','Violação do limite de deslocamento observado')]])
add('O antigo contador `shot_distance_proxy_gap_over_10m` permanece nos dados brutos como diagnóstico da aproximação por setor; deixou de ser erro do resolvedor novo, que usa a distância física. `used_distance_error` verifica a distância efetivamente informada ao chute. Altura simulada de contato de cabeça ainda é um alvo simplificado de 1,6 m; tracking externo fornece sua própria altura.')
add()
add('## Estilos, força e mando')
add()
table(['Diferença de força — calibrado','n','Gols/jogo','Chutes/jogo','Vitória mandante'],[(k,v['metrics']['matches'],number(v['metrics']['goals_per_match']),number(v['metrics']['shots_per_match']),percent(v['metrics']['home_win_rate'])) for k,v in new['strength'].items()])
add('Todos os cruzamentos de estilos estão em `summary.json`. Os cinco mais frequentes, escolhidos por tamanho de amostra:')
table(['Estilo mandante / visitante','n','Gols/jogo','Chutes/jogo'],[(k,v['metrics']['matches'],number(v['metrics']['goals_per_match']),number(v['metrics']['shots_per_match'])) for k,v in sorted(new['styles'].items(),key=lambda kv:kv[1]['metrics']['matches'],reverse=True)[:5]])
add('Controles adicionais com os mesmos elencos de força 80 e estilo equilibrado, sementes 113100–113123 em cada modo:')
for label,title in [('before','Anterior'),('after','Calibrado')]:
 control=json.loads((HERE/f'realism-controls-{label}.json').read_text())
 rows=[]
 for mode in ('neutral','home_away'):
  rr=[r for r in control['matches'] if r['mode']==mode];n=len(rr)
  rows.append((mode,n,number(sum(r['score'][0] for r in rr)/n),number(sum(r['score'][1] for r in rr)/n),number(sum(r['second_added_announced'] for r in rr)/n),number(sum(r['second_added_played'] for r in rr)/n)))
 add(f'**{title}**');add();table(['Modo','n','Gols equipe 0','Gols equipe 1','Acréscimo 2ºT anunciado (min)','Acréscimo 2ºT jogado (min)'],rows)
add('São só 24 jogos por modo e versão; diferenças pequenas não demonstram viés de mando. Tempo público, tempo bruto e acréscimo anunciado são medidas diferentes. Não se compara o número de eventos abstratos de passe com passes completos de tracking.')
add()
add('## Onde testar e desenvolver a seguir')
add()
add('1. **Chutes extremos e qualidade por assistência:** reduzir as caudas ainda divergentes de distância/ângulo sem impor quotas; validar cruzamentos, passes em profundidade e rebotes com uma liga completa, incluindo pressão e posição do goleiro no instante do chute.')
add('2. **Impedimento geométrico:** posição da bola, penúltimo defensor, corredor e instante do passe. O impedimento atual ainda depende do modelo probabilístico por setor.')
add('3. **Movimento contínuo:** aceleração, frenagem, curvas e sprint por jogador; o limite atual de deslocamento de 8 m/s não representa picos de velocidade de elite. Deslocamento entre eventos não equivale a velocidade instantânea medida por tracking.')
add('4. **Contato aéreo e colisões:** altura individual, impulsão, tempo do salto, disputa, bloqueio corporal, quique, arrasto e recepção após a bola cair. O voo atual usa gravidade e velocidade horizontal constante; a altura de contato simulada ainda é simplificada.')
add('5. **Posse e passe completos:** registrar cada recepção, domínio, perda, pressão e linha de passe antes de comparar volume, acerto, progressão e duração de posse com eventos reais. O motor atual agrega circulação em batidas de tempo.')
add('6. **Fadiga e contexto:** pressão alta contra bloco baixo, superioridade numérica, 120 minutos, substituições, chuva e estado do placar; testes pareados com atributos idênticos e apenas uma intervenção de cada vez. O estudo atual tem estratos descritivos de estilo/força, não estima isoladamente todos esses efeitos.')
add()
add('## Fontes e reprodução')
add()
add('<img src="statsbomb_icon.svg" width="48" alt="StatsBomb">')
add()
add('Dados espaciais: **StatsBomb Open Data**, disponibilizados para pesquisa pela StatsBomb/Hudl. [Repositório e termos](https://github.com/statsbomb/open-data), [marca oficial](https://www.hudl.com/en_gb/products/statsbomb), [media pack](https://statsbomb.com/media-pack/). Ícone original da página oficial, preservado em `statsbomb_icon.svg`; direitos da marca pertencem ao titular. Conversão 120×80 → 105×68 não é metragem física observada do estádio.')
add()
add('Referência agregada: [Football-Data.co.uk](https://www.football-data.co.uk/data.php), [mirror datasets/football-datasets](https://github.com/datasets/football-datasets), fontes e hashes em `summary.json`. Geometria: [IFAB, Lei 1](https://www.theifab.com/laws/latest/the-field-of-play/).')
add()
add('Scripts: `build_shot_reference.py`, `run_audit.py`, `run_sensitivity.py`, `run_controls.py`, `run_physics_controls.py`, `summarise.py`, `make_report.py`. Os seis arquivos `realism-before/after-*.json.gz` retêm as amostras completas, sem seleção. Os hashes dos eventos reais usados no ajuste estão em `data/spatial_shot_reference_v13.json`. Veja [README.md](README.md) para os comandos básicos.')
(HERE/'REPORT.md').write_text('\n'.join(lines)+'\n')
