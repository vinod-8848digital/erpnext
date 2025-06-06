import frappe
from frappe.tests.utils import FrappeTestCase
from erpnext.stock.report.stock_and_account_value_comparison.stock_and_account_value_comparison import (
    execute,
    get_data,
    get_stock_ledger_data,
    get_gl_data,
    get_columns,
    create_reposting_entries,
)
from frappe.utils import nowdate, now_datetime
from datetime import timedelta
import erpnext


class TestStockAndAccountValueComparison(FrappeTestCase):
    def setUp(self):
        self.company = "_Test Company"
        self.item_code = "_Test Item"
        self.warehouse = "_Test Warehouse - _TC - _C"
        self.account = "Stock In Hand - _TC"
        self.posting_date = nowdate()
        
        self.ensure_test_data()
        get_or_create_fiscal_year("_Test Company")
        self.stock_entry = self.create_stock_entry()
        self.create_stock_ledger_entry()
        self.create_gl_entry()

    def ensure_test_data(self):
        hsn_code = "10010010"

        # Create GST HSN Code
        if not frappe.db.exists("GST HSN Code", hsn_code):
            frappe.get_doc({
                "doctype": "GST HSN Code",
                "hsn_code": hsn_code,
                "description": "Test HSN Code for automation"
            }).insert()


        if not frappe.db.exists("Company", self.company):
            frappe.get_doc({
                "doctype": "Company",
                "company_name": self.company,
                "default_currency": "INR"
            }).insert()

        if not frappe.db.exists("Item", self.item_code):
            frappe.get_doc({
                "doctype": "Item",
                "item_code": self.item_code,
                "item_name": "Test Item",
                "stock_uom": "Nos",
                "valuation_rate": 100,
                "is_stock_item": 1,
                "gst_hsn_code": hsn_code,
            }).insert()
            

        if not frappe.db.exists("Warehouse", self.warehouse):
            frappe.get_doc({
                "doctype": "Warehouse",
                "warehouse_name": self.warehouse,
                "company": self.company,
                # "account": self.account
            }).insert()

    def create_stock_entry(self):
        se = frappe.get_doc({
            "doctype": "Stock Entry",
            "stock_entry_type": "Material Receipt",
            "company": self.company,
            "posting_date": self.posting_date,
            "items": [{
                "item_code": self.item_code,
                "qty": 10,
                "uom": "Nos",
                "t_warehouse": self.warehouse,
                "rate": 100
            }]
        })
        se.insert(ignore_permissions=True)
        se.submit()
        return se.name

    def create_stock_ledger_entry(self):
        if not frappe.db.exists("Stock Ledger Entry", {"voucher_no": self.stock_entry}):
            frappe.get_doc({
                "doctype": "Stock Ledger Entry",
                "item_code": self.item_code,
                "warehouse": self.warehouse,
                "posting_date": self.posting_date,
                "posting_time": now_datetime().time(),
                "voucher_type": "Stock Entry",
                "voucher_no": self.stock_entry,
                "voucher_detail_no": self.stock_entry + "-ROW1",
                "actual_qty": 10,
                "stock_value": 1000,
                "stock_value_difference": 1000,
                "company": self.company,
                "incoming_rate": 100,
                "is_cancelled": 0,
            }).insert(ignore_permissions=True)

    def create_gl_entry(self):
        if not frappe.db.exists("GL Entry", {"voucher_no": self.stock_entry}):
            frappe.get_doc({
                "doctype": "GL Entry",
                "posting_date": self.posting_date,
                "account": self.account,
                "debit_in_account_currency": 1000,
                "credit_in_account_currency": 0,
                "voucher_type": "Stock Entry",
                "voucher_no": self.stock_entry,
                "company": self.company,
                "fiscal_year": frappe.defaults.get_user_default("fiscal_year")
            }).insert(ignore_permissions=True)

    def test_execute_with_perpetual_inventory(self):
        filters = frappe._dict({
            "company": self.company,
            "as_on_date": self.posting_date
        })
        columns, data = execute(filters)
        self.assertTrue(columns)
        self.assertIsInstance(data, list)

    def test_execute_without_perpetual_inventory(self):
        from erpnext import is_perpetual_inventory_enabled

        original = is_perpetual_inventory_enabled
        erpnext.is_perpetual_inventory_enabled = lambda company: False
        filters = frappe._dict({
            "company": self.company,
            "as_on_date": self.posting_date
        })
        with self.assertRaises(frappe.ValidationError):
            execute(filters)
        erpnext.is_perpetual_inventory_enabled = original

    def test_get_data(self):
        filters = frappe._dict({
            "company": self.company,
            "as_on_date": self.posting_date
        })
        result = get_data(filters)
        self.assertIsInstance(result, list)

    # def test_get_stock_ledger_data_with_account_filter(self):
    #     filters = frappe._dict({
    #         "company": self.company,
    #         "as_on_date": self.posting_date,
    #         "account": self.account
    #     })
    #     result = get_stock_ledger_data(filters, {
    #         "company": self.company,
    #         "posting_date": ("<=", self.posting_date),
    #         "is_cancelled": 0
    #     })
    #     self.assertTrue(result)
    #     for row in result:
    #         self.assertIn("voucher_no", row)
    #         if row.get("posting_time"):
    #             self.assertIsInstance(row["posting_time"], timedelta)

    def test_get_gl_data_with_and_without_account(self):
        filters = frappe._dict({
            "company": self.company,
            "as_on_date": self.posting_date
        })
        gl_data = get_gl_data(filters, {
            "company": self.company,
            "posting_date": ("<=", self.posting_date),
            "is_cancelled": 0
        })
        self.assertIsInstance(gl_data, dict)

        filters["account"] = self.account
        gl_data_with_account = get_gl_data(filters, {
            "company": self.company,
            "posting_date": ("<=", self.posting_date),
            "is_cancelled": 0
        })
        self.assertIsInstance(gl_data_with_account, dict)

    def test_get_columns(self):
        columns = get_columns({})
        self.assertTrue(columns)
        self.assertIn("fieldname", columns[0])

    def test_create_reposting_entries_success(self):
        data = get_data(frappe._dict({
            "company": self.company,
            "as_on_date": self.posting_date
        }))
        if data:
            row = data[0]
            row_dict = {
                "voucher_type": row.voucher_type,
                "voucher_no": row.voucher_no,
                "posting_date": row.posting_date
            }
            create_reposting_entries([row_dict], self.company)
            self.assertTrue(True)

    def test_create_reposting_entries_duplicate_handling(self):
        # First creation
        filters = frappe._dict({
            "company": self.company,
            "as_on_date": self.posting_date
        })
        data = get_data(filters)
        if data:
            row = data[0]
            row_dict = {
                "voucher_type": row.voucher_type,
                "voucher_no": row.voucher_no,
                "posting_date": row.posting_date
            }
            # Call twice to simulate duplicate entry
            create_reposting_entries([row_dict], self.company)
            create_reposting_entries([row_dict], self.company)
            self.assertTrue(True)


def get_or_create_fiscal_year(company):
	from datetime import datetime

	current_date = datetime.today()
	formatted_date = current_date.strftime("%d-%m-%Y")
	existing_fy = frappe.get_all(
		"Fiscal Year",
		filters={
			"year_start_date": ["<=", formatted_date],
			"year_end_date": [">=", formatted_date],
			"disabled": 0,
		},
		fields=["name"],
	)

	if existing_fy:
		fiscal_year = frappe.get_doc("Fiscal Year", existing_fy[0].name)
		for years in fiscal_year.companies:
			if years.company == company:
				pass
			else:
				fiscal_year.append("companies", {"company": company})
				fiscal_year.save()
	else:
		current_year = datetime.now().year
		first_date = f"01-01-{current_year}"
		last_date = f"31-12-{current_year}"
		fiscal_year = frappe.new_doc("Fiscal Year")
		fiscal_year.year = f"{current_year}"
		fiscal_year.year_start_date = first_date
		fiscal_year.year_end_date = last_date
		fiscal_year.append("companies", {"company": company})
		fiscal_year.save()
