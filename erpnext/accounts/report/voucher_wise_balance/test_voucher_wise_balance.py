import frappe
from frappe.tests.utils import FrappeTestCase
from erpnext.accounts.test.accounts_mixin import AccountsTestMixin
from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice
from erpnext.accounts.doctype.payment_entry.test_payment_entry import get_payment_entry
from erpnext.accounts.report.voucher_wise_balance.voucher_wise_balance import execute

class TestVoucherWiseBalance(AccountsTestMixin, FrappeTestCase):
    def setUp(self):
        self.company = "_Test Company"
        self.customer = "_Test Customer"
        self.account = "Debtors - TC"

        # Create test Sales Invoice
        self.invoice = create_sales_invoice(
            do_not_save=False,
            customer=self.customer,
            posting_date="2025-01-05",
            company=self.company,
            item_list=[{"item_code": "_Test Item", "qty": 1, "rate": 1000.00}]
        )

        # Create and submit Payment Entry
        self.payment_entry = get_payment_entry(
            self.invoice.doctype, self.invoice.name
        )
        self.payment_entry.posting_date = "2025-01-07"
        self.payment_entry.paid_amount = 1180.00
        self.payment_entry.received_amount = 1180.00
        self.payment_entry.save()
        self.payment_entry.submit()

    def test_voucher_wise_balance_basic(self):
        filters = frappe._dict({
            "company": self.company,
            "from_date": "2025-01-01",
            "to_date": "2025-12-31"
        })

        _, data = execute(filters)

        self.assertTrue(data, "No data returned from voucher wise balance report")


@frappe.whitelist()
def call_method():
    obj_1 = TestVoucherWiseBalance()
    obj_1.setUp()
    obj_1.test_voucher_wise_balance_basic()
