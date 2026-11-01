import unittest
from dataclasses import replace
from engine import make_generic_team, PendingAction, Band, Lane, Zone
from engine_experiment_v13 import MatchEngine
from spatial_shot_v13 import reference_target_probability, shot_geometry
from compare_general_engine_v13 import neutral_comparison
import real_match_benchmark_v13 as bench
from test_real_match_benchmark_v13 import RealMatchBenchmarkTests


class NeutralCalibrationTests(unittest.TestCase):
    def test_neutral_overrides_cannot_create_listing_order_advantage(self):
        e = MatchEngine(make_generic_team('A',80,seed=1), make_generic_team('B',80,seed=2), seed=3,
                        venue_context={'mode':'neutral','home_familiarity':1,'away_familiarity':0,
                                       'crowd_home_share':1,'away_travel_load':1})
        for side in (0,1):
            d=e._venue_effects(side)
            for key in ('pressure_shift','support_shift','space_shift','travel_load','crowd_edge'):
                self.assertEqual(d[key],0)
        clone=MatchEngine.from_json(e.export_json())
        self.assertEqual(clone.venue_diagnostic(),e.venue_diagnostic())

    def test_geometric_reference_has_distance_and_pressure_cost(self):
        for pressure in (0,.5,1):
            near=reference_target_probability(12,pressure)
            far=reference_target_probability(40,pressure)
            self.assertGreater(near,far)
            self.assertTrue(0<far<near<1)
        self.assertGreater(reference_target_probability(12,0),reference_target_probability(12,1))

    def test_target_risk_is_not_normalized_away(self):
        e=MatchEngine(make_generic_team('A',80,seed=1),make_generic_team('B',80,seed=2),seed=3)
        a=next(p for p in e.teams[0].on_field if p.player.position=='ST')
        k=e._goalkeeper(1)
        p=PendingAction(0,a.player.name,'shoot',Zone(Band.BOX,Lane.CENTER),danger=.6,pressure=.4)
        probabilities=set(); targets=set()
        for second in range(100):
            e.state.second=second
            g=shot_geometry(e,p,a,k,e.shot_selection_diagnostic(a,p,k))
            probabilities.add(g['reference_on_target_probability'])
            targets.add(g['shot_target'])
        self.assertEqual(len(probabilities),1)
        self.assertGreater(len(targets),4)

    def test_neutral_index_is_invariant_to_home_away_labels(self):
        row=RealMatchBenchmarkTests._row
        real=bench.summarise_matches([row(3,0),row(1,1),row(1,0),row(0,2)])
        rows=[row(4,0),row(1,1),row(2,0),row(0,1)]
        mirrored=[]
        for r in rows:
            mirrored.append({key:(r[key.replace('home_','away_')] if key.startswith('home_') else r[key.replace('away_','home_')]) for key in r})
        seasons=[{'metrics':real['metrics']},{'metrics':real['metrics']}]
        a=neutral_comparison(bench,real,bench.summarise_matches(rows),seasons)
        b=neutral_comparison(bench,real,bench.summarise_matches(mirrored),seasons)
        self.assertEqual(a['realism_index'],b['realism_index'])
        self.assertFalse(any('home_' in c['name'] or 'away_' in c['name'] for c in a['components']))

if __name__=='__main__': unittest.main()
