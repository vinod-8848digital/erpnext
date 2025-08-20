import frappe
from frappe import qb
from frappe.tests.utils import FrappeTestCase, change_settings
from frappe.utils import add_days, flt, getdate, today
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice
from erpnext.accounts.report.accounts_receivable.accounts_receivable import execute
from erpnext.accounts.test.accounts_mixin import AccountsTestMixin
from erpnext.selling.doctype.sales_order.test_sales_order import make_sales_order
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch

import erpnext.accounts.report.bank_reconciliation_report.bank_reconciliation_report as report

class TestBankReconciliationReport(FrappeTestCase):

    def setUp(self):
        self.filters = {
            "account": "Test Account",
            "from_date": "2024-01-01",
            "to_date": "2024-01-31"
        }

    @patch("bank_reconciliation_report.get_columns")
    @patch("bank_reconciliation_report.get_payment_entries")
    @patch("bank_reconciliation_report.get_journal_entries")
    @patch("bank_reconciliation_report.get_bank_transaction_entries")
    @patch("bank_reconciliation_report.get_static_rows")
    def test_execute(self, mock_static_rows, mock_bank, mock_journal, mock_payment, mock_columns):
        mock_columns.return_value = ["col1", "col2"]
        mock_payment.return_value = ["payment"]
        mock_journal.return_value = ["journal"]
        mock_bank.return_value = ["bank"]
        mock_static_rows.return_value = ["row1", "row2"]
        columns, data = report.execute(self.filters)
        self.assertEqual(columns, ["col1", "col2"])
        self.assertEqual(data, ["row1", "row2"])

    def test_get_columns(self):
        columns = report.get_columns()
        self.assertIsInstance(columns, list)
        self.assertTrue(any(col["fieldname"] == "details" for col in columns))

    @patch("bank_reconciliation_report.get_account_balance")
    @patch("bank_reconciliation_report.frappe")
    def test_get_static_rows(self, mock_frappe, mock_get_account_balance):
        mock_get_account_balance.return_value = {"total_debit": 100, "total_credit": 50, "balance": 50}
        mock_frappe.db.count.return_value = 0
        mock_frappe.get_all.return_value = [
            {"payment_document": "Payment Entry", "name": "PE-1", "paid_to": "Test Account", "paid_amount": 100, "posting_date": "2024-01-10", "reference_no": "REF-1"}
        ]
        bank_transactions = [
            {"deposit": 200, "withdrawal": 0, "posting_date": "2024-01-05", "payment_document": "Bank Transaction", "name": "BT-1", "reference_no": "BNK-REF-1"},
            {"deposit": 0, "withdrawal": 150, "posting_date": "2024-01-06", "payment_document": "Bank Transaction", "name": "BT-2", "reference_no": "BNK-REF-2"}
        ]
        payment_entries = [
            {"payment_entry": "PE-1", "credit": 100, "debit": 0, "payment_type": "Receive", "posting_date": "2024-01-10", "payment_document": "Payment Entry", "reference_no": "REF-1"},
            {"payment_entry": "PE-2", "credit": 0, "debit": 50, "payment_type": "Pay", "posting_date": "2024-01-11", "payment_document": "Payment Entry", "reference_no": "REF-2"}
        ]
        journal_entries = [
            {"payment_entry": "JE-1", "debit": 60, "credit": 0, "payment_document": "Journal Entry", "posting_date": "2024-01-12", "reference_no": "JREF-1"},
            {"payment_entry": "JE-2", "debit": 0, "credit": 40, "payment_document": "Journal Entry", "posting_date": "2024-01-13", "reference_no": "JREF-2"}
        ]
        rows = report.get_static_rows(bank_transactions, payment_entries, journal_entries, self.filters)
        self.assertIsInstance(rows, list)
        self.assertTrue(any("Balance as per ERPNext" in str(row.get("details")) for row in rows))
        self.assertTrue(any(row.get("debit") == "200" for row in rows))
        self.assertTrue(any(row.get("credit") == "150" for row in rows))

    def test_format_adjustment_data(self):
        entries = [
            {"posting_date": "2024-01-01", "payment_document": "Doc", "details": "Detail", "debit": 10, "credit": 5, "reference_no": "REF"}
        ]
        formatted = report.format_adjustment_data(entries, self.filters, "type")
        self.assertEqual(formatted[0]["details"], "Detail")
        self.assertEqual(formatted[0]["debit"], 10)

    @patch("bank_reconciliation_report.frappe")
    def test_get_payment_entries(self, mock_frappe):
        mock_frappe.db.sql.return_value = [
            {"payment_document": "Payment Entry", "payment_entry": "PE-1", "reference_no": "REF-1", "posting_date": "2024-01-10", "debit": 100, "credit": 100, "paid_from": "Test Account", "paid_to": "Other", "payment_type": "Receive", "details": "Other"}
        ]
        result = report.get_payment_entries(self.filters)
        self.assertIsInstance(result, list)
        self.assertEqual(result[0]["payment_entry"], "PE-1")

    @patch("bank_reconciliation_report.frappe")
    def test_get_journal_entries(self, mock_frappe):
        mock_frappe.db.sql.return_value = [
            {"payment_document": "Journal Entry", "posting_date": "2024-01-12", "payment_entry": "JE-1", "debit": 60, "credit": 0, "details": "Against", "account": "Test Account", "reference_no": "JREF-1", "ref_date": "2024-01-12", "account_type": "Bank"}
        ]
        result = report.get_journal_entries(self.filters)
        self.assertIsInstance(result, list)
        self.assertEqual(result[0]["payment_entry"], "JE-1")

    @patch("bank_reconciliation_report.frappe")
    def test_get_journal_entries_missing_account(self, mock_frappe):
        filters = {"from_date": "2024-01-01", "to_date": "2024-01-31"}
        with self.assertRaises(Exception):
            report.get_journal_entries(filters)

    @patch("bank_reconciliation_report.frappe")
    def test_get_journal_entries_missing_dates(self, mock_frappe):
        filters = {"account": "Test Account"}
        with self.assertRaises(Exception):
            report.get_journal_entries(filters)

    @patch("bank_reconciliation_report.frappe")
    def test_get_bank_transaction_entries(self, mock_frappe):
        mock_frappe.db.sql.return_value = [
            {"payment_document": "Bank Transaction", "name": "BT-1", "bank_account": "Test Account", "deposit": 200, "withdrawal": 0, "posting_date": "2024-01-05", "reference_no": "BNK-REF-1"}
        ]
        result = report.get_bank_transaction_entries(self.filters)
        self.assertIsInstance(result, list)
        self.assertEqual(result[0]["name"], "BT-1")

    @patch("bank_reconciliation_report.frappe")
    def test_get_bank_transaction_entries_missing_dates(self, mock_frappe):
        filters = {"account": "Test Account"}
        with self.assertRaises(Exception):
            report.get_bank_transaction_entries(filters)

    @patch("bank_reconciliation_report.frappe")
    def test_get_account_balance(self, mock_frappe):
        mock_frappe.db.sql.side_effect = [
            [{"total_debit": 100, "total_credit": 50}],
            [{"balance": 50}]
        ]
        result = report.get_account_balance("Test Account", "2024-01-01")
        self.assertEqual(result["total_debit"], 100)
        self.assertEqual(result["total_credit"], 50)
        self.assertEqual(result["balance"], 50)

    @patch("bank_reconciliation_report.frappe")
    def test_get_account_balance_empty(self, mock_frappe):
        mock_frappe.db.sql.side_effect = [
            [],
            []
        ]
        result = report.get_account_balance("Test Account", "2024-01-01")
        self.assertEqual(result["total_debit"], 0)
        self.assertEqual(result["total_credit"], 0)
        self.assertEqual(result["balance"], 0)
