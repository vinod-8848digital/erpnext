import unittest
import frappe
from frappe import _dict
import json
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

	def test_no_difference_data_skipped_T_SLV_006(self):
		# Create stock entry with correct rate matching valuation
		from erpnext.stock.doctype.stock_entry.test_stock_entry import make_stock_entry
		se = make_stock_entry(
			item_code=self.item.name,
			qty=1,
			rate=100,  # Matches valuation_rate
			to_warehouse=self.warehouse
		)
		se.submit()

		_, data = stock_ledger_variance.execute({
			"company": self.company,
			"item_code": self.item.name,
			"warehouse": self.warehouse,
			"difference_in": "Qty"
		})
		print('data', data)

		self.assertTrue(all(row["difference_in_qty"] == 0 for row in data) or not data)

	def test_fifo_queue_path_T_SLV_007(self):
		_, data = stock_ledger_variance.execute({
			"company": self.company,
			"item_code": self.item.name,
			"warehouse": self.warehouse
		})
		print('data', data)
		if data:
			# Simulate FIFO queue path
			data[0]["stock_queue"] = json.dumps([{"qty": 1, "rate": 200}])
			data[0]["fifo_value_diff"] = 50
			data[0]["fifo_qty_diff"] = 1
			data[0]["fifo_valuation_diff"] = 10

			from erpnext.stock.report.stock_ledger_variance import stock_ledger_variance as slv
			valuation_method = "FIFO"

			result = slv.has_difference(data[0], 2, None, valuation_method)
			self.assertTrue(result)

	def test_with_unknown_difference_type_T_SLV_008(self):
		_, data = stock_ledger_variance.execute({
			"company": self.company,
			"item_code": self.item.name,
			"warehouse": self.warehouse,
			"difference_in": "RandomValue"  # Unknown difference type
		})
		self.assertIsInstance(data, list)

	def test_include_disabled_filter_T_SLV_009(self):
		_, data = stock_ledger_variance.execute({
			"company": self.company,
			"item_code": self.item.name,
			"warehouse": self.warehouse,
			"include_disabled": 1
		})
		self.assertIsInstance(data, list)

	def test_has_difference_conditions_T_SLV_010(self):
		from erpnext.stock.report.stock_ledger_variance import stock_ledger_variance as slv

		row = _dict({
			"difference_in_qty": 0,
			"diff_value_diff": 0,
			"valuation_diff": 0,
			"stock_queue": json.dumps([{"qty": 1, "rate": 100}]),
			"fifo_value_diff": 50,
			"fifo_qty_diff": 1,
			"fifo_valuation_diff": 20,
		})

		# Covers FIFO and non-moving average case
		result = slv.has_difference(row, 2, None, "FIFO")
		self.assertTrue(result)





