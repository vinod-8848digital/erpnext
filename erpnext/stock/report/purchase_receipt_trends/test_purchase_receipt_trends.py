import unittest
import frappe
from erpnext.stock.report.purchase_receipt_trends.purchase_receipt_trends import execute, get_chart_data
from erpnext.stock.doctype.purchase_receipt.test_purchase_receipt import (
	make_purchase_receipt,
)
from frappe.utils import today, add_days, getdate


class TestPurchaseReceiptTrendsReport(unittest.TestCase):
	def setUp(self):
		from erpnext.stock.doctype.item.test_item import create_item
		company = frappe.get_doc("Company", "_Test Company")

		# Set mandatory accounts for stock transactions
		frappe.db.set_value("Company", company.name, "stock_received_but_not_billed", "_Test Stock Received But Not Billed - _TC")
		frappe.db.set_value("Company", company.name, "default_expense_account", "Cost of Goods Sold - _TC")
		frappe.db.set_value("Company", company.name, "default_inventory_account", "Stock In Hand - _TC")
		self.supplier_names = []
		for i in range(12):
			supplier_name = f"Test Supplier {i}"
			if not frappe.db.exists("Supplier", supplier_name):
				supplier = frappe.get_doc({
                            "doctype": "Supplier",
                            "supplier_name": supplier_name,
                            "supplier_type": "Company"
                        })
				supplier.insert()
			self.supplier_names.append(supplier_name)
			# frappe.db.set_value("Supplier", supplier_name, "default_payable_account", "Creditors - _TC")
		self.purchase_receipts = []
		for i, supplier_name in enumerate(self.supplier_names):
			item = create_item(f"_Test Item Chart {i}", {
                "is_stock_item": 1,
                "stock_uom": "Nos"
            })
			pr = make_purchase_receipt(
                company="_Test Company",
                supplier=supplier_name,
                item_code=item.name,
                qty=1,
                rate=100 + i
            )
			pr.submit()
			self.purchase_receipts.append(pr)
		self.default_filters = frappe._dict({
            "company": "_Test Company",
            "fiscal_year": frappe.defaults.get_user_default("fiscal_year") or "2024-2025",
            "based_on": "Supplier",
            "group_by": "Item",
            "period": "Monthly",
            "period_based_on": "posting_date"
        })


	def tearDown(self):
		for pr in self.purchase_receipts:
			if frappe.db.exists("Purchase Receipt", pr.name):
				frappe.get_doc("Purchase Receipt", pr.name).cancel()
		for supplier in self.supplier_names:
			if frappe.db.exists("Supplier", supplier):
				frappe.get_doc("Supplier", supplier).disable = 1

	@frappe.whitelist()
	def test_execute_with_valid_filters(self):
		cols, data, none_val, chart = execute(self.default_filters)

		self.assertIsInstance(cols, list)
		self.assertGreater(len(cols), 0)

		self.assertIsInstance(data, list)
		self.assertGreater(len(data), 0)

		self.assertIsInstance(chart, dict)
		self.assertIn("datasets", chart["data"])
		self.assertIn("labels", chart["data"])

	def test_execute_with_empty_data(self):
		if not frappe.db.exists("Fiscal Year", "2099-2100"):
			frappe.get_doc({
                "doctype": "Fiscal Year",
                "year": "2099-2100",
                "year_start_date": getdate("2099-04-01"),
                "year_end_date": getdate("2100-03-31"),
                "disabled": 0,
				"companies": [{'company': "_Test Company"}]
            }).insert(ignore_permissions=True)
		filters = frappe._dict({
            "company": "_Test Company",
            "fiscal_year": "2099-2100",
            "based_on": "Supplier",
            "group_by": "Item",
            "period": "Monthly",
            "period_based_on": "posting_date"
        })
		cols, data, none_val, chart = execute(filters)
		self.assertEqual(data, [])

	def test_chart_data_top_10_cutoff(self):
		_, data, _, _ = execute(self.default_filters)
		chart = get_chart_data(data, self.default_filters)

		self.assertGreater(len(chart["data"]["labels"]), 0)
		self.assertLessEqual(len(chart["data"]["labels"]), 10)

	def test_chart_data_without_group_by(self):
		filters = self.default_filters.copy()
		del filters["group_by"]

		_, data, _, _ = execute(filters)
		chart = get_chart_data(data, filters)

		self.assertLessEqual(len(chart["data"]["labels"]), 10)

	def test_chart_data_with_no_data(self):
		data = []
		chart = get_chart_data(data, self.default_filters)
		self.assertEqual(chart, [])

