import frappe
from frappe.tests.utils import FrappeTestCase
from .pos_register import execute
from erpnext.accounts.test.accounts_mixin import AccountsTestMixin
from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice
from erpnext.accounts.doctype.pos_profile.test_pos_profile import make_pos_profile
from erpnext.selling.doctype.customer.test_customer import get_customer_dict_new
from erpnext.accounts.doctype.account.test_account import create_account
from erpnext.accounts.doctype.payment_entry.test_payment_entry import get_or_create_fiscal_year
from erpnext.accounts.doctype.pos_profile.test_pos_profile import make_pos_profile
class TestPOSRegistry(FrappeTestCase, AccountsTestMixin):

    def setUp(self):
        self.create_company()
        self.company = "_Test Company"

        # Ensure fiscal year exists
        get_or_create_fiscal_year(self.company)

        # Create test customer
        self.customer = frappe.get_doc(get_customer_dict_new("_Test POS Customer")).insert()

        # Create test bank and income accounts if not exists
        create_account(
            account_name="Bank",
            parent_account="Bank Accounts - _TC",
            account_type="Bank",
            company=self.company,
            is_group=0,
        )

        create_account(
            account_name="Sales",
            parent_account="Income - _TC",
            account_type="Income Account",
            company=self.company,
            is_group=0,
        )

        # Create POS Profile
        self.pos_profile = make_pos_profile(
            company=self.company,
            name="_Test POS Profile",
            customer=self.customer.name,
            income_account="Sales - _TC",
            payments=[{"mode_of_payment": "Cash"}],
        )

    def tearDown(self):
        frappe.db.rollback()

    def test_pos_registry_report_TC_ACC_594(self):
        pos_profile = make_pos_profile()
        # Create and submit POS invoice
        self.invoice = create_sales_invoice(
            customer=self.customer.name,
            company=self.company,
            pos_profile=pos_profile.name,
            is_pos=1,
            do_not_submit=True,
        )

        self.invoice.cash_bank_account = "Bank - _TC"
        self.invoice.paid_amount = 1000
        self.invoice.set("payments", [{"mode_of_payment": "Cash", "amount": 1000}])
        self.invoice.submit()

        filters = frappe._dict({
            "company": self.company,
            'from_date' :'2025-01-01',
            'to_date' :'2025-10-08',
            'group_by' :'POS Profile'
        })
        columns, data = execute(filters)

        # Assertions
        self.assertTrue(len(data) > 0, "POS Registry should return at least one row")

        # Verify payments
        for row in data:
            self.assertEqual(row.get("mode_of_payment"), "Cash")

    def test_pos_registry_filters_conditions_TC_ACC_595(self):
        filters = frappe._dict({})
        columns, data = execute(filters)
        self.assertTrue(len(data) == 0, "POS Registry should return no rows when no filters are applied")


        filters = frappe._dict({
            "pos_profile" : "Non-Existent POS Profile",
        })
        with self.assertRaisesRegex(frappe.ValidationError, "Company is mandatory"):
            columns, data = execute(filters)
        
        filters = frappe._dict({
            "pos_profile" : "Non-Existent POS Profile",
            "company" : "_Test Company",
        })
        with self.assertRaisesRegex(frappe.ValidationError, "From Date and To Date are mandatory"):
            columns, data = execute(filters)
        
        return
