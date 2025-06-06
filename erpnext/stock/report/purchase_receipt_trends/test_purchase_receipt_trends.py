import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from erpnext.stock.report.purchase_receipt_trends.purchase_receipt_trends import (
	execute,
	get_chart_data,
)
from erpnext.stock.doctype.purchase_receipt.test_purchase_receipt import (
	make_purchase_receipt,
)
from erpnext.stock.doctype.item.test_item import create_item
from erpnext.stock.doctype.warehouse.test_warehouse import create_warehouse


class TestPurchaseReceiptTrendsReport(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.company = frappe.get_doc("Company", "_Test Company")

		# Set required accounts for GL entries
		frappe.db.set_value("Company", self.company.name, "stock_received_but_not_billed", "_Test Stock Received But Not Billed - _TC")
		frappe.db.set_value("Company", self.company.name, "default_expense_account", "Cost of Goods Sold - _TC")
		frappe.db.set_value("Company", self.company.name, "default_inventory_account", "Stock In Hand - _TC")
		frappe.db.set_value("Company", self.company.name, "default_payable_account", "Creditors - _TC")
		frappe.db.set_value("Company", self.company.name, "stock_adjustment_account", "Stock Adjustment - _TC")
		frappe.db.set_value("Company", self.company.name, "cost_center", "Main - _TC")

		self.supplier_names = []
		self.purchase_receipts = []

		self.warehouse = create_warehouse("_Test PR Trends WH")

		for i in range(12):
			supplier_name = f"Test Supplier {i}"
			if not frappe.db.exists("Supplier", supplier_name):
				supplier = frappe.get_doc({
					"doctype": "Supplier",
					"supplier_name": supplier_name,
					"supplier_type": "Company"
				}).insert()
			else:
				supplier = frappe.get_doc("Supplier", supplier_name)

			# Ensure default payable account is set
			frappe.db.set_value("Supplier", supplier.name, "default_payable_account", "Creditors - _TC")

			self.supplier_names.append(supplier.name)

			item = create_item(f"_Test Item Chart {i}", {
				"is_stock_item": 1,
				"stock_uom": "Nos"
			})

			pr = make_purchase_receipt(
				company=self.company.name,
				supplier=supplier.name,
				item_code=item.name,
				qty=1,
				rate=100 + i,
				warehouse=self.warehouse.name
			)
			pr.submit()
			self.purchase_receipts.append(pr)

		self.default_filters = frappe._dict({
			"company": self.company.name,
			"fiscal_year": frappe.defaults.get_user_default("fiscal_year") or "2024-2025",
			"based_on": "Supplier",
			"group_by": "Item",
			"period": "Monthly",
			"period_based_on": "posting_date"
		})

	def tearDown(self):
		for pr in self.purchase_receipts:
			if frappe.db.exists("Purchase Receipt", pr.name):
				doc = frappe.get_doc("Purchase Receipt", pr.name)
				if doc.docstatus == 1:
					doc.cancel()
				doc.delete()

		for supplier in self.supplier_names:
			if frappe.db.exists("Supplier", supplier):
				frappe.delete_doc("Supplier", supplier, force=True)

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
				"companies": [{"company": self.company.name}]
			}).insert(ignore_permissions=True)

		filters = frappe._dict({
			"company": self.company.name,
			"fiscal_year": "2099-2100",
			"based_on": "Supplier",
			"group_by": "Item",
			"period": "Monthly",
			"period_based_on": "posting_date"
