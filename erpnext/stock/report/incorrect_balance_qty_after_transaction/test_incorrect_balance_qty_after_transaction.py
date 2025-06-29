import frappe
from frappe.tests.utils import FrappeTestCase
from erpnext.stock.report.incorrect_balance_qty_after_transaction.incorrect_balance_qty_after_transaction import execute
from erpnext.stock.doctype.warehouse.test_warehouse import create_warehouse
from erpnext.stock.doctype.item.test_item import create_item
from erpnext.accounts.doctype.payment_entry.test_payment_entry import create_company
from erpnext.accounts.utils import nowdate
from erpnext.stock.doctype.stock_entry.test_stock_entry import get_or_create_fiscal_year
from erpnext import is_perpetual_inventory_enabled
from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_territory
from datetime import date
from frappe.utils import nowdate, add_days




class TestIncorrectBalanceQtyReport(FrappeTestCase):
    def setUp(self):
        # Create company
        self.company = create_company("_Test Company")
        self.company = "_Test Company"
        get_or_create_fiscal_year("_Test Company")

        # Create warehouse
        self.warehouse = create_warehouse(
            warehouse_name="_Test Warehouse - _TC",
            company=self.company
        )

        # Create item
        self.item_code = create_item(
            item_code="_Test Item",
            valuation_rate=100,
            warehouse=self.warehouse,
            company=self.company,
        )



    def test_get_data_detects_difference_due_to_stock_reconciliation(self):
        from erpnext.stock.report.incorrect_balance_qty_after_transaction.incorrect_balance_qty_after_transaction import get_data

        # Step 1: Create regular stock entry
        stock_entry = frappe.get_doc({
            "doctype": "Stock Entry",
            "stock_entry_type": "Material Receipt",
            "company": self.company,
            "to_warehouse": self.warehouse,
            "items": [{
                "item_code": self.item_code,
                "qty": 5,
                "rate": 100,
                "t_warehouse": self.warehouse,
                # "batch_no": self.batch.name
            }]
        })
        stock_entry.insert()
        stock_entry.submit()

        # Step 2: Create Stock Reconciliation with qty mismatch and no batch (to trigger reset)
        stock_recon = frappe.get_doc({
            "doctype": "Stock Reconciliation",
            "company": self.company,
            "purpose": "Stock Reconciliation",
            "items": [{
                "item_code": self.item_code,
                "warehouse": self.warehouse,
                "qty": 20,
                "valuation_rate": 100
            }],
            "posting_date": nowdate(),
            "posting_time": "10:00:00"
        })
        stock_recon.insert()
        stock_recon.submit()

        # Step 3: Manually tamper SLE to simulate incorrect final qty (e.g., 18 instead of 20)
        sle = frappe.db.get_value(
            "Stock Ledger Entry",
            {"voucher_type": "Stock Reconciliation", "voucher_no": stock_recon.name},
            ["name"],
        )
        print("sle",sle)
        if sle:
            frappe.db.set_value("Stock Ledger Entry", sle, "qty_after_transaction", 18)
            frappe.db.set_value("Stock Ledger Entry", sle, "batch_no", "")  # <-- CRUCIAL
            frappe.db.set_value("Stock Ledger Entry", sle, "posting_date", add_days(nowdate(), 1))
            frappe.db.set_value("Stock Ledger Entry", sle, "posting_time", "23:59:59")
            frappe.db.commit()

        # Step 4: Run report
        data = get_data({
            "item_code": self.item_code.name,
            "warehouse": self.warehouse,
            "company": self.company
        })


        # Step 5: Check for difference > 0.5
        has_diff = any(
            isinstance(row, dict) and row.get("differnce") and abs(row.get("differnce", 0)) > 0.5
            for row in data
        )

        self.assertTrue(has_diff, "Expected at least one row with incorrect qty due to reconciliation mismatch")


    def test_execute_validates_data_and_appends_empty_dict(self):
        from erpnext.stock.report.incorrect_balance_qty_after_transaction import incorrect_balance_qty_after_transaction as report

        # Step 1: Insert a Stock Entry
        stock_entry = frappe.get_doc({
            "doctype": "Stock Entry",
            "stock_entry_type": "Material Receipt",
            "company": self.company,
            "to_warehouse": self.warehouse,
            "items": [{
                "item_code": self.item_code,
                "qty": 10,
                "rate": 100,
                "t_warehouse": self.warehouse,
            }]
        })
        stock_entry.insert()
        stock_entry.submit()

        # Step 2: Stock Reconciliation to create discrepancy
        recon = frappe.get_doc({
            "doctype": "Stock Reconciliation",
            "company": self.company,
            "purpose": "Stock Reconciliation",
            "items": [{
                "item_code": self.item_code,
                "warehouse": self.warehouse,
                "qty": 15,  # Reconcile to 15
                "valuation_rate": 100
            }],
            "posting_date": nowdate(),
            "posting_time": "11:00:00"
        })
        recon.insert()
        recon.submit()

        # Step 3: Manually alter qty_after_transaction to simulate discrepancy (e.g., it should be 15 but we fake it as 12)
        sle_name = frappe.db.get_value(
            "Stock Ledger Entry",
            {"voucher_type": "Stock Reconciliation", "voucher_no": recon.name},
            "name"
        )

        frappe.db.set_value("Stock Ledger Entry", sle_name, "qty_after_transaction", 12)
        frappe.db.set_value("Stock Ledger Entry", sle_name, "batch_no", "")  # Important to hit reconciliation logic
        frappe.db.commit()

        # Step 4: Run report
        columns, data = report.execute({
            "item_code": self.item_code.name,
            "warehouse": self.warehouse,
            "company": self.company
        })

        # Step 5: Verify a row with discrepancy and an empty row is returned (this ensures both res.append(row) and res.append({}) are hit)
        found_row = False
        found_empty_dict = False

        for i in range(len(data) - 1):
            if data[i].get("differnce") and data[i + 1] == {}:
                found_row = True
                found_empty_dict = True
                break

        self.assertTrue(found_row and found_empty_dict, "Expected validate_data to append a row and an empty dict")

    def test_validate_data_appends_row_and_empty_dict_for_qty_mismatch(self):
        from erpnext.stock.report.incorrect_balance_qty_after_transaction import incorrect_balance_qty_after_transaction as report

        # Create initial stock entry
        stock_entry = frappe.get_doc({
            "doctype": "Stock Entry",
            "stock_entry_type": "Material Receipt",
            "company": self.company,
            "to_warehouse": self.warehouse,
            "items": [{
                "item_code": self.item_code,
                "qty": 10,
                "rate": 100,
                "t_warehouse": self.warehouse
            }]
        })
        stock_entry.insert()
        stock_entry.submit()

        # Create stock reconciliation with reset logic
        stock_recon = frappe.get_doc({
            "doctype": "Stock Reconciliation",
            "company": self.company,
            "purpose": "Stock Reconciliation",
            "items": [{
                "item_code": self.item_code,
                "warehouse": self.warehouse,
                "qty": 20,
                "valuation_rate": 100
            }],
            "posting_date": nowdate(),
            "posting_time": "11:59:59"
        })
        stock_recon.insert()
        stock_recon.submit()

        # Tamper the Stock Ledger Entry to simulate mismatch
        sle_name = frappe.db.get_value(
            "Stock Ledger Entry",
            {"voucher_type": "Stock Reconciliation", "voucher_no": stock_recon.name},
            "name"
        )

        # Set the qty_after_transaction to simulate error and empty batch_no
        frappe.db.set_value("Stock Ledger Entry", sle_name, {
            "qty_after_transaction": 17,  # Should be 20, introduce diff of 3
            "batch_no": "",
        })
        frappe.db.commit()

        # Run report
        columns, data = report.execute({
            "company": self.company,
            "warehouse": self.warehouse,
            "item_code": self.item_code.name
        })

        # Find whether a row followed by an empty dict exists
        found_error_row_and_blank = False
        for i in range(len(data) - 1):
            if isinstance(data[i], dict) and data[i].get("differnce") and data[i + 1] == {}:
                found_error_row_and_blank = True
                break

        self
