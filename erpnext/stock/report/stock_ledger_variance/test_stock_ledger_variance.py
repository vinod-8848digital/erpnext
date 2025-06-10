import unittest
import frappe
from erpnext.stock.report.stock_ledger_variance import stock_ledger_variance
from erpnext.stock.doctype.item.test_item import create_item

class TestStockLedgerVarianceReport(unittest.TestCase):
	def setUp(self):
		super().setUp()
		self.company = "_Test Company"

		self.item = create_item(item_code="Test Item SLV", is_stock_item=1, valuation_rate=100)

		self.warehouse = "_Test Warehouse - _TC"

		from erpnext.stock.doctype.stock_entry.test_stock_entry import make_stock_entry

		self.stock_entry = make_stock_entry(
			item_code=self.item.name,
			qty=5,
			rate=150,
			to_warehouse=self.warehouse
		)
		self.stock_entry.submit()

	def test_execute_with_default_filters_T_SLV_001(self):
		columns, data = stock_ledger_variance.execute({
			"company": self.company,
			"item_code": self.item.name,
			"warehouse": self.warehouse
		})
		self.assertIsInstance(columns, list)
		self.assertIsInstance(data, list)

	def test_execute_with_qty_difference_T_SLV_002(self):
		_, data = stock_ledger_variance.execute({
			"company": self.company,
			"item_code": self.item.name,
			"warehouse": self.warehouse,
			"difference_in": "Qty"
		})
		for row in data:
			self.assertIn("difference_in_qty", row)

	def test_execute_with_value_difference_T_SLV_003(self):
		_, data = stock_ledger_variance.execute({
			"company": self.company,
			"item_code": self.item.name,
			"warehouse": self.warehouse,
			"difference_in": "Value"
		})
		for row in data:
			self.assertIn("diff_value_diff", row)

	def test_execute_with_valuation_difference_T_SLV_004(self):
		_, data = stock_ledger_variance.execute({
			"company": self.company,
			"item_code": self.item.name,
			"warehouse": self.warehouse,
			"difference_in": "Valuation"
		})
		for row in data:
			self.assertIn("valuation_diff", row)

	def test_execute_with_invalid_item_T_SLV_005(self):
		_, data = stock_ledger_variance.execute({
			"company": self.company,
			"item_code": "Invalid Item",
			"warehouse": self.warehouse
		})
		self.assertEqual(data, [])
