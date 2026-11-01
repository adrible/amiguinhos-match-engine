from __future__ import annotations

import unittest

from calibration_v13 import simulate_fixture
from final_protocol_v13 import (
    EXPECTED_OFFICIAL_FINAL_HASH,
    EXPECTED_OFFICIAL_FINAL_SEED,
    OFFICIAL_FINAL_AWAY,
    OFFICIAL_FINAL_HASH,
    OFFICIAL_FINAL_HOME,
    OFFICIAL_FINAL_SEED,
    assert_calibration_seed_allowed,
    is_reserved_official_seed,
)


class OfficialFinalProtocolTests(unittest.TestCase):
    def test_declared_hash_and_seed_are_stable(self):
        self.assertEqual(OFFICIAL_FINAL_HASH, EXPECTED_OFFICIAL_FINAL_HASH)
        self.assertEqual(OFFICIAL_FINAL_SEED, EXPECTED_OFFICIAL_FINAL_SEED)
        self.assertEqual(OFFICIAL_FINAL_SEED, 1810131239)

    def test_exact_final_fixture_seed_is_reserved(self):
        self.assertTrue(
            is_reserved_official_seed(
                OFFICIAL_FINAL_HOME, OFFICIAL_FINAL_AWAY, OFFICIAL_FINAL_SEED
            )
        )

    def test_adjacent_seed_is_not_reserved(self):
        self.assertFalse(
            is_reserved_official_seed(
                OFFICIAL_FINAL_HOME, OFFICIAL_FINAL_AWAY, OFFICIAL_FINAL_SEED + 1
            )
        )
        assert_calibration_seed_allowed(
            OFFICIAL_FINAL_HOME, OFFICIAL_FINAL_AWAY, OFFICIAL_FINAL_SEED + 1
        )

    def test_other_fixture_can_use_same_numeric_seed(self):
        self.assertFalse(
            is_reserved_official_seed(
                "benfica_u21", OFFICIAL_FINAL_AWAY, OFFICIAL_FINAL_SEED
            )
        )

    def test_calibration_rejects_reserved_seed_before_simulation(self):
        with self.assertRaisesRegex(RuntimeError, "reserved for the live final runner"):
            simulate_fixture(
                OFFICIAL_FINAL_HOME,
                OFFICIAL_FINAL_AWAY,
                OFFICIAL_FINAL_SEED,
                auto_adapt=True,
            )


if __name__ == "__main__":
    unittest.main()
