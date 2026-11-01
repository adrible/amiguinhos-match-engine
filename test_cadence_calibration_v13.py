import copy
import statistics
import unittest
from engine import MatchEngine as BaseEngine, make_generic_team
from engine_experiment_v13 import MatchEngine


class CadenceCalibrationTests(unittest.TestCase):
    def setUp(self):
        self.a=make_generic_team('Alpha',80,seed=1)
        self.b=make_generic_team('Beta',80,seed=2)

    def test_same_fixture_keeps_weather_when_order_is_reversed(self):
        for seed in range(20):
            first=MatchEngine(copy.deepcopy(self.a),copy.deepcopy(self.b),seed=seed)
            second=MatchEngine(copy.deepcopy(self.b),copy.deepcopy(self.a),seed=seed)
            self.assertEqual(first.environment_diagnostic(),second.environment_diagnostic())
            self.assertEqual(first.match_flow,second.match_flow)

    def test_cadence_spread_narrows_without_deterministic_matches(self):
        base=[];current=[]
        for seed in range(200):
            base.append(BaseEngine(self.a,self.b,seed=seed).match_flow)
            current.append(MatchEngine(self.a,self.b,seed=seed).match_flow)
        self.assertLess(statistics.pstdev(current),statistics.pstdev(base))
        self.assertGreater(statistics.pstdev(current),.1)
        self.assertLess(abs(statistics.mean(current)-statistics.mean(base)),.10)

    def test_restore_keeps_existing_cadence_and_weather(self):
        e=MatchEngine(self.a,self.b,seed=9,environment={'weather':'rain','pitch':'heavy'})
        e.match_flow=.43
        clone=MatchEngine.from_json(e.export_json())
        self.assertEqual(clone.match_flow,.43)
        self.assertEqual(clone.environment_diagnostic(),e.environment_diagnostic())
