import copy
from dataclasses import asdict
import unittest

from engine_experiment_v13_continuous import MatchEngine
from validation.continuous_v13.paired_contexts import fixture, fingerprint_attributes, intervention, measure, window


class ControlledContextTests(unittest.TestCase):
    def test_paired_rosters_have_identical_attributes_and_physical_profiles(self):
        e=fixture(127001)
        for a,b in zip(e.teams[0].on_field,e.teams[1].on_field):
            self.assertEqual({k:v for k,v in asdict(a.player).items() if k!='name'},
                             {k:v for k,v in asdict(b.player).items() if k!='name'})
            self.assertEqual(e._cs_profiles[e._key(0,a.player.name)],e._cs_profiles[e._key(1,b.player.name)])
        self.assertFalse(e.auto_substitutions_enabled)
        self.assertFalse(e.config.auto_tactical_adaptation)

    def test_tactical_interventions_change_only_the_named_tactic(self):
        for case,team,key,value in [('pressing',0,'pressing',.9),('low_block',1,'defensive_line',.25)]:
            e=fixture(127002);before=[asdict(rt.team.tactics) for rt in e.teams];attrs=fingerprint_attributes(e);rng=e.rng.getstate()
            intervention(e,case);before[team][key]=value
            self.assertEqual(before,[asdict(rt.team.tactics) for rt in e.teams])
            self.assertEqual(attrs,fingerprint_attributes(e));self.assertEqual(rng,e.rng.getstate())

    def test_rain_does_not_also_change_turf_temperature_or_wind(self):
        e=fixture(127003);before=dict(e._v13_environment);attrs=fingerprint_attributes(e)
        intervention(e,'rain');before['weather']='rain'
        self.assertEqual(before,e._v13_environment);self.assertEqual(attrs,fingerprint_attributes(e))
        self.assertGreater(e._environment_effects()['surface_control_penalty'],0.)

    def test_numerical_advantage_keeps_the_remaining_players_unchanged(self):
        e=fixture(127004);before={p.player.name:asdict(p.player) for p in e.teams[1].on_field}
        intervention(e,'numerical_advantage')
        self.assertEqual(sum(not p.red for p in e.teams[1].on_field),10)
        self.assertEqual(before,{p.player.name:asdict(p.player) for p in e.teams[1].on_field})
        self.assertEqual(sum(p['red'] for p in e._physical_players()),1)

    def test_fresh_substitution_keeps_talent_and_body_profile_equal(self):
        e=fixture(127005);out=e.teams[0].on_field[-1];out.energy=.5
        profile=copy.deepcopy(e._cs_profiles[e._key(0,out.player.name)])
        row=intervention(e,'fresh_substitution');incoming=e.teams[0].by_name('A equal-attribute fresh ST')
        self.assertTrue(row['attributes_equal']);self.assertEqual(incoming.energy,1.)
        self.assertEqual(profile,e._cs_profiles[e._key(0,incoming.player.name)])
        self.assertLessEqual(e._cs_motion[e._key(0,incoming.player.name)].peak_speed,profile.sprint_speed)

    def test_score_contrast_does_not_count_prescribed_goal_as_new_outcome(self):
        e=fixture(127006);intervention(e,'score_state');start=measure(e)
        e.stats[0].goals+=2;end=measure(e)
        self.assertEqual(window(end,start)['goals'],[2,0])

    def test_extra_duration_is_a_horizon_intervention_not_extra_talent(self):
        e=fixture(127007);attrs=fingerprint_attributes(e);before=e.export_state()
        intervention(e,'scheduled_120_minutes')
        self.assertEqual(e.state.period_markers,[45,90,105,120])
        self.assertEqual(attrs,fingerprint_attributes(e))
        after=e.export_state();before['state']['period_markers']=[45,90,105,120]
        self.assertEqual(before,after)

    def test_legal_manual_extra_time_saves_and_turns_the_ends(self):
        e=fixture(127008);e.state.second=e._cs_time=5400.;e.state.period_index=2;e.state.ended=True
        e.start_extra_time();self.assertFalse(e.state.ended);self.assertEqual(e.state.period_markers,[105,120])
        self.assertEqual(e.attack_direction(0),1)
        e.advance_physics(.3);restored=MatchEngine.from_json(e.export_json())
        e.advance_physics(.7);restored.advance_physics(.7);self.assertEqual(e.export_state(),restored.export_state())


if __name__=='__main__':unittest.main()
