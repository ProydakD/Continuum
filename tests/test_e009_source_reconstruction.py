"""Contract tests, including mechanical passes that must NOT be semantic passes."""
from copy import deepcopy
import unittest

from research.e009_adjudication_v2 import FIELDS
from research.e009_measurement.expressions import resolve_expression
from research.e009_measurement.reconstruction import SCHEMA, build_request, materialize_reconstruction


def view(payload, representation="S", stage="B"):
    return {"memory": {"format": representation, "payload": payload}, "stage": stage,
            "origin": {"actor": "contract-fixture"}, "sha256": None,
            "trust": "unverified_author_assertion"}


def pointer(path, document=0):
    return {"document": document, "pointer": path}


def span(text, value, decode="text", document=0):
    start = text.index(value)
    return {"document": document, "start": start, "end": start + len(value), "decode": decode}


def literal(selector):
    return {"op": "literal", "selector": selector}


def binding(expression, scope, current=None):
    return {"expression": expression, "scope_witnesses": [scope],
            "currentness_witnesses": [current if current is not None else scope]}


def known(expression, scope, current=None):
    return {"state": "known", "values": [binding(expression, scope, current)], "state_witnesses": []}


def fixture():
    payload = {"id": "H", "version": 2, "origin": "prior", "proposition": {"query": {"kind": "model", "index": 167}, "value": 1},
               "status": "supported", "bases": [["e:EA"]], "reasons": [], "previous_sha256": "a" * 64}
    root = pointer("")
    claim = {"id": "H", "identity": literal(pointer("/id")), "identity_witnesses": [root],
             "currentness_witnesses": [root],
             "fields": {name: known(literal(pointer("/" + name)), root) for name in FIELDS}}
    output = {"schema": SCHEMA, "claims": [claim], "coverage": {"state": "complete", "gaps": [], "witnesses": [root]}}
    return view(payload), output


