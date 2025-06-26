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
            has_batch_no = 0,
        )

        # self.batch = frappe.new_doc("Batch")
        # self.batch.item = self.item_code
        # self.batch.batch_qty = 5
        # self.batch.expiry_date = date(2030, 1, 1)
        # self.batch.batch_id = "TEST-BATCH-101"
        # self.batch.insert()

        # # Create price list (avoid currency errors)
        # if not frappe.db.exists("Price List", "Test Selling"):
        #     frappe.get_doc({
        #         "doctype": "Price List",
        #         "price_list_name": "Test Selling",
        #         "selling": 1,
        #         "currency": "INR"
        #     }).insert()

        # # Create territory
        # create_territory("_Test Territory")

        # # Create customer
        # if not frappe.db.exists("Customer", "Test Customer"):
        #     self.customer = frappe.get_doc({
        #         "doctype": "Customer",
        #         "customer_name": "Test Customer",
        #         "customer_group": "Commercial",
        #         "territory": "_Test Territory"
        #     }).insert()
        # else:
        #     self.customer = frappe.get_doc("Customer", "Test Customer")


        # # Ensure currency exchange rate exists
        # if not frappe.db.exists("Currency Exchange", {"from_currency": "USD", "to_currency": "INR"}):
        #     frappe.get_doc({
        #         "doctype": "Currency Exchange",
        #         "from_currency": "USD",
        #         "to_currency": "INR",
        #         "exchange_rate": 83.0,
        #         "date": nowdate()
        #     }).insert()

        # self.filters = {
        #     "based_on": "Sales Invoice",
        #     "from_date": add_days(nowdate(), -15),
        #     "to_date": nowdate()
        # }


        # # Create two sales orders with different PO numbers
        # self.so1 = frappe.get_doc({
        #     "doctype": "Sales Order",
        #     "company": self.company,
        #     "customer": self.customer.name,
        #     "selling_price_list": "Test Selling",
        #     "transaction_date": add_days(nowdate(), -10),
        #     "delivery_date": add_days(nowdate(), -5),  # simulate delayed delivery
        #     "set_warehouse": self.warehouse,
        #     "currency": "INR", 
        #     "items": [{
        #         "item_code": self.item_code,
        #         "qty": 1,
        #         "rate": 100,
        #         "batch_no": "TEST-BATCH-001",
        #     }],
        #     "po_no": "PO-001"
        # }).insert()
        # self.so1.submit()

        # self.so2 = frappe.get_doc({
        #     "doctype": "Sales Order",
        #     "company": self.company,
        #     "customer": self.customer.name,
        #     "selling_price_list": "Test Selling",
        #     "transaction_date": add_days(nowdate(), -10),
        #     "delivery_date": add_days(nowdate(), -5),
        #     "set_warehouse": self.warehouse,
        #     "currency": "INR", 
        #     "items": [{
        #         "item_code": self.item_code,
        #         "qty": 1,
        #         "rate": 200,
        #         "batch_no": "TEST-BATCH-002",
        #     }],
        #     "po_no": "PO-002"
        # }).insert()
        # self.so2.submit()


        # stock_entry = frappe.get_doc({
        #     "doctype": "Stock Entry",
        #     "stock_entry_type": "Material Receipt",
        #     "company": self.company,
        #     "to_warehouse": self.warehouse,
        #     "items": [{
        #         "item_code": self.item_code,
        #         "qty": 2,
        #         "rate": 100,
        #         "t_warehouse": self.warehouse,
        #         "batch_no": self.batch.name
        #     }]
        # })
        # stock_entry.insert()
        # stock_entry.submit()

        # from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice

        # # Create Sales Invoice for so1
        # self.si1 = make_sales_invoice(self.so1.name)
        # self.si1.posting_date = nowdate()
        # self.si1.currency = "INR"
        # self.si1.update_stock = 1
        # self.si1.set_posting_time = 1
        # for item in self.si1.items:
        #     item.batch_no = self.batch.name
        # self.si1.insert()
        # self.si1.submit()

        # # Create Sales Invoice for so2
        # self.si2 = make_sales_invoice(self.so2.name)
        # self.si2.posting_date = nowdate()
        # self.si2.currency = "INR"
        # self.si2.update_stock = 1
        # self.si2.set_posting_time = 1
        # for item in self.si2.items:
        #     item.batch_no = self.batch.name
        # self.si2.insert()
        # self.si2.submit()
        # # frappe.db.commit()


        # sales_invoice_list = frappe.db.get_list('Sales Invoice', {'posting_date': nowdate(), "company": self.company}, ['name'])
        # print("sales_invoice_list",sales_invoice_list)


    # def test_execute_reports_difference(self):
    #     columns, data = execute({
    #         "item_code": self.item_code,
    #         # "warehouse": self.warehouse,
    #         # "company": self.company
    #     })
    #     print("data",data)

    #     # There should be at least one row with non-zero difference
    #     difference_index = [col["fieldname"] for col in columns].index("differnce")

    #     has_difference = any(
    #         row.get("differnce") and abs(row.get("differnce", 0)) > 0.5
    #         for row in data if isinstance(row, dict)
    #     )

    #     self.assertTrue(has_difference, "Expected at least one row with balance mismatch > 0.5")


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