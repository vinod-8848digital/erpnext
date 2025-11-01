import frappe
from frappe.tests.utils import FrappeTestCase
from erpnext.accounts.doctype.purchase_invoice.test_purchase_invoice import make_purchase_invoice
from erpnext.accounts.report.tds_computation_summary.tds_computation_summary import execute
from erpnext.accounts.test.accounts_mixin import AccountsTestMixin
from datetime import datetime, timedelta
from erpnext.accounts.report.tax_withholding_details.test_tax_withholding_details import create_tax_category

class TestTDSComputationSummary(AccountsTestMixin, FrappeTestCase):

    def setUp(self):
        """Setup standard TDS and Supplier records for testing."""
        self.today = frappe.utils.nowdate()
        # Define necessary values once
        self.tds_rate_value = 10.0
        self.tds_account_head = "TCS - _TC"
        
        # 1. Create a Tax Withholding Category (TDS Section)
        create_tax_category(rate = 10)
        self.tds_category_name = "TCS"
        # 2. Create a Supplier
        self.supplier_name = "Test TDS Supplier"
        if not frappe.db.exists("Supplier", self.supplier_name):
            self.supplier = frappe.get_doc({
                "doctype": "Supplier",
                "supplier_name": self.supplier_name,
                "supplier_group": "Unclassified" # Assuming this group exists
            }).insert(ignore_permissions=True)
        else:
            self.supplier = frappe.get_doc("Supplier", self.supplier_name)


    def tearDown(self):
        """Cleanup logic (often handled by frappe.db.rollback in testing)."""
        pass

    def test_tds_computation_summary_report(self):
        """Test the report execution and data filtering."""
        
        # --- TEST SETUP: Create Purchase Invoice with TDS ---
        
        invoice_amount = 1000.0
        tds_rate = 10.0
        tds_amount = invoice_amount * (tds_rate / 100) # 100.0
        net_total = invoice_amount - tds_amount # 900.0
        pi = frappe.new_doc("Purchase Invoice")
        pi.update({
            "doctype": "Purchase Invoice",
            "supplier": self.supplier_name,
            "posting_date": self.today,
            "due_date": self.today,
            "company": "_Test Company",
            "set_warehouse": "_Test Warehouse Group - _TC", # Assuming default warehouse exists
            "items": [
                {
                    "item_code": "_Test Item", # Assuming a standard test item exists
                    "qty": 1,
                    "rate": invoice_amount,
                    "amount": invoice_amount
                }
            ],
            "taxes": [
                {
                    "charge_type": "Actual",
                    # FIX: Use the consistently defined account head string for robustness
                    "account_head": self.tds_account_head, 
                    "tax_withholding_category": self.tds_category_name,
                    "rate": tds_rate,
                    "tax_amount_for_currency": -tds_amount, # TDS is typically a deduction
                    "tax_amount": -tds_amount,
                    "add_deduct_tax": "Deduct",
                    "description": f"TDS @ {tds_rate}%",
                }
            ]
        })
        
        # Manually set totals and submit
        pi.grand_total = net_total
        pi.total_taxes_and_charges = -tds_amount
        pi.net_total = invoice_amount
        pi.paid_amount = 0
        pi.base_grand_total = net_total # For simplicity, assuming base currency equals transaction currency
        
        try:
            pi.insert(ignore_permissions=True)
            pi.submit()
            
        except Exception as e:
            frappe.log_error(title="PI Insertion Error", message=e)
            self.fail(f"Could not submit Purchase Invoice: {e}")
            return
            
        # --- TEST EXECUTION: Run Report ---

        # Define filters to capture the created invoice
        filters = frappe._dict({
            "from_date": self.today,
            "to_date": self.today,
            "party": self.supplier_name,
            "tds_section": self.tds_category_name,
            "party_type": "Supplier",
            "company": pi.company
        })

        # Execute the report function
        columns, data = execute(filters)

        # --- TEST ASSERTIONS ---

        # 1. Check if one row of data is returned
        self.assertEqual(len(data), 1, "The report should return exactly one row for the submitted Purchase Invoice.")

        row = data[0]

        # 2. Assert key fields
        self.assertEqual(row.get("party"), self.supplier_name)
        self.assertEqual(row.get("section_code"), self.tds_category_name)
        
        # 3. Assert monetary values (use self.assertAlmostEqual for float comparison)
        # Note: The taxable_amount is the amount *before* the TDS deduction is applied on the tax line.
        self.assertAlmostEqual(row.get("total_amount"), invoice_amount) 
        self.assertAlmostEqual(row.get("rate"), tds_rate)
        
        # The tds_amount is stored as a negative value in taxes, but the report should show the absolute value
        self.assertAlmostEqual(abs(row.get("tax_amount")), tds_amount) 
        
        # --- TEST EXECUTION: Test Date Filtering ---
        
        # Use a date range that excludes the PI
        excluded_filters = frappe._dict({
            "from_date": (datetime.strptime(self.today, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d"),
            "to_date": (datetime.strptime(self.today, "%Y-%m-%d") + timedelta(days=2)).strftime("%Y-%m-%d"),
            "party_type": "Supplier",
            "company": pi.company
        })
        
        columns_excluded, data_excluded = execute(excluded_filters)
        self.assertEqual(len(data_excluded), 0, "Report should return zero rows when the date filter excludes the document.")


@frappe.whitelist()
def run_tests():
    obj_1 = TestTDSComputationSummary()
    obj_1.setUp()
    obj_1.test_tds_computation_summary_report()
    return "TDS Computation Summary tests executed successfully."
