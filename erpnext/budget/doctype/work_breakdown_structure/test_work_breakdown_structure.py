import frappe
from frappe.tests.utils import FrappeTestCase
from erpnext.budget.doctype.work_breakdown_structure.work_breakdown_structure import (
	get_children,
	delete_wbs_from_tree_view,
	after_insert,
)

class TestWorkBreakdownStructure(FrappeTestCase):
	def setUp(self):
		# Backup originals
		if not hasattr(frappe, "_original_get_doc"):
			frappe._original_get_doc = frappe.get_doc
		if not hasattr(frappe.db, "_original_get_value"):
			frappe.db._original_get_value = frappe.db.get_value
		if not hasattr(frappe, "_original_qb_from_"):
			frappe._original_qb_from_ = frappe.qb.from_

		# Restore before setup
		frappe.get_doc = frappe._original_get_doc
		frappe.db.get_value = frappe.db._original_get_value
		frappe.qb.from_ = frappe._original_qb_from_

		# Ensure company exists
		if not frappe.db.exists("Company", "Test WBS Company"):
			self.company = frappe.get_doc({
				"doctype": "Company",
				"company_name": "Test WBS Company",
				"abbr": "TWC",
				"default_currency": "INR"
			}).insert(ignore_permissions=True)
		else:
			self.company = frappe.get_doc("Company", "Test WBS Company")

		# Create root WBS
		self.root_wbs = frappe.get_doc({
			"doctype": "Work Breakdown Structure",
			"company": self.company.name,
			"project": "Demo Project",
			"wbs_name": "Root WBS",
			"is_group": 1,
			"wbs_level": "Level 1",
		}).insert(ignore_permissions=True)

		# Create child WBS
		self.child_wbs = frappe.get_doc({
			"doctype": "Work Breakdown Structure",
			"company": self.company.name,
			"project": "Demo Project",
			"wbs_name": "Child WBS",
			"is_group": 0,
			"parent_work_breakdown_structure": self.root_wbs.name,
			"wbs_level": "Level 2",
		}).insert(ignore_permissions=True)

	def tearDown(self):
		# Always restore everything cleanly
		frappe.get_doc = frappe._original_get_doc
		frappe.db.get_value = frappe.db._original_get_value
		frappe.qb.from_ = frappe._original_qb_from_

	def test_get_children_TC_BUD_001(self):
		"""Covers get_children() fully for root and non-root branches"""

		root_result = get_children(
			"Work Breakdown Structure",
			parent=None,
			project="Demo Project",
			is_root=True
		)
		self.assertIsInstance(root_result, list)
		self.assertGreaterEqual(len(root_result), 1)
		self.assertIn("value", root_result[0])
		self.assertIn("expandable", root_result[0])

		parent_value = f"{self.root_wbs.name} : {self.root_wbs.wbs_name}"
		non_root_result = get_children(
			"Work Breakdown Structure",
			parent=parent_value,
			project="Demo Project",
			is_root=False
		)
		self.assertIsInstance(non_root_result, list)
		self.assertGreaterEqual(len(non_root_result), 1)
		self.assertIn("value", non_root_result[0])
		self.assertIn("expandable", non_root_result[0])
		self.assertIn("parent", non_root_result[0])
		self.assertTrue(non_root_result[0]["value"].startswith(self.child_wbs.name))

	def test_delete_wbs_from_tree_view_and_after_insert_TC_WBS_003(self):
		"""Covers delete_wbs_from_tree_view() and after_insert() fully"""

		dummy_doc = frappe.get_doc({
			"doctype": "Work Breakdown Structure",
			"name": "TEST-WBS-AFTER-INSERT",
			"company": self.company.name,
			"project": "Demo Project",
			"wbs_name": "After Insert WBS",
			"is_wbs": 1,
			"is_group": 0,
			"wbs_level": "Level 1"
		}).insert(ignore_permissions=True)

		after_insert(dummy_doc)
		created_wbs = frappe.get_doc("Work Breakdown Structure", dummy_doc.name)
		self.assertEqual(created_wbs.company, self.company.name)

		created_wbs.submit()
		self.assertEqual(created_wbs.docstatus, 1)
		created_wbs.cancel()
		self.assertEqual(created_wbs.docstatus, 2)

		wbs_to_delete = frappe.get_doc({
			"doctype": "Work Breakdown Structure",
			"company": self.company.name,
			"project": "Demo Project",
			"wbs_name": "Delete WBS",
			"is_group": 0,
			"wbs_level": "Level 2"
		}).insert(ignore_permissions=True)

		delete_wbs_from_tree_view(wbs_to_delete.name)
		self.assertFalse(frappe.db.exists("Work Breakdown Structure", wbs_to_delete.name))

	def test_check_available_budget_TC_WBS_004(self):
		"""Covers check_available_budget() fully for all doctype paths"""
		from erpnext.budget.doctype.work_breakdown_structure.work_breakdown_structure import check_available_budget

		# Backup originals
		orig_get_doc = frappe.get_doc
		orig_qb_from_ = frappe.qb.from_

		frappe.db.get_value = lambda *args, **kwargs: 50

		class DummyQuery:
			def select(self, *a, **k): return self
			def where(self, *a, **k): return self
			def run(self, as_dict=False): return [{"sob": 1000}]

		frappe.qb.from_ = lambda x: DummyQuery()

		self.child_wbs.linked_monthly_distribution = "Dummy Distribution"
		self.child_wbs.available_budget = 2000
		self.child_wbs.committed_overall_budget = 500
		self.child_wbs.actual_overall_budget = 300

		def mock_get_doc(doctype, name=None):
			if doctype == "Work Breakdown Structure":
				return self.child_wbs
			return type("DummyMD", (), {
				"applicable_on_material_request": 1,
				"applicable_on_purchase_order": 1,
				"applicable_on_booking_actual_expenses": 1,
				"action_if_accumulated_monthly_budget_exceeded_on_mr": "Stop",
				"action_if_accumulated_monthly_budget_exceeded_on_po": "Warn",
				"action_if_accumulated_monthly_budget_exceeded_on_actual": "Ignore",
			})()

		frappe.get_doc = mock_get_doc

		for doctype in [
			"Material Request", "Stock Entry", "Budget Amendment", "Budget Transfer",
			"Expense Claim", "Journal Entry", "Purchase Order", "Purchase Receipt", "Purchase Invoice"
		]:
			result = check_available_budget(self.child_wbs.name, 100, doctype, "2024-05-10")
			self.assertIn("available_bgt", result)
			self.assertIn("wbs", result)
			self.assertIn("action", result)

		# restore mocks after test
		frappe.get_doc = orig_get_doc
		frappe.qb.from_ = orig_qb_from_

	def test_get_available_budget_and_control_actions_TC_WBS_005(self):
		"""Covers get_available_budget_for_month() and get_control_actions() completely"""
		from erpnext.budget.doctype.work_breakdown_structure.work_breakdown_structure import (
			get_available_budget_for_month,
			get_control_actions,
		)

		result1 = get_available_budget_for_month("May", "DummyDist", None)
		self.assertEqual(result1, 0.0)

		result2 = get_available_budget_for_month("May", None, 5000)
		self.assertEqual(result2, 5000)

		frappe.db.get_value = lambda *a, **k: None
		result3 = get_available_budget_for_month("May", "DummyDist", 8000)
		self.assertEqual(result3, 8000)

		frappe.db.get_value = lambda *a, **k: 25
		result4 = get_available_budget_for_month("May", "DummyDist", 10000)
		self.assertEqual(result4, 2500.0)

		default_controls = get_control_actions()
		self.assertEqual(default_controls["mr_action"], "Ignore")

		class DummyMD:
			applicable_on_material_request = 1
			applicable_on_purchase_order = 1
			applicable_on_booking_actual_expenses = 1
			action_if_accumulated_monthly_budget_exceeded_on_mr = "Stop"
			action_if_accumulated_monthly_budget_exceeded_on_po = "Warn"
			action_if_accumulated_monthly_budget_exceeded_on_actual = "Ignore"

		frappe.get_doc = lambda doctype, name=None: DummyMD()
		controls = get_control_actions("DummyDist")
		self.assertEqual(controls["mr_action"], "Stop")
