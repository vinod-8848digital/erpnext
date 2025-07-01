# Copyright (c) 2020, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt


import frappe
from frappe import qb
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, flt, now_datetime, today

from erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool import (
	auto_reconcile_vouchers,
	create_journal_entry_bts,
	create_payment_entry_bts,
	get_account_balance,
	get_bank_transactions,
	get_linked_payments,
	reconcile_vouchers,
	update_bank_transaction,
)
from erpnext.accounts.doctype.payment_entry.test_payment_entry import create_payment_entry
from erpnext.accounts.test.accounts_mixin import AccountsTestMixin


class TestBankReconciliationTool(AccountsTestMixin, FrappeTestCase):
	def setUp(self):
		self.create_company()
		self.create_customer()
		self.clear_old_entries()
		bank_dt = qb.DocType("Bank")
		qb.from_(bank_dt).delete().where(bank_dt.name == "HDFC").run()
		self.create_bank_account()
		# self.create_test_data()

		self.bank_account_doc = self.make_bank_account()
		self.bank_account = self.bank_account_doc.name

	def tearDown(self):
		frappe.db.rollback()

	def create_bank_account(self):
		bank = frappe.get_doc(
			{
				"doctype": "Bank",
				"bank_name": "HDFC",
			}
		).save()

		self.bank_account = (
			frappe.get_doc(
				{
					"doctype": "Bank Account",
					"account_name": "HDFC _current_",
					"bank": bank,
					"is_company_account": True,
					"account": self.bank,  # account from Chart of Accounts
				}
			)
			.insert()
			.name
		)

	def test_auto_reconcile(self):
		# make payment
		from_date = add_days(today(), -1)
		to_date = today()
		payment = create_payment_entry(
			company=self.company,
			posting_date=from_date,
			payment_type="Receive",
			party_type="Customer",
			party=self.customer,
			paid_from=self.debit_to,
			paid_to=self.bank,
			paid_amount=100,
		).save()
		payment.reference_no = "123"
		payment = payment.save().submit()

		# make bank transaction
		bank_transaction = (
			frappe.get_doc(
				{
					"doctype": "Bank Transaction",
					"date": to_date,
					"deposit": 100,
					"bank_account": self.bank_account,
					"reference_number": "123",
					"currency": "INR",
				}
			)
			.save()
			.submit()
		)

		# assert API output pre reconciliation
		transactions = get_bank_transactions(self.bank_account, from_date, to_date)
		self.assertEqual(len(transactions), 1)
		self.assertEqual(transactions[0].name, bank_transaction.name)

		# auto reconcile
		auto_reconcile_vouchers(
			bank_account=self.bank_account,
			from_date=from_date,
			to_date=to_date,
			filter_by_reference_date=False,
		)

		# assert API output post reconciliation
		transactions = get_bank_transactions(self.bank_account, from_date, to_date)
		self.assertEqual(len(transactions), 0)

	def make_bank_account(self):
		# Check if bank already exists
		bank_name = "HDFC"
		bank = frappe.db.get_value("Bank", {"bank_name": bank_name})
		if not bank:
			bank = frappe.get_doc({"doctype": "Bank", "bank_name": bank_name}).insert().name

		# Check if Bank Account already exists
		account_name = "HDFC _current_"
		existing = frappe.db.get_value("Bank Account", {"account_name": account_name, "bank": bank})
		if existing:
			return frappe.get_doc("Bank Account", existing)

		# Create new Bank Account
		return frappe.get_doc(
			{
				"doctype": "Bank Account",
				"account_name": account_name,
				"bank": bank,
				"is_company_account": True,
				"account": self.bank,  # from Chart of Accounts
			}
		).insert()

	def test_get_account_balance_TC_ACC_263(self):
		balance = get_account_balance(self.bank_account, today(), self.company)
		self.assertIsInstance(balance, float)

	def test_update_bank_transaction_TC_ACC_264(self):
		bt = (
			frappe.get_doc(
				{
					"doctype": "Bank Transaction",
					"date": today(),
					"deposit": 500,
					"bank_account": self.bank_account,
					"currency": "INR",
				}
			)
			.insert()
			.submit()
		)

		updated = update_bank_transaction(bt.name, "REF-001", "Customer", self.customer)
		self.assertEqual(updated["reference_number"], "REF-001")

	def test_create_journal_entry_bts_TC_ACC_265(self):
		bt = (
			frappe.get_doc(
				{
					"doctype": "Bank Transaction",
					"date": today(),
					"deposit": 1000,
					"bank_account": self.bank_account,
					"currency": "INR",
				}
			)
			.insert()
			.submit()
		)

		je = create_journal_entry_bts(
			bt.name,
			reference_number="CHQ123",
			posting_date=today(),
			reference_date=today(),
			entry_type="Journal Entry",
			second_account=self.debit_to,
			party_type="Customer",
			party=self.customer,
			allow_edit=True,
		)
		self.assertEqual(je.voucher_type, "Journal Entry")

	def test_create_payment_entry_bts_TC_ACC_266(self):
		bt = (
			frappe.get_doc(
				{
					"doctype": "Bank Transaction",
					"date": today(),
					"deposit": 500,
					"unallocated_amount": 500,
					"bank_account": self.bank_account,
					"currency": "INR",
				}
			)
			.insert()
			.submit()
		)

		pe = create_payment_entry_bts(
			bt.name,
			reference_number="PE001",
			reference_date=today(),
			party_type="Customer",
			party=self.customer,
			posting_date=today(),
			mode_of_payment="Cash",
			allow_edit=True,
		)
		self.assertEqual(pe.payment_type, "Receive")

	def test_get_linked_payments_TC_ACC_267(self):
		bt = (
			frappe.get_doc(
				{
					"doctype": "Bank Transaction",
					"date": today(),
					"deposit": 200,
					"unallocated_amount": 200,
					"bank_account": self.bank_account,
					"currency": "INR",
				}
			)
			.insert()
			.submit()
		)

		pe = create_payment_entry(
			company=self.company,
			posting_date=today(),
			payment_type="Receive",
			party_type="Customer",
			party=self.customer,
			paid_from=self.debit_to,
			paid_to=self.bank,
			paid_amount=200,
			reference_no="LINK123",
		)
		pe.insert()
		pe.submit()

		bt.reference_number = "LINK123"
		bt.save()

		linked = get_linked_payments(
			bt.name, document_types=["payment_entry"], from_date=add_days(today(), -5), to_date=today()
		)
		self.assertTrue(len(linked) > 0)
