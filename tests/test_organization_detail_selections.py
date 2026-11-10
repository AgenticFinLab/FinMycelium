"""Detail projection IDs stay local to immutable facts."""

import copy
import unittest

from sparse_test_dependencies import install_missing_lmbase_containers

install_missing_lmbase_containers()

from finmy.builder.sparse_build.organization_batches import (
    _memberships, organize_person_plan,
)
from finmy.builder.sparse_build.organization_details import (
    detail_index_catalog, validate_detail_selections,
)
from finmy.builder.sparse_build.organization_errors import OrganizationValidationError
from finmy.builder.sparse_build.person_organization import (
    apply_organization, organization_request,
)
from test_sparse_organization_batches import OrganizationResponses, many_facts
from test_sparse_person_organization import facts, plan, vf


class OrganizationDetailSelectionsTest(unittest.TestCase):
    def catalog_package(self):
        return {
            "activity": [
                {"activity_id": "A1", "action_id": "ACT1"},
                {"activity_id": "A2", "action_id": "ACT2"},
                {"activity_id": "T1", "transaction_id": "TX1"},
            ],
            "activity_detail": [
                {"activity_id": "A1", "detail_index": 4, "value": "Fourth retained detail"},
                {"activity_id": "A2", "detail_index": 2, "value": "Other activity's detail"},
                {"activity_id": "A1", "detail_index": 0, "value": "First detail"},
            ],
            "financial_transaction": [{"transaction_id": "TX1", "details": ["Transaction detail"]}],
            "transaction_instrument": [{"transaction_id": "TX1", "ordinal": 0}],
        }

    def test_catalog_preserves_sparse_local_keys_and_empty_activity(self):
        package = self.catalog_package()
        before = copy.deepcopy(package)
        catalog = detail_index_catalog(package)
        self.assertEqual(catalog, {"A1": [0, 4], "A2": [2], "T1": []})
        self.assertEqual(detail_index_catalog(package, ["T1", "A1"]), {"T1": [], "A1": [0, 4]})
        self.assertEqual(package, before)
        catalog["A1"].append(99)
        self.assertEqual(detail_index_catalog(package)["A1"], [0, 4])


    def test_omitted_null_empty_and_cross_event_projections_stay_distinct(self):
        rows = [
            {"event_id": "E1", "activity_id": "A1"},
            {"event_id": "E2", "activity_id": "A1", "detail_indices": None},
            {"event_id": "E3", "activity_id": "A1", "detail_indices": []},
            {"event_id": "E4", "activity_id": "A1", "detail_indices": [4, 0]},
            {"event_id": "E5", "activity_id": "A1", "detail_indices": [0]},
            {"event_id": "E1", "activity_id": "T1", "detail_indices": []},
        ]
        before = copy.deepcopy(rows)
        validate_detail_selections(rows, detail_index_catalog(self.catalog_package()), phase="Placement")
        self.assertEqual(rows, before)

    def test_real_transaction_adapter_does_not_make_transaction_details_selectable(self):
        from finmy.person_epg.adapter import from_subject_graph
        from test_subject_graph_schema import field, graph_fixture

        graph = graph_fixture()
        graph["events"][1]["transactions"][0]["details"] = [field("A documented transaction detail")]
        before = copy.deepcopy(graph)
        package = from_subject_graph(graph)
        transaction = package["financial_transaction"][0]
        self.assertTrue(transaction["details"])
        activity = next(row for row in package["activity"]
                        if row.get("transaction_id") == transaction["transaction_id"])
        aid = activity["activity_id"]
        catalog = detail_index_catalog(package)
        self.assertEqual(catalog[aid], [])
        self.assertEqual(organization_request(package, {"stages": []}, {})["available_detail_indices"][aid], [])
        with self.assertRaises(OrganizationValidationError) as caught:
            validate_detail_selections(
                [{"event_id": "E", "activity_id": aid, "detail_indices": [0]}], catalog, phase="Placement")
        self.assertEqual(caught.exception.report["violations"][0]["allowed_detail_indices"], [])
        self.assertEqual(graph, before)


if __name__ == "__main__":
    unittest.main()
