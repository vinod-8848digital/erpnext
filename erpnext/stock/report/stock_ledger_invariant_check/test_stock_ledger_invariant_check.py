import unittest
import frappe
from frappe.test_runner import make_test_records_for_doctype
from erpnext.stock.report.stock_consumption_and_delivery.stock_consumption_and_delivery import get_suppliers_details

from erpnext.buying.doctype.supplier.supplier import make_supplier
from erpnext.stock.doctype.item.test_item import create_item
from erpnext.accounts.doctype.purchase_invoice.test_purchase_invoice import make_purchase_invoice


class TestStockLedgerInvariantCheck(unittest.TestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.warehouse = "_Test Warehouse"

		# Create two suppliers
		self.supplier1 = make_supplier("_Test Supplier 1")
		self.supplier2 = make_supplier("_Test Supplier 2")

		# Create two stock items
		self.item1 = create_item(
			"_Test Item SC 1",
			is_stock_item=1,
			inventory_account="_Test Account Cost for Goods Sold - _TC"
		)
		self.item2 = create_item(
			"_Test Item SC 2",
			is_stock_item=1,
			inventory_account="_Test Account Cost for Goods Sold - _TC"
		)

		# Create purchase invoices for both items with update_stock
		make_purchase_invoice(
			supplier=self.supplier1.name,
			item_code=self.item1.name,
			qty=2,
			rate=50,
			update_stock=1,
			warehouse=self.warehouse,
		)

		make_purchase_invoice(
			supplier=self.supplier2.name,
			item_code=self.item2.name,
			qty=3,
			rate=75,
			update_stock=1,
			warehouse=self.warehouse,
		)

	def test_get_suppliers_details_with_filter(self):
		# Apply supplier filter to only include supplier1
		filters = {"supplier": self.supplier1.name}
		item_supplier_map = get_suppliers_details(filters)

		# Should include item1 only
		self.assertIn(self.item1.name, item_supplier_map)
		self.assertNotIn(self.item2.name, item_supplier_map)

		# Also ensure supplier name is correctly mapped
		self.assertIn(self.supplier1.name, item_supplier_map[self.item1.name])

	def tearDown(self):
		frappe.delete_doc_if_exists("Supplier", "_Test Supplier 1", force=1)
		frappe.delete_doc_if_exists("Supplier", "_Test Supplier 2", force=1)
		frappe.delete_doc_if_exists("Item", "_Test Item SC 1", force=1)
		frappe.delete_doc_if_exists("Item", "_Test Item SC 2", force=1)
