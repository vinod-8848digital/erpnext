import frappe
from frappe.tests.utils import FrappeTestCase
from erpnext.buying.doctype.purchase_order.test_purchase_order import create_purchase_order
from .purchase_order_trends import execute

class TestPurchaseOrderTrends(FrappeTestCase):
	def setUp(self):
		po = create_purchase_order()
		self.filters = frappe._dict(
			company = "_Test Company",
			period = "Monthly",
			fiscal_year = "2025",
			period_based_on = "Posting Date",
			based_on = "Item"
		)

	def tearDown(self):
		frappe.db.rollback()

	def test_purchase_order_trends_report(self):
		# based on item
		data = execute(self.filters)
		item_data = data[1][0]
		self.assertEqual(item_data[0], '_Test Item')

		# based on supplier
		self.filters.update(
			{
				"based_on": "Supplier"
			}
		)
		s_data = execute(self.filters)
		supplier_data = s_data[1][0]
		self.assertEqual(supplier_data[0], "_Test Supplier")
		self.assertEqual(supplier_data[1], "_Test Supplier Group")

		# based on supplier group
		self.filters.update(
			{
				"based_on": "Supplier Group"
			}
		)
		sg_data = execute(self.filters)
		supplier_group_data = sg_data[1][0]
		self.assertEqual(supplier_group_data[0], "_Test Supplier Group")

		# based on item group
		self.filters.update(
			{
				"based_on": "Item Group"
			}
		)
		ig_data = execute(self.filters)
		item_group_data = ig_data[1][0]
		self.assertEqual(item_group_data[0], "_Test Item Group")

		# based on group by item
		self.filters["group_by"] = "Item"
		g_data = execute(self.filters)
		group_item_data = g_data[1][0]
		self.assertEqual(group_item_data[0], "_Test Item Group")