class SourceExpressionTests(unittest.TestCase):
    def test_literal_null_hash_and_malformed_array_exact(self):
        memory = view({"null": None, "hash": "a" * 66, "array": [0] * 65, "empty": {}})
        for key, value in memory["memory"]["payload"].items():
            with self.subTest(key=key):
                result = resolve_expression(memory, literal(pointer("/" + key)))
                self.assertEqual(result["value"], value)
                self.assertTrue(result["literal_copy"])
                self.assertFalse(result["semantic_entailment_verified"])

    def test_symbolic_lists_preserve_flat_nested_empty_order_and_duplicates(self):
        for text, expected in (("[e:EA,e:EA]", ["e:EA", "e:EA"]), ("[[e:EA],[c:H]]", [["e:EA"], ["c:H"]]),
                               ("[[]]", [[]]), (" [] ", []), ("[alpha-id,B_2]", ["alpha-id", "B_2"])):
            with self.subTest(text=text):
                result = resolve_expression(view(text, "F"), {"op": "symbolic_list", "selector": span(text, text)})
                self.assertEqual(result["value"], expected)
                self.assertFalse(result["literal_copy"])
                self.assertFalse(result["semantic_entailment_verified"])

    def test_symbolic_list_rejects_operators_numbers_reserved_and_trailing_text(self):
        for text in ("[EA OR EB]", "[EA,]", "[1]", "[true]", "[null]", "[NaN]", "[\"EA\"]", "[EA] trailing", "[EA", "[ЭА]"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                resolve_expression(view(text, "F"), {"op": "symbolic_list", "selector": span(text, text)})

    def test_symbolic_list_requires_text_not_structured_string_or_json(self):
        with self.assertRaises(ValueError):
            resolve_expression(view({"value": "[EA]"}), {"op": "symbolic_list", "selector": pointer("/value")})
        text = '"[EA]"'
        with self.assertRaises(ValueError):
            resolve_expression(view(text, "F"), {"op": "symbolic_list", "selector": span(text, text, "json")})

    def test_query_value_assembly_retains_individual_provenance(self):
        text = '🌍 H: query={"kind":"model","index":167}; value=1; current.'
        expression = {"op": "object", "members": {"query": literal(span(text, '{"kind":"model","index":167}', "json")),
                                                   "value": literal(span(text, "1;", "text"))}}
        expression["members"]["value"]["selector"]["end"] -= 1
        expression["members"]["value"]["selector"]["decode"] = "json"
        result = resolve_expression(view(text, "F"), expression)
        self.assertEqual(result["value"], {"query": {"kind": "model", "index": 167}, "value": 1})
        self.assertEqual(len(result["sources"]), 2)
        self.assertFalse(result["literal_copy"])
        self.assertFalse(result["semantic_entailment_verified"])

    def test_semantic_proposal_is_retained_but_never_source_copy(self):
        text = "H(model167) is refuted; proposition value remains one."
        result = resolve_expression(view(text, "F"), {"op": "interpret", "proposal": "model167; value=1", "witnesses": [span(text, text)]})
        self.assertEqual(result["value"], "model167; value=1")
        self.assertTrue(result["contains_semantic_proposal"])
        self.assertEqual(result["semantic_proposal_count"], 1)
        self.assertFalse(result["literal_copy"])
        self.assertFalse(result["semantic_entailment_verified"])

    def test_nested_proposal_count_is_not_just_top_level_flag(self):
        memory = view({"text": "candidate meaning"})
        proposal = {"op": "interpret", "proposal": None, "witnesses": [pointer("/text")]}
        result = resolve_expression(memory, {"op": "object", "members": {"first": proposal, "second": proposal}})
        self.assertEqual(result["semantic_proposal_count"], 2)

    def test_no_value_override_default_search_array_or_empty_object_constructor(self):
        for expression in ({"op": "literal", "selector": pointer("/x"), "value": 2}, {"op": "default", "value": 1},
                           {"op": "search", "query": "x"}, {"op": "array", "items": []}, {"op": "object", "members": {}},
                           {"op": "interpret", "proposal": 1, "witnesses": []}):
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                resolve_expression(view({"x": 1}), expression)

    def test_depth_and_node_limits_are_enforced(self):
        expression = literal(pointer("/x"))
        for _ in range(34):
            expression = {"op": "object", "members": {"x": expression}}
        with self.assertRaisesRegex(ValueError, "limit"):
            resolve_expression(view({"x": 1}), expression)
        wide = {"op": "object", "members": {str(i): literal(pointer("/x")) for i in range(1025)}}
        with self.assertRaisesRegex(ValueError, "limit"):
            resolve_expression(view({"x": 1}), wide)


class SourceReconstructionTests(unittest.TestCase):
    def test_complete_literal_records_are_mechanical_only(self):
        memory, output = fixture()
        result = materialize_reconstruction(memory, output)
        self.assertTrue(result["mechanically_valid"])
        self.assertEqual(result["state_counts"], {"known": 7, "absent": 0, "unknown": 0, "conflicting": 0})
        for key in ("measurement_eligible", "semantic_entailment_verified", "identity_verified", "currentness_verified", "coverage_verified"):
            self.assertIs(result[key], False)
        self.assertEqual(build_request(memory)["schema"], SCHEMA)

    def test_known_null_absent_unknown_and_conflicting_remain_distinct(self):
        memory, output = fixture()
        memory["memory"]["payload"].update(origin=None, alternate="refuted")
        fields = output["claims"][0]["fields"]
        fields["previous_sha256"] = {"state": "absent", "values": [], "state_witnesses": [pointer("")]}
        fields["version"] = {"state": "unknown", "values": [], "state_witnesses": []}
        fields["status"]["state"] = "conflicting"
        fields["status"]["values"].append(binding(literal(pointer("/alternate")), pointer("")))
        output["coverage"].update(state="partial", gaps=["Version not settled by this observation."])
        result = materialize_reconstruction(memory, output)
        self.assertEqual(result["state_counts"], {"known": 4, "absent": 1, "unknown": 1, "conflicting": 1})
        resolved = result["claims"][0]["fields"]
        self.assertIsNone(resolved["origin"]["values"][0]["resolved"]["value"])
        self.assertEqual(resolved["previous_sha256"]["values"], [])
        # Even this intentionally false absence declaration is NOT semantically approved.
        self.assertFalse(result["measurement_eligible"])

    def test_identity_expression_mismatch_is_rejected_not_repaired(self):
        memory, output = fixture()
        output["claims"][0]["id"] = "other"
        with self.assertRaisesRegex(ValueError, "identity expression"):
            materialize_reconstruction(memory, output)

    def test_wrong_record_field_context_is_visible_not_silently_repaired(self):
        memory, output = fixture()
        memory["memory"]["payload"]["other"] = {"id": "OTHER", "status": "supported"}
        output["claims"][0]["fields"]["status"]["values"][0]["expression"] = literal(pointer("/other/status"))
        result = materialize_reconstruction(memory, output)
        context = result["claims"][0]["fields"]["status"]["values"][0]["native_contexts"][0]
        self.assertEqual(context["category"], "native_context_other_id")
        self.assertFalse(result["measurement_eligible"])

    def test_missing_identity_scope_or_currentness_witness_is_rejected(self):
        for location in ("identity", "claim_current", "scope", "value_current"):
            memory, output = fixture()
            claim = output["claims"][0]
            if location == "identity":
                claim["identity_witnesses"] = []
            elif location == "claim_current":
                claim["currentness_witnesses"] = []
            else:
                claim["fields"]["status"]["values"][0]["scope_witnesses" if location == "scope" else "currentness_witnesses"] = []
            with self.subTest(location=location), self.assertRaises(ValueError):
                materialize_reconstruction(memory, output)

    def test_carry_forward_retains_history_and_current_witness_separately(self):
        old, output = fixture()
        old["stage"] = "A"
        current = view({"note": "All earlier claim fields remain current."}, stage="B")
        memory = {"memory": None, "trust": "unverified_author_assertion", "journal": [old, current]}
        claim = output["claims"][0]
        claim["currentness_witnesses"] = [pointer("", 1)]
        for field in claim["fields"].values():
            field["values"][0]["currentness_witnesses"] = [pointer("", 1)]
        output["coverage"]["witnesses"] = [pointer("", 1)]
        result = materialize_reconstruction(memory, output)
        status = result["claims"][0]["fields"]["status"]["values"][0]
        self.assertEqual(status["resolved"]["sources"][0]["stage"], "A")
        self.assertEqual(status["currentness_witnesses"][0]["source"]["stage"], "B")
        self.assertFalse(result["currentness_verified"])
        claim["currentness_witnesses"] = [pointer("")]
        with self.assertRaisesRegex(ValueError, "final document"):
            materialize_reconstruction(memory, output)

    def test_duplicate_value_is_not_conflict_even_from_distinct_pointers(self):
        memory, output = fixture()
        memory["memory"]["payload"]["alternate"] = "supported"
        field = output["claims"][0]["fields"]["status"]
        field["state"] = "conflicting"
        field["values"].append(binding(literal(pointer("/alternate")), pointer("")))
        with self.assertRaisesRegex(ValueError, "distinct values"):
            materialize_reconstruction(memory, output)

    def test_unknown_cannot_be_hidden_by_complete_coverage(self):
        memory, output = fixture()
        output["claims"][0]["fields"]["status"] = {"state": "unknown", "values": [], "state_witnesses": []}
        with self.assertRaisesRegex(ValueError, "coverage"):
            materialize_reconstruction(memory, output)

    def test_absent_requires_explicit_witness_not_schema_default(self):
        memory, output = fixture()
        output["claims"][0]["fields"]["previous_sha256"] = {"state": "absent", "values": [], "state_witnesses": []}
        with self.assertRaisesRegex(ValueError, "witness"):
            materialize_reconstruction(memory, output)

    def test_invalid_cardinality_and_duplicate_claim_ids(self):
        for state in ("known", "conflicting"):
            memory, output = fixture()
            output["claims"][0]["fields"]["status"].update(state=state, values=[])
            with self.subTest(state=state), self.assertRaises(ValueError):
                materialize_reconstruction(memory, output)
        memory, output = fixture()
        output["claims"].append(deepcopy(output["claims"][0]))
        with self.assertRaisesRegex(ValueError, "claim ID"):
            materialize_reconstruction(memory, output)

    def test_empty_complete_coverage_requires_current_witness(self):
        memory = view({"note": "No current claims remain."})
        output = {"schema": SCHEMA, "claims": [], "coverage": {"state": "complete", "gaps": [], "witnesses": []}}
        with self.assertRaises(ValueError):
            materialize_reconstruction(memory, output)
        output["coverage"]["witnesses"] = [pointer("")]
        self.assertFalse(materialize_reconstruction(memory, output)["coverage_verified"])

    def test_unreadable_with_gaps_retains_empty_observation(self):
        output = {"schema": SCHEMA, "claims": [], "coverage": {"state": "unreadable", "gaps": ["No identifiable record."], "witnesses": []}}
        self.assertEqual(materialize_reconstruction(view("opaque", "F"), output)["claims"], [])
        output["coverage"]["gaps"] = []
        with self.assertRaises(ValueError):
            materialize_reconstruction(view("opaque", "F"), output)

    def test_false_semantic_proposal_remains_visible_and_ineligible(self):
        memory, output = fixture()
        field = output["claims"][0]["fields"]["proposition"]
        field["values"][0]["expression"] = {"op": "interpret", "proposal": "an unsupported interpretation", "witnesses": [pointer("/proposition")]}
        result = materialize_reconstruction(memory, output)
        self.assertEqual(result["interpretation_proposals"], 1)
        self.assertFalse(result["measurement_eligible"])
        self.assertFalse(result["semantic_entailment_verified"])

    def test_free_prose_composition_and_semantic_fallback_keep_unknown_fields(self):
        text = 'H current; query={"kind":"model","index":167}; value=1; status=refuted; bases=[[e:EA,e:ED]]; reasons=[ED].'
        scope = span(text, text)
        value_selector = span(text, "1;", "json")
        value_selector["end"] -= 1
        composed = {"op": "object", "members": {"query": literal(span(text, '{"kind":"model","index":167}', "json")),
                                                 "value": literal(value_selector)}}
        proposal = {"op": "interpret", "proposal": "model167; value=1", "witnesses": [scope]}
        for expression, proposal_count in ((composed, 0), (proposal, 1)):
            fields = {name: {"state": "unknown", "values": [], "state_witnesses": []} for name in FIELDS}
            fields["proposition"] = known(expression, scope)
            fields["status"] = known(literal(span(text, "refuted")), scope)
            for name, source in (("bases", "[[e:EA,e:ED]]"), ("reasons", "[ED]")):
                fields[name] = known({"op": "symbolic_list", "selector": span(text, source)}, scope)
            output = {"schema": SCHEMA, "claims": [{"id": "H", "identity": literal(span(text, "H")),
                       "identity_witnesses": [scope], "currentness_witnesses": [scope], "fields": fields}],
                      "coverage": {"state": "partial", "gaps": ["Version, origin and previous hash are not asserted."], "witnesses": [scope]}}
            with self.subTest(operation=expression["op"]):
                result = materialize_reconstruction(view(text, "F"), output)
                self.assertEqual(result["state_counts"]["unknown"], 3)
                self.assertEqual(result["state_counts"]["known"], 4)
                self.assertEqual(result["interpretation_proposals"], proposal_count)
                self.assertFalse(result["measurement_eligible"])

    def test_sidecars_extra_fields_and_v2_outputs_are_rejected(self):
        memory, output = fixture()
        with self.assertRaises(ValueError):
            materialize_reconstruction({**memory, "private_sidecar": {}}, output)
        for changed in ({**output, "approved": True}, {**output, "schema": "e009-public-reconstruction-v2"}):
            with self.assertRaises(ValueError):
                materialize_reconstruction(memory, changed)

    def test_returned_values_do_not_mutate_source_or_proposal(self):
        memory, output = fixture()
        original = deepcopy((memory, output))
        result = materialize_reconstruction(memory, output)
        result["claims"][0]["fields"]["bases"]["values"][0]["resolved"]["value"][0].append("change")
        self.assertEqual((memory, output), original)


if __name__ == "__main__":
    unittest.main()
