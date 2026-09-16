from __future__ import annotations

"""Bridge pytest-style function tests into the repository's unittest-only CI.

The realism-stack test modules intentionally use small plain ``test_*`` functions.
The candidate workflow historically invokes ``python -m unittest``; importing a
module containing only those functions does not execute them.  This adapter
registers every zero-argument ``test_*`` function as a real unittest method and
fails loudly if a future test starts requiring a fixture/parameter.
"""

import importlib
import inspect
import unittest


MODULES = [
    "test_v13_stoppage_time",
    "test_v13_clock_behaviour",
    "test_v13_mental_state",
    "test_v13_tactical_fouls",
    "test_v13_mismatches",
    "test_v13_micro_adjustments",
    "test_v13_second_balls",
    "test_v13_set_piece_defense",
    "test_v13_offensive_communication",
    "test_v13_numerical_advantage",
    "test_v13_load_injuries",
    "test_v13_gk_one_v_one",
    "test_v13_penalties",
]


class NewRealismStackFunctionTests(unittest.TestCase):
    pass


def _wrap(module_name: str, function_name: str):
    def test_method(self):
        module = importlib.import_module(module_name)
        function = getattr(module, function_name)
        signature = inspect.signature(function)
        required = [
            parameter.name
            for parameter in signature.parameters.values()
            if parameter.default is inspect.Parameter.empty
            and parameter.kind
            in {
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            }
        ]
        self.assertEqual(
            required,
            [],
            f"{module_name}.{function_name} requires fixture/parameter(s) {required}; "
            "convert it to unittest or provide an explicit local harness.",
        )
        function()

    test_method.__name__ = f"test__{module_name}__{function_name}"
    test_method.__qualname__ = (
        f"NewRealismStackFunctionTests.{test_method.__name__}"
    )
    return test_method


_registered = 0
for _module_name in MODULES:
    _module = importlib.import_module(_module_name)
    _functions = sorted(
        name
        for name, value in vars(_module).items()
        if name.startswith("test_") and inspect.isfunction(value)
    )
    if not _functions:
        raise RuntimeError(f"No test_* functions found in {_module_name}")
    for _function_name in _functions:
        setattr(
            NewRealismStackFunctionTests,
            f"test__{_module_name}__{_function_name}",
            _wrap(_module_name, _function_name),
        )
        _registered += 1

if _registered == 0:
    raise RuntimeError("No realism-stack function tests were registered")


if __name__ == "__main__":
    unittest.main(verbosity=2)
