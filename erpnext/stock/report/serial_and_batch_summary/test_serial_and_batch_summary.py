# test_serial_and_batch_summary.py

import frappe
from frappe.tests.utils import FrappeTestCase
# from erpnext.stock.report.serial_and_batch_summary.serial_and_batch_summary import execute, get_data, get_filter_conditions, get_columns
from erpnext.accounts.doctype.payment_entry.test_payment_entry import create_company
# import frappe
import unittest
from datetime import date
from erpnext.stock.doctype.item.test_item import create_item
from erpnext.stock.doctype.warehouse.test_warehouse import create_warehouse
from erpnext.accounts.doctype.payment_entry.test_payment_entry import create_company
from erpnext.stock.report.serial_and_batch_summary.serial_and_batch_summary import execute, get_filter_conditions, get_columns

class TestSerialAndBatchBundleReport(unittest.TestCase):

    def setUp(self):
        self.company = create_company("_Test Company")
        self.company = "_Test Company"

        self.warehouse = create_warehouse(
            warehouse_name="_Test Warehouse - _TC",
            company=self.company
        )

        self.item = create_item(
            item_code="TESTITEM001",
            valuation_rate=100,
            warehouse=self.warehouse,
            company=self.company,
            has_batch_no = 1,
        )

        if frappe.db.exists("Batch", "BATCH201"):
            frappe.delete_doc("Batch", "BATCH201", force=True)

        self.batch = frappe.new_doc("Batch")
        self.batch.batch_id = "BATCH201"
        self.batch.item = self.item.name
        self.batch.batch_qty = 2
        self.batch.expiry_date = date(2030, 1, 1)
        self.batch.insert()

        # Add batch stock via stock entry
        self.stock_entry = create_stock_entry(
            item_code=self.item,
            warehouse=self.warehouse,
            qty=10,
            company="_Test Company",
            batch_no= self.batch
        )

            


        self.serial_batch_bundle = frappe.get_doc({
                "doctype": "Serial and Batch Bundle",
                "voucher_type": "Stock Entry",
                "voucher_no": self.stock_entry,
                "posting_date": "2024-06-01",
                "company": self.company,
                "item_code": self.item.name,
                "item_name": self.item.item_name,
                "docstatus": 1,
                "is_cancelled": 0,
                "type_of_transaction": "Inward",  # <-- REQUIRED FIELD
                "entries": [                       # <-- REQUIRED CHILD TABLE
                    {
                        # "serial_no": "SN001",
                        "batch_no": "BATCH201",
                        "warehouse": self.warehouse,
                        "incoming_rate": 100,
                        "stock_value_difference": 1000,
                        "qty": 10
                    }
                ]
            }).insert(ignore_permissions=True)

        self.entry = frappe.get_doc({
            "doctype": "Serial and Batch Entry",
            "parenttype": "Serial and Batch Bundle",
            "parent": self.serial_batch_bundle.name,
            # "serial_no": "SN001",
            "batch_no": "BATCH201",
            "warehouse": "_Test Warehouse - _TC",
            "incoming_rate": 100,
            "stock_value_difference": 1000,
            "qty": 10
        }).insert(ignore_permissions=True)

    def tearDown(self):
        frappe.db.rollback()  # Rollback everything to keep DB clean

    
    def test_execute_with_minimal_filters(self):
        filters = {
            "from_date": "2024-01-01",
            "to_date": "2025-01-01"
        }
        columns, data = execute(filters=filters)
        self.assertTrue(columns)
        self.assertTrue(data)

    
    def test_filter_combinations(self):
        filters = {
            "voucher_type": "Stock Entry",
            "item_code": self.item.name,
            "warehouse": "_Test Warehouse - _TC",
            "company": "Test Company",
            "from_date": "2024-01-01",
            "to_date": "2025-01-01"
        }
        data = frappe.get_all("Serial and Batch Bundle", filters={"item_code": self.item.name})
        filter_conditions = get_filter_conditions(filters)
        self.assertIn(["Serial and Batch Bundle", "voucher_type", "=", "Stock Entry"], filter_conditions)

    
    def test_columns_with_serial_and_batch(self):
        filters = {"item_code": self.item.name}
        data = [{
            "item_code": self.item.name,
            "company": "Test Company"
        }]
        columns = get_columns(filters, data)
        fieldnames = [col["fieldname"] for col in columns]
        # self.assertIn("serial_no", fieldnames)
        self.assertIn("batch_no", fieldnames)
        self.assertIn("qty", fieldnames)


    def test_get_voucher_type(self):
        from erpnext.stock.report.serial_and_batch_summary.serial_and_batch_summary import get_voucher_type
        result = get_voucher_type("Serial and Batch Bundle", "", "", 0, 10, {})
        self.assertIsInstance(result, list)

    
    def test_get_serial_nos(self):
        from erpnext.stock.report.serial_and_batch_summary.serial_and_batch_summary import get_serial_nos
        result = get_serial_nos("Serial and Batch Entry", "SN", "", 0, 10, {
            "voucher_no": ["STE-TEST-001"],
            "item_code": self.item.name
        })
        # self.assertTrue(any("SN001" in sn for sn in result))


    def test_get_batch_nos(self):
        from erpnext.stock.report.serial_and_batch_summary.serial_and_batch_summary import get_batch_nos
        result = get_batch_nos("Serial and Batch Entry", "BATCH", "", 0, 10, {
            "voucher_no": ["STE-TEST-001"],
            "item_code": self.item.name
        })
        self.assertTrue(any("BATCH201" in b for b in result))


def create_stock_entry(item_code, warehouse, qty, company,batch_no):
   se = frappe.get_doc({
       "doctype": "Stock Entry",
       "stock_entry_type": "Material Receipt",
       "company": company,
       "items": [{
           "item_code": item_code,
           "qty": qty,
           "uom": "Nos",
           "t_warehouse": warehouse,
           "rate": 100,
           "batch_no":batch_no
       }]
   })
   se.insert(ignore_permissions=True)
   se.submit()
   return se.name
