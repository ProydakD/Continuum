import unittest

from research.e008_reference import public_reference_input
from research.e008_reference_worker import solve
from research.e008_scm import VARIABLES, evidence, model


class ReferenceTests(unittest.TestCase):
    def setUp(self):
        self.scm = model("relay", VARIABLES, "and", [0, 0, 0])
        self.inputs = {"evidence": [evidence(self.scm, "EA")],
                       "questions": [{"id": "Q1", "kind": "probability", "target": "V1", "do": [["V0", 1]]}]}

    def test_observation_does_not_imply_single_do_answer(self):
        result = solve(self.inputs)
        self.assertEqual(result["answers"], [{"id": "Q1", "value": None, "identified": False}])
        self.assertGreater(result["compatible_parameter_assignments"], 1)

    def test_interventional_population_identifies_its_probability(self):
        self.inputs["evidence"].append(evidence(self.scm, "EB", [["V0", 1]]))
        self.assertEqual(solve(self.inputs)["answers"], [{"id": "Q1", "value": "1", "identified": True}])

    def test_private_world_fields_never_enter_reference_input(self):
        world = {"evidence": self.inputs["evidence"], "panel": [], "successor": self.inputs["questions"],
                 "truth": "PRIVATE", "design_audit": "PRIVATE", "revision_probe": "PRIVATE"}
        self.assertEqual(public_reference_input(world), self.inputs)
        with self.assertRaises(ValueError):
            solve(dict(self.inputs, truth=self.scm))

    def test_duplicate_sources_or_questions_and_unknown_fields_rejected(self):
        with self.assertRaises(ValueError):
            solve(dict(self.inputs, evidence=self.inputs["evidence"] * 2))
        with self.assertRaises(ValueError):
            solve(dict(self.inputs, questions=self.inputs["questions"] * 2))
        with self.assertRaises(ValueError):
            solve(dict(self.inputs, questions=[dict(self.inputs["questions"][0], expected="1")]))


if __name__ == "__main__":
    unittest.main()
