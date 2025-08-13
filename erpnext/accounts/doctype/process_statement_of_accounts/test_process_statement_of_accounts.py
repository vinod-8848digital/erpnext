# Copyright (c) 2020, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt


import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, format_date, getdate, today

from erpnext.accounts.doctype.process_statement_of_accounts.process_statement_of_accounts import (
	get_context,
	get_report_pdf,
	get_statement_dict,
	send_emails,
)
from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice
from erpnext.accounts.test.accounts_mixin import AccountsTestMixin


class TestProcessStatementOfAccounts(AccountsTestMixin, FrappeTestCase):
	def setUp(self):
		self.create_company()
		self.create_customer()
		self.create_customer(customer_name="Other Customer")
		self.clear_old_entries()
		self.si = create_sales_invoice()
		create_sales_invoice(customer="Other Customer")

	def test_process_soa_for_gl(self):
		"""Tests the utils for Statement of Accounts(General Ledger)"""
		process_soa = create_process_soa(
			name="_Test Process SOA for GL",
			customers=[{"customer": "_Test Customer"}, {"customer": "Other Customer"}],
		)
		statement_dict = get_statement_dict(process_soa, get_statement_dict=True)

		# Checks if the statements are filtered based on the Customer
		self.assertIn("Other Customer", statement_dict)
		self.assertIn("_Test Customer", statement_dict)

		# Checks if the correct number of receivable entries exist
		# 3 rows for opening and closing and 1 row for SI
		receivable_entries = statement_dict["_Test Customer"][0]
		self.assertEqual(len(receivable_entries), 4)

		# Checks the amount for the receivable entry
		self.assertEqual(receivable_entries[1].voucher_no, self.si.name)
		self.assertEqual(receivable_entries[1].balance, 100)

	def test_process_soa_for_ar(self):
		"""Tests the utils for Statement of Accounts(Accounts Receivable)"""
		process_soa = create_process_soa(name="_Test Process SOA for AR", report="Accounts Receivable")
		statement_dict = get_statement_dict(process_soa, get_statement_dict=True)

		# Checks if the statements are filtered based on the Customer
		self.assertNotIn("Other Customer", statement_dict)
		self.assertIn("_Test Customer", statement_dict)

		# Checks if the correct number of receivable entries exist
		receivable_entries = statement_dict["_Test Customer"][0]
		self.assertEqual(len(receivable_entries), 1)

		# Checks the amount for the receivable entry
		self.assertEqual(receivable_entries[0].voucher_no, self.si.name)
		self.assertEqual(receivable_entries[0].total_due, 100)

		# Checks the ageing summary for AR
		ageing_summary = statement_dict["_Test Customer"][1][0]
		expected_summary = frappe._dict(
			range1=100,
			range2=0,
			range3=0,
			range4=0,
			range5=0,
		)
		self.check_ageing_summary(ageing_summary, expected_summary)

	def test_auto_email_for_process_soa_ar(self):
		process_soa = create_process_soa(
			name="_Test Process SOA", enable_auto_email=1, report="Accounts Receivable"
		)
		send_emails(process_soa.name, from_scheduler=True)
		process_soa.load_from_db()
		self.assertEqual(process_soa.posting_date, getdate(add_days(today(), 7)))

	def check_ageing_summary(self, ageing, expected_ageing):
		for age_range in expected_ageing:
			self.assertEqual(expected_ageing[age_range], ageing.get(age_range))

	def test_send_auto_email(self):
		from erpnext.accounts.doctype.process_statement_of_accounts.process_statement_of_accounts import (
			send_auto_email,
		)

		posa1 = create_process_soa(
			name="_Test POSA SEND 1",
			enable_auto_email=1,
			from_date=getdate(today()),
			to_date=getdate(today()),
		)

		posa2 = create_process_soa(
			name="_Test POSA SEND 2", enable_auto_email=1, posting_date=getdate(today())
		)

		posa3 = create_process_soa(
			name="_Test POSA SEND 3", enable_auto_email=1, to_date=add_days(getdate(today()), -1)
		)

		posa4 = create_process_soa(name="_Test POSA SEND 4", enable_auto_email=0, to_date=getdate(today()))

		result = send_auto_email()
		self.assertTrue(result)

		selected_names = {
			d.name
			for d in frappe.get_list(
				"Process Statement Of Accounts",
				filters={"enable_auto_email": 1},
				or_filters={"to_date": today(), "posting_date": today()},
				fields=["name"],
			)
		}

		self.assertIn(posa1.name, selected_names)
		self.assertIn(posa2.name, selected_names)
		self.assertIn(posa3.name, selected_names)
		self.assertNotIn(posa4.name, selected_names)

	def test_fetch_customers_sales_partner(self):
		from erpnext.accounts.doctype.process_statement_of_accounts.process_statement_of_accounts import (
			fetch_customers,
		)

		# Create a Sales Partner
		sales_partner = frappe.get_doc(
			{
				"doctype": "Sales Partner",
				"partner_name": "_Test Sales Partner Fetch",
				"commission_rate": "100",
			}
		).insert(ignore_permissions=True)

		# Create a Customer linked to that Sales Partner
		customer = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": "_Test Customer Fetch",
				"customer_type": "Company",
				"email_id": "customer@example.com",
				"default_sales_partner": sales_partner.name,
			}
		).insert(ignore_permissions=True)

		customers_list = fetch_customers(
			customer_collection="Sales Partner", collection_name=sales_partner.name, primary_mandatory=1
		)

		self.assertIsInstance(customers_list, list)
		self.assertTrue(any(cust["name"] == customer.name for cust in customers_list))
		self.assertEqual(customers_list[0]["primary_email"], "customer@example.com")

	def test_download_statements(self):
		from erpnext.accounts.doctype.process_statement_of_accounts.process_statement_of_accounts import (
			download_statements,
		)

		posa_01 = create_process_soa(
			name="_Test POSA 01",
		)

		doc = frappe.get_doc("Process Statement Of Accounts", posa_01.name)

		download_statements(doc.name)
		report = get_report_pdf(doc)

		self.assertEqual(frappe.local.response.filename, f"{doc.name}.pdf")
		self.assertEqual(frappe.local.response.type, "download")
		self.assertEqual(frappe.local.response.filecontent, report)

	def test_get_context(self):
		# Create test customer
		customer = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": "Test Customer for Context",
				"customer_group": "All Customer Groups",
				"territory": "All Territories",
			}
		).insert(ignore_permissions=True)

		# Create Process Statement of Accounts document with dates
		from_date = "2023-01-01"
		to_date = "2023-12-31"
		template_doc = frappe.get_doc(
			{
				"doctype": "Process Statement Of Accounts",
				"from_date": from_date,
				"to_date": to_date,
				"customers": [{"customer": customer.name}],
			}
		)

		context = get_context(customer.name, template_doc)

		self.assertIsInstance(context, dict)
		self.assertIn("doc", context)
		self.assertIn("customer", context)
		self.assertIn("frappe", context)

		self.assertNotEqual(id(context["doc"]), id(template_doc))

		self.assertFalse(hasattr(context["doc"], "customers"))

		self.assertEqual(context["doc"].from_date, format_date(from_date))
		self.assertEqual(context["doc"].to_date, format_date(to_date))

		self.assertEqual(context["customer"].name, customer.name)
		self.assertIsNotNone(context["frappe"])

		customer.delete(ignore_permissions=True)

	def tearDown(self):
		frappe.db.rollback()


def create_process_soa(**args):
	args = frappe._dict(args)
	frappe.delete_doc_if_exists("Process Statement Of Accounts", args.name)
	process_soa = frappe.new_doc("Process Statement Of Accounts")
	soa_dict = frappe._dict(
		name=args.name,
		company=args.company or "_Test Company",
		customers=args.customers or [{"customer": "_Test Customer"}],
		enable_auto_email=1 if args.enable_auto_email else 0,
		frequency=args.frequency or "Weekly",
		report=args.report or "General Ledger",
		from_date=args.from_date or getdate(today()),
		to_date=args.to_date or getdate(today()),
		posting_date=args.posting_date or getdate(today()),
		include_ageing=1,
	)
	process_soa.update(soa_dict)
	process_soa.save()
	return process_soa
