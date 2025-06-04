from types import SimpleNamespace
import frappe
from frappe.tests.utils import FrappeTestCase

import erpnext.stock.report.serial_no_ledger.serial_no_ledger as snl


class TestSerialNoLedgerReport(FrappeTestCase):
    def setUp(self):
        self.filters = {}

    def test_get_columns(self):
        columns = snl.get_columns(self.filters)
        self.assertIsInstance(columns, list)
        self.assertTrue(any(isinstance(col, dict) and col.get("fieldname") == "posting_date" for col in columns))

    def test_get_serial_nos_no_filter(self):
        def fake_get_all(doctype, fields, filters, order_by):
            self.assertIn("parent", filters)
            return [
                {"serial_no": "SN-003", "parent": "bundle-1", "stock_value_difference": 20},
                {"serial_no": "SN-004", "parent": "bundle-1", "stock_value_difference": 30},
            ]

        frappe.get_all = fake_get_all
        serial_bundle_ids = ["bundle-1", "bundle-2"]
        serial_nos = snl.get_serial_nos({}, serial_bundle_ids)
        self.assertIn("bundle-1", serial_nos)

    # def test_get_serial_nos_with_serial_no_filter(self):
    #     original_get_all = frappe.get_all

    #     def fake_get_all(doctype, fields, filters, order_by):
    #         self.assertEqual(filters.get("serial_no"), "SN-001")
    #         return [{"serial_no": "SN-001", "parent": "bundle-1", "stock_value_difference": 15}]

    #     frappe.get_all = fake_get_all
    #     try:
    #         serial_nos = snl.get_serial_nos({"serial_no": "SN-001"}, ["bundle-1"])
    #         self.assertEqual(serial_nos["bundle-1"][0]["serial_no"], "SN-001")
    #     finally:
    #         frappe.get_all = original_get_all

    def test_get_data_no_stock_ledgers(self):
        snl.get_stock_ledger_entries = lambda filters, to_date, order, check_serial_no: []
        data = snl.get_data({})
        self.assertEqual(data, [])

    def test_get_data_with_stock_ledger(self):
        sle = SimpleNamespace(
            posting_date="2025-01-01",
            posting_time="12:00:00",
            voucher_type="Purchase Invoice",
            voucher_no="PINV-0001",
            actual_qty=5,
            company="TestCo",
            warehouse="WH-001",
            serial_no="SN-001,SN-002",
            serial_and_batch_bundle="bundle-1",
            stock_value_difference=50,
        )

        snl.get_stock_ledger_entries = lambda filters, to_date, order, check_serial_no: [sle]
        snl.get_serial_nos = lambda filters, bundle_ids: {
            "bundle-1": [
                {"serial_no": "SN-003", "valuation_rate": 20},
                {"serial_no": "SN-004", "valuation_rate": 30},
            ]
        }

        frappe.db.get_value = lambda dt, dn, fld: "Test Supplier" if fld == "supplier" else None

        filters = {"serial_no": "SN-001"}
        data = snl.get_data(filters)

        self.assertTrue(any(d.get("serial_no") == "SN-001" for d in data))
        self.assertTrue(any(d.get("serial_no") == "SN-003" for d in data))
        self.assertTrue(any(d.get("qty") == 1 for d in data))

    def test_execute(self):
        filters = {"item_code": "ITEM-001"}
        columns, data = snl.execute(filters)
        self.assertIsInstance(columns, list)
        self.assertIsInstance(data, list)

    # # New test for division by zero (actual_qty == 0)
    # def test_get_data_division_by_zero(self):
    #     sle = SimpleNamespace(
    #         posting_date="2025-01-01",
    #         posting_time="12:00:00",
    #         voucher_type="Purchase Invoice",
    #         voucher_no="PINV-0001",
    #         actual_qty=0,
    #         company="TestCo",
    #         warehouse="WH-001",
    #         serial_no="SN-001",
    #         serial_and_batch_bundle=None,
    #         stock_value_difference=0,
    #     )

    #     snl.get_stock_ledger_entries = lambda filters, to_date, order, check_serial_no: [sle]
    #     snl.get_serial_nos = lambda filters, bundle_ids: {}

    #     frappe.db.get_value = lambda dt, dn, fld: None

    #     filters = {}
    #     # Should not raise ZeroDivisionError, valuation_rate should be handled safely
    #     data = snl.get_data(filters)
    #     self.assertTrue(all('valuation_rate' in d for d in data))  # valuation_rate should be present even if 0

    # # New test when both serial_no and serial_and_batch_bundle are missing or empty
    # def test_get_data_no_serial_no_and_no_bundle(self):
    #     sle = SimpleNamespace(
    #         posting_date="2025-01-01",
    #         posting_time="12:00:00",
    #         voucher_type="Other Voucher",
    #         voucher_no="OV-0001",
    #         actual_qty=10,
    #         company="TestCo",
    #         warehouse="WH-001",
    #         serial_no=None,
    #         serial_and_batch_bundle=None,
    #         stock_value_difference=100,
    #     )
    #     snl.get_stock_ledger_entries = lambda filters, to_date, order, check_serial_no: [sle]
    #     snl.get_serial_nos = lambda filters, bundle_ids: {}

    #     frappe.db.get_value = lambda dt, dn, fld: None

    #     data = snl.get_data({})
    #     self.assertEqual(len(data), 1)
    #     self.assertIsNone(data[0].get("serial_no"))
    #     self.assertEqual(data[0].get("qty"), 1)
    #     self.assertEqual(data[0].get("status"), "Active")

    # New test for party field returning None
    def test_get_data_party_field_none(self):
        sle = SimpleNamespace(
            posting_date="2025-01-01",
            posting_time="12:00:00",
            voucher_type="Random Voucher",
            voucher_no="RV-0001",
            actual_qty=3,
            company="TestCo",
            warehouse="WH-001",
            serial_no="SN-005",
            serial_and_batch_bundle=None,
            stock_value_difference=30,
        )
        snl.get_stock_ledger_entries = lambda filters, to_date, order, check_serial_no: [sle]
        snl.get_serial_nos = lambda filters, bundle_ids: {}

        # Simulate frappe.db.get_value returning None for party field
        frappe.db.get_value = lambda dt, dn, fld: None

        data = snl.get_data({})
        self.assertEqual(data[0].get("party"), None)
        self.assertEqual(data[0].get("party_type"), None)

