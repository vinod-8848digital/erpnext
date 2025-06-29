from types import SimpleNamespace
import frappe
from frappe.tests.utils import FrappeTestCase
import erpnext.stock.report.serial_no_ledger.serial_no_ledger as snl


class TestSerialNoLedger(FrappeTestCase):
    def setUp(self):
        self.filters = {}

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

        frappe.db.get_value = lambda dt, dn, fld, **kwargs: "Test Supplier" if fld == "supplier" else None

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

    def test_get_data_division_by_zero(self):
        sle = SimpleNamespace(
            posting_date="2025-01-01",
            posting_time="12:00:00",
            voucher_type="Purchase Invoice",
            voucher_no="PINV-0001",
            actual_qty=1,
            company="TestCo",
            warehouse="WH-001",
            serial_no="SN-001",
            serial_and_batch_bundle=None,
            stock_value_difference=0,
        )

        snl.get_stock_ledger_entries = lambda filters, to_date, order, check_serial_no: [sle]
        snl.get_serial_nos = lambda filters, bundle_ids: {}
        frappe.db.get_value = lambda dt, dn, fld, **kwargs: None

        filters = {}
        data = snl.get_data(filters)
        self.assertTrue(all("valuation_rate" in d for d in data))

    def test_get_data_no_serial_no_and_no_bundle(self):
        sle = SimpleNamespace(
            posting_date="2025-01-01",
            posting_time="12:00:00",
            voucher_type="Other Voucher",
            voucher_no="OV-0001",
            actual_qty=10,
            company="TestCo",
            warehouse="WH-001",
            serial_no=None,
            serial_and_batch_bundle=None,
            stock_value_difference=100,
        )
        snl.get_stock_ledger_entries = lambda filters, to_date, order, check_serial_no: [sle]
        snl.get_serial_nos = lambda filters, bundle_ids: {}
        frappe.db.get_value = lambda dt, dn, fld, **kwargs: None

        data = snl.get_data({})
        self.assertEqual(len(data), 0)

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
        frappe.db.get_value = lambda dt, dn, fld, **kwargs: None

        data = snl.get_data({})
        self.assertEqual(data[0].get("party"), None)
        self.assertEqual(data[0].get("party_type"), None)

    def test_get_data_zero_actual_qty(self):
        sle = SimpleNamespace(
            posting_date="2025-01-01",
            posting_time="12:00:00",
            voucher_type="Purchase Receipt",
            voucher_no="PR-0001",
            actual_qty=0,
            company="TestCo",
            warehouse="WH-001",
            serial_no="SN-ZERO",
            serial_and_batch_bundle=None,
            stock_value_difference=0,
        )

        snl.get_stock_ledger_entries = lambda filters, to_date, order, check_serial_no: [sle]
        snl.get_serial_nos = lambda filters, bundle_ids: {}
        frappe.db.get_value = lambda dt, dn, fld, **kwargs: "Test Supplier"

        data = snl.get_data({})
        self.assertEqual(len(data), 1, "Should not include rows with zero actual_qty")

    def test_get_data_multiple_sles_with_serial_and_bundle(self):
        sle1 = SimpleNamespace(
            posting_date="2025-01-01",
            posting_time="12:00:00",
            voucher_type="Purchase Receipt",
            voucher_no="PR-001",
            actual_qty=2,
            company="TestCo",
            warehouse="WH-001",
            serial_no="SN-001\nSN-002",
            serial_and_batch_bundle=None,
            stock_value_difference=200,
        )

        sle2 = SimpleNamespace(
            posting_date="2025-01-02",
            posting_time="13:00:00",
            voucher_type="Delivery Note",
            voucher_no="DN-001",
            actual_qty=-1,
            company="TestCo",
            warehouse="WH-001",
            serial_no=None,
            serial_and_batch_bundle="BND-001",
            stock_value_difference=-100,
        )

        snl.get_stock_ledger_entries = lambda filters, to_date, order, check_serial_no: [sle1, sle2]

        snl.get_serial_nos = lambda filters, bundle_ids: {
            "BND-001": [{"serial_no": "SN-003", "valuation_rate": 100}]
        }

        frappe.db.get_value = lambda dt, dn, fld, **kwargs: "Test Supplier" if fld == "supplier" else "Test Customer"

        data = snl.get_data({})

        serials = [row.get("serial_no") for row in data]
        self.assertIn("SN-001", serials)
        self.assertIn("SN-002", serials)
        self.assertIn("SN-003", serials)
        self.assertEqual(sum(row.get("qty", 0) for row in data), 1)

    def test_get_serial_nos_loop_and_mapping_logic(self):
        # Patch the correct reference inside the snl module
        original_get_all = snl.frappe.get_all

        try:
            # Provide mock data that would be returned by frappe.get_all
            mock_data = [
                frappe._dict({
                    "serial_no": "SN-A",
                    "parent": "BND-001",
                    "valuation_rate": 100
                }),
                frappe._dict({
                    "serial_no": "SN-B",
                    "parent": "BND-001",
                    "valuation_rate": -50  # Should be converted to abs() => 50
                }),
                frappe._dict({
                    "serial_no": "SN-C",
                    "parent": "BND-002",
                    "valuation_rate": 0
                })
            ]

            snl.frappe.get_all = lambda *args, **kwargs: mock_data

            filters = {}  # no filtering on serial_no
            bundle_ids = ["BND-001", "BND-002"]

            result = snl.get_serial_nos(filters, bundle_ids)

            expected = {
                "BND-001": [
                    {"serial_no": "SN-A", "valuation_rate": 100},
                    {"serial_no": "SN-B", "valuation_rate": 50},
                ],
                "BND-002": [
                    {"serial_no": "SN-C", "valuation_rate": 0},
                ]
            }

            self.assertEqual(result, expected)

        finally:
            # Restore the original frappe.get_all
            snl.frappe.get_all = original_get_all



    def test_execute_with_serial_no_filter_and_bundle(self):
        # Backup real methods
        original_get_all = snl.frappe.get_all
        original_get_stock_ledger_entries = snl.get_stock_ledger_entries
        original_get_serial_nos_from_sle = snl.get_serial_nos_from_sle
        original_db_get_value = frappe.db.get_value

        try:
            # Mock SLE with a bundle ID
            sle = SimpleNamespace(
                posting_date="2025-01-05",
                posting_time="14:00:00",
                voucher_type="Purchase Receipt",
                voucher_no="PR-999",
                actual_qty=2,
                company="TestCo",
                warehouse="WH-TEST",
                serial_no=None,
                serial_and_batch_bundle="BND-999",
                stock_value_difference=200,
            )

            snl.get_stock_ledger_entries = lambda filters, to_date, order, check_serial_no: [sle]

            # Provide serial_no filter so it covers both paths in get_serial_nos
            filters = {"serial_no": "SN-X"}

            # Mock frappe.get_all so we hit the loop in get_serial_nos
            snl.frappe.get_all = lambda *args, **kwargs: [
                frappe._dict({
                    "serial_no": "SN-X",
                    "parent": "BND-999",
                    "valuation_rate": 75
                }),
                frappe._dict({
                    "serial_no": "SN-Y",
                    "parent": "BND-999",
                    "valuation_rate": -25
                }),
            ]

            # Needed because get_data also calls this
            snl.get_serial_nos_from_sle = lambda serials: []

            frappe.db.get_value = lambda dt, dn, fld, **kwargs: "Test Supplier"

            columns, data = snl.execute(filters)
            print("data",data)

            # Validate serial_no and valuation_rate values
            serials = [d.get("serial_no") for d in data]
            self.assertIn("SN-X", serials)
            self.assertIn("SN-Y", serials)

            self.assertEqual(len(data), 2)
            for row in data:
                self.assertIn("valuation_rate", row)

        finally:
            # Restore all patched methods
            snl.frappe.get_all = original_get_all
            snl.get_stock_ledger_entries = original_get_stock_ledger_entries
            snl.get_serial_nos_from_sle = original_get_serial_nos_from_sle
            frappe.db.get_value = original_db_get_value