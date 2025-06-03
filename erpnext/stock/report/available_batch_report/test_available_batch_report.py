# Copyright (c) 2025, Frappe Technologies
# License: GNU General Public License v3. See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today, add_days
import erpnext.stock.report.available_batch_report.available_batch_report as available_batch_report
from erpnext.stock.doctype.warehouse.test_warehouse import create_warehouse



class TestAvailableBatchReport(FrappeTestCase):
	def setUp(self):
		find_warehouse = frappe.db.get_value('Warehouse', {"company": "_Test Company"}, ['name'])
		if not find_warehouse:
			warehouse_name = "Auto Created Warehouse"
			new_warehouse = create_warehouse(warehouse_name, {"company": "_Test Company"})
			find_warehouse = new_warehouse.name

		self.batch_no = "TEST-BATCH-001"

		if not frappe.db.exists("GST HSN Code", "11112222"):
			frappe.get_doc({
				"doctype": "GST HSN Code",
				"hsn_code": "11112222",
				"description": "Test HSN Code for Automation",
				"item_type": "Goods"
			}).insert(ignore_permissions=True)

		self.item_code = "Test Item"
		if not frappe.db.exists("Item", self.item_code):
			frappe.get_doc({
				"doctype": "Item",
				"item_code": self.item_code,
				"item_name": "Test Item",
				"stock_uom": "Nos",
				"is_stock_item": 1,
				"gst_hsn_code": "11112222",
				"has_batch_no": 1
			}).insert(ignore_permissions=True)

		if not frappe.db.exists("Batch", self.batch_no):
			frappe.get_doc({
				"doctype": "Batch",
				"item": self.item_code,
				"batch_id": self.batch_no,
				"expiry_date": add_days(today(), 30)
			}).insert(ignore_permissions=True)

		# if not frappe.db.exists("Stock Entry", "Test Voucher"):
		se = frappe.get_doc({
			"doctype": "Stock Entry",
			"company": "_Test Company",
			"stock_entry_type": "Material Receipt",  # or whatever type fits your case
			"posting_date": today(),
			"items": [{
				"item_code": self.item_code,
				"qty": 10,
				"t_warehouse": find_warehouse,
				"batch_no": self.batch_no,
				"uom": "Nos"
			}]
		})
		se.insert(ignore_permissions=True)
		se.submit() 

		frappe.get_doc({
			"doctype": "Stock Ledger Entry",
			"item_code": self.item_code,
			"warehouse": find_warehouse,
			"batch_no": self.batch_no,
			"posting_date": today(),
			"posting_time": "10:00",
			"voucher_type": "Stock Entry",
			"voucher_no": se.name,
			"voucher_detail_no": "Test Voucher Detail",
			"actual_qty": 10,
			"stock_uom": "Nos",
			"is_cancelled": 0,
			"company": "_Test Company"
		}).insert(ignore_permissions=True)

	def test_get_columns_with_item_name(self):
		filters = frappe._dict(show_item_name=True)
		columns = available_batch_report.get_columns(filters)
		labels = [col["label"] for col in columns]
		self.assertIn("Item Name", labels)
		self.assertIn("Batch No", labels)

	def test_get_columns_without_item_name(self):
		filters = frappe._dict(show_item_name=False)
		columns = available_batch_report.get_columns(filters)
		labels = [col["label"] for col in columns]
		self.assertNotIn("Item Name", labels)

	def test_parse_batchwise_data_excludes_zero_qty(self):
		batchwise_data = {
			("Item-A", "Warehouse-A", "Batch-A"): frappe._dict(
				item_code="Item-A",
				warehouse="Warehouse-A",
				batch_no="Batch-A",
				expiry_date=today(),
				balance_qty=0
			),
			("Item-B", "Warehouse-B", "Batch-B"): frappe._dict(
				item_code="Item-B",
				warehouse="Warehouse-B",
				batch_no="Batch-B",
				expiry_date=today(),
				balance_qty=5
			)
		}
		result = available_batch_report.parse_batchwise_data(batchwise_data)
		self.assertEqual(len(result), 1)
		self.assertEqual(result[0].item_code, "Item-B")

	def test_execute_returns_data(self):
		filters = frappe._dict(
			item_code=self.item_code,
			to_date=today(),
			show_item_name=True,
			include_expired_batches=True
		)

		columns, data = available_batch_report.execute(filters)

		self.assertTrue(columns)
		self.assertTrue(data)
		self.assertEqual(data[0].item_code, self.item_code)
		self.assertEqual(data[0].batch_no, self.batch_no)

	def test_get_data_empty_filters(self):
		filters = frappe._dict(
			item_code="Non-Existent-Item",
			to_date=today(),
			include_expired_batches=False,
			show_item_name=False
		)
		data = available_batch_report.get_data(filters)
		self.assertEqual(data, [])
