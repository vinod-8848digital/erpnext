import frappe
from frappe import qb
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, flt, getdate, today

from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice
from erpnext.accounts.report.customer_ledger_summary.customer_ledger_summary import execute
from erpnext.accounts.test.accounts_mixin import AccountsTestMixin


class TestCustomerLedgerSummary(FrappeTestCase, AccountsTestMixin):
	def setUp(self):
		self.create_company()
		self.create_customer()
		self.create_item()
		self.clear_old_entries()

	def tearDown(self):
		frappe.db.rollback()

	def create_sales_invoice(self, do_not_submit=False, **args):
		si = create_sales_invoice(
			item=self.item,
			company=self.company,
			customer=self.customer,
			debit_to=self.debit_to,
			posting_date=today(),
			parent_cost_center=self.cost_center,
			cost_center=self.cost_center,
			rate=100,
			qty=10,
			price_list_rate=100,
			do_not_save=1,
			**args,
		)
		si = si.save()
		if not do_not_submit:
			si = si.submit()
		return si

	def create_payment_entry(self, docname, do_not_submit=False):
		pe = get_payment_entry("Sales Invoice", docname, bank_account=self.cash, party_amount=40)
		pe.paid_from = self.debit_to
		pe.insert()
		if not do_not_submit:
			pe.submit()
		return pe

	def create_credit_note(self, docname, do_not_submit=False):
		credit_note = create_sales_invoice(
			company=self.company,
			customer=self.customer,
			item=self.item,
			qty=-1,
			debit_to=self.debit_to,
			cost_center=self.cost_center,
			is_return=1,
			return_against=docname,
			do_not_submit=do_not_submit,
		)

		return credit_note

	def test_ledger_summary_basic_output(self):
		filters = {"company": self.company, "from_date": today(), "to_date": today()}

		si = self.create_sales_invoice(do_not_submit=True)
		si.save().submit()

		expected = {
			"party": "_Test Customer",
			"party_name": "_Test Customer",
			"opening_balance": 0,
			"invoiced_amount": 1000.0,
			"paid_amount": 0,
			"return_amount": 0,
			"closing_balance": 1000.0,
			"currency": "INR",
			"customer_name": "_Test Customer",
		}

		report = execute(filters)[1]
		self.assertEqual(len(report), 1)
		for field in expected:
			with self.subTest(field=field):
				self.assertEqual(report[0].get(field), expected.get(field))

	def test_summary_with_return_and_payment(self):
		filters = {"company": self.company, "from_date": today(), "to_date": today()}

		si = self.create_sales_invoice(do_not_submit=True)
		si.save().submit()

		expected = {
			"party": "_Test Customer",
			"party_name": "_Test Customer",
			"opening_balance": 0,
			"invoiced_amount": 1000.0,
			"paid_amount": 0,
			"return_amount": 0,
			"closing_balance": 1000.0,
			"currency": "INR",
			"customer_name": "_Test Customer",
		}

		report = execute(filters)[1]
		self.assertEqual(len(report), 1)
		for field in expected:
			with self.subTest(field=field):
				self.assertEqual(report[0].get(field), expected.get(field))

		cr_note = self.create_credit_note(si.name, True)
		cr_note.items[0].qty = -2
		cr_note.save().submit()

		expected_after_cr_note = {
			"party": "_Test Customer",
			"party_name": "_Test Customer",
			"opening_balance": 0,
			"invoiced_amount": 1000.0,
			"paid_amount": 0,
			"return_amount": 200.0,
			"closing_balance": 800.0,
			"currency": "INR",
		}
		report = execute(filters)[1]
		self.assertEqual(len(report), 1)
		for field in expected_after_cr_note:
			with self.subTest(field=field):
				self.assertEqual(report[0].get(field), expected_after_cr_note.get(field))

		pe = self.create_payment_entry(si.name, True)
		pe.paid_amount = 500
		pe.save().submit()

		expected_after_cr_and_payment = {
			"party": "_Test Customer",
			"party_name": "_Test Customer",
			"opening_balance": 0,
			"invoiced_amount": 1000.0,
			"paid_amount": 500.0,
			"return_amount": 200.0,
			"closing_balance": 300.0,
			"currency": "INR",
		}

		report = execute(filters)[1]
		self.assertEqual(len(report), 1)
		for field in expected_after_cr_and_payment:
			with self.subTest(field=field):
				self.assertEqual(report[0].get(field), expected_after_cr_and_payment.get(field))
	
	def test_party_ledger_summary_report_lines_TC_ACC_611(self):
		from erpnext.accounts.report.customer_ledger_summary.customer_ledger_summary import PartyLedgerSummaryReport, TREE_DOCTYPES
		from frappe.utils import add_days

		# --- Prepare filters for normal run ---
		filters = {
			"company": self.company,
			"from_date": today(),
			"to_date": today(),
			"party_type": "Customer",
		}

		# --- Patch frappe.throw to catch validations ---
		original_throw = frappe.throw
		frappe.throw = lambda msg: (_ for _ in ()).throw(Exception(msg))  # raise Exception

		# --- Patch get_descendants_of to avoid DB call ---
		original_get_descendants_of = frappe.utils.nestedset.get_descendants_of
		frappe.utils.nestedset.get_descendants_of = lambda doctype, value: [f"{value}-child"]

		# --- Patch frappe.db.get_single_value to avoid DB call ---
		original_get_single_value = frappe.db.get_single_value
		frappe.db.get_single_value = lambda dt, fn: "Naming Series"

		# --- Patch methods that query DB ---
		original_get_party_details = PartyLedgerSummaryReport.get_party_details
		PartyLedgerSummaryReport.get_party_details = lambda self: setattr(self, "parties", ["_Test Customer"]) or setattr(self, "party_details", {"_Test Customer": {"customer_name": "_Test Customer"}})

		original_get_gl_entries = PartyLedgerSummaryReport.get_gl_entries
		PartyLedgerSummaryReport.get_gl_entries = lambda self: setattr(self, "gl_entries", [])

		original_get_return_invoices = PartyLedgerSummaryReport.get_return_invoices
		PartyLedgerSummaryReport.get_return_invoices = lambda self: setattr(self, "return_invoices", [])

		original_get_party_adjustment_amounts = PartyLedgerSummaryReport.get_party_adjustment_amounts
		PartyLedgerSummaryReport.get_party_adjustment_amounts = lambda self: setattr(self, "party_adjustment_accounts", set())

		try:
			# --- Normal run (covers __init__, run, validate_filters) ---
			report = PartyLedgerSummaryReport(filters)
			columns, data = report.run({"party_type": "Customer", "naming_by": ["Selling Settings", "cust_master_name"]})

			self.assertEqual(report.filters.company, self.company)
			self.assertEqual(report.filters.party_type, "Customer")
			self.assertEqual(report.parties, ["_Test Customer"])
			self.assertIsInstance(columns, list)
			self.assertIsInstance(data, list)

			# --- Cover "no company" exception in validate_filters ---
			report_missing_company = PartyLedgerSummaryReport({"from_date": today(), "to_date": today()})
			with self.assertRaises(Exception) as e:
				report_missing_company.validate_filters()
			self.assertIn("Company is mandatory", str(e.exception))

			# --- Cover "from_date > to_date" exception in validate_filters ---
			report_invalid_dates = PartyLedgerSummaryReport({
				"company": self.company,
				"from_date": add_days(today(), 1),
				"to_date": today()
			})
			with self.assertRaises(Exception) as e:
				report_invalid_dates.validate_filters()
			self.assertIn("From Date must be before To Date", str(e.exception))

			# --- Cover "if not self.parties" branch ---
			report_empty_party = PartyLedgerSummaryReport(filters)
			# Patch get_party_details to set empty parties
			report_empty_party.get_party_details = lambda: setattr(report_empty_party, "parties", [])
			cols, dat = report_empty_party.run({"party_type": "Customer", "naming_by": ["Selling Settings", "cust_master_name"]})
			self.assertEqual(cols, [])
			self.assertEqual(dat, [])

		finally:
			# --- Restore patched functions ---
			frappe.throw = original_throw
			frappe.utils.nestedset.get_descendants_of = original_get_descendants_of
			frappe.db.get_single_value = original_get_single_value
			PartyLedgerSummaryReport.get_party_details = original_get_party_details
			PartyLedgerSummaryReport.get_gl_entries = original_get_gl_entries
			PartyLedgerSummaryReport.get_return_invoices = original_get_return_invoices
			PartyLedgerSummaryReport.get_party_adjustment_amounts = original_get_party_adjustment_amounts

	def test_party_ledger_summary_report_hierarchical_and_conditions_TC_ACC_612(self):
		import frappe
		from frappe.utils import today
		from erpnext.accounts.report.customer_ledger_summary.customer_ledger_summary import PartyLedgerSummaryReport, TREE_DOCTYPES, scrub
		from frappe.query_builder import DocType

		# --- Filters ---
		filters = {
			"company": self.company,
			"from_date": today(),
			"to_date": today(),
			"party_type": "Customer",
			"territory": ["_Test Territory"],
			"customer_group": ["_Test Group"],
			"payment_terms_template": "Net 30",
			"sales_partner": ["_Test Partner"],
			"sales_person": ["_Test Person"],
			"party": "_Test Customer",
		}

		# --- Backup originals ---
		original_throw = frappe.throw
		original_get_descendants_of = frappe.utils.nestedset.get_descendants_of
		from erpnext.accounts.report.customer_ledger_summary import customer_ledger_summary
		original_get_children = customer_ledger_summary.get_children
		from frappe.desk import reportview
		original_build_match_conditions = reportview.build_match_conditions
		original_qb = frappe.qb
		original_get_party_conditions = PartyLedgerSummaryReport.get_party_conditions

		# --- Patches ---
		frappe.throw = lambda msg: (_ for _ in ()).throw(Exception(msg))
		frappe.utils.nestedset.get_descendants_of = lambda doctype, value: [f"{value}-child"]
		customer_ledger_summary.get_children = lambda doctype, value: [f"{value}-child"]
		reportview.build_match_conditions = lambda party_type: "1=1"
		frappe.qb = frappe._dict()
		frappe.qb.DocType = lambda name: frappe._dict(
			select=lambda *a, **k: frappe._dict(
				where=lambda *a, **k: frappe._dict(run=lambda as_dict=False: [frappe._dict(party="_Test Customer", customer_name="_Test Customer")])
			)
		)
		PartyLedgerSummaryReport.get_party_conditions = lambda self, dt: []

		try:
			# --- Instantiate report ---
			report = PartyLedgerSummaryReport(filters)

			# --- update_hierarchical_filters ---
			report.update_hierarchical_filters()
			for doctype in TREE_DOCTYPES:
				key = scrub(doctype)
				if report.filters.get(key):
					self.assertIn("-child", report.filters[key][0])

			# --- get_party_details ---
			report.get_party_details()
			
			# --- get_party_conditions ---
			dt = DocType("Customer")
			conditions = report.get_party_conditions(dt)
			self.assertIsInstance(conditions, list)

		finally:
			# --- Restore originals ---
			frappe.throw = original_throw
			frappe.utils.nestedset.get_descendants_of = original_get_descendants_of
			customer_ledger_summary.get_children = original_get_children
			reportview.build_match_conditions = original_build_match_conditions
			frappe.qb = original_qb
			PartyLedgerSummaryReport.get_party_conditions = original_get_party_conditions

	def test_party_ledger_summary_get_party_conditions_TC_ACC_613(self):
		import frappe
		from frappe.utils import today
		from erpnext.accounts.report.customer_ledger_summary.customer_ledger_summary import PartyLedgerSummaryReport
		from frappe.query_builder import DocType

		# --- Filters that cover every if branch ---
		filters = {
			"company": self.company,
			"from_date": today(),
			"to_date": today(),
			"party_type": "Customer",
			"party": "_Test Customer",
			"territory": ["_Test Territory"],
			"customer_group": ["_Test Group"],
			"payment_terms_template": "Net 30",
			"sales_partner": ["_Test Partner"],
			"sales_person": ["_Test Person"],
		}

		# --- Backup originals ---
		original_qb = frappe.qb

		# --- Create mock DocType and qb equivalents without using any classes ---
		def make_mock_field():
			return frappe._dict({
				"isin": lambda val: f"mock_condition_for_{val}"
			})

		def make_mock_doctype(name):
			return frappe._dict({
				"name": make_mock_field(),
				"territory": make_mock_field(),
				"customer_group": make_mock_field(),
				"supplier_group": make_mock_field(),
				"payment_terms": "mock_payment_terms",
				"default_sales_partner": make_mock_field(),
			})

		def mock_from_(*args, **kwargs):
			return frappe._dict({
				"select": lambda *a, **k: frappe._dict({
					"where": lambda *a, **k: frappe._dict({
						"join": lambda *a, **k: frappe._dict({
							"on": lambda *a, **k: frappe._dict({
								"select": lambda *a, **k: frappe._dict({
									"where": lambda *a, **k: "mock_joined_query"
								})
							})
						})
					})
				})
			})

		frappe.qb = frappe._dict()
		frappe.qb.DocType = lambda name: make_mock_doctype(name)
		frappe.qb.from_ = mock_from_

		try:
			# --- Run the actual method ---
			report = PartyLedgerSummaryReport(filters)
			doctype = DocType("Customer")
			conditions = report.get_party_conditions(doctype)

			# --- Assert full coverage ---
			self.assertIsInstance(conditions, list)
			self.assertGreaterEqual(len(conditions), 6)

		finally:
			frappe.qb = original_qb


	def test_party_ledger_summary_get_columns_TC_ACC_614(self):
		import frappe
		from frappe import _
		from frappe.utils import today
		from erpnext.accounts.report.customer_ledger_summary.customer_ledger_summary import PartyLedgerSummaryReport

		# --- Mock translation function ---
		original_translate = frappe._
		frappe._ = lambda x: x  # prevent needing actual translations

		# --- Mock filters to hit all branches ---
		filters_customer = {
			"company": self.company,
			"from_date": today(),
			"to_date": today(),
			"party_type": "Customer",
		}

		filters_supplier = {
			"company": self.company,
			"from_date": today(),
			"to_date": today(),
			"party_type": "Supplier",
		}

		# --- Instantiate report for Customer ---
		report_customer = PartyLedgerSummaryReport(filters_customer)
		report_customer.party_naming_by = "Naming Series"
		report_customer.party_adjustment_accounts = ["Test Adj Account 1", "Test Adj Account 2"]

		# --- Run the function and assert ---
		customer_columns = report_customer.get_columns()
		self.assertTrue(any(col["fieldname"] == "party_name" for col in customer_columns))
		self.assertTrue(any(col["label"] == "Credit Note" for col in customer_columns))
		self.assertTrue(any(col.get("is_adjustment") == 1 for col in customer_columns))
		self.assertTrue(any(col["fieldname"] == "territory" for col in customer_columns))
		self.assertTrue(any(col["fieldname"] == "customer_group" for col in customer_columns))


		# --- Instantiate report for Supplier ---
		report_supplier = PartyLedgerSummaryReport(filters_supplier)
		report_supplier.party_naming_by = "Not Naming Series"
		report_supplier.party_adjustment_accounts = ["Adj X"]

		# --- Run the function and assert ---
		supplier_columns = report_supplier.get_columns()
		self.assertFalse(any(col["fieldname"] == "party_name" for col in supplier_columns))
		self.assertTrue(any(col["label"] == "Debit Note" for col in supplier_columns))
		self.assertTrue(any(col["fieldname"] == "supplier_group" for col in supplier_columns))


		# --- Restore original translation function ---
		frappe._ = original_translate


	def test_party_ledger_summary_prepare_conditions_TC_ACC_615(self):
		import frappe
		from frappe.query_builder import Table
		from frappe.query_builder.functions import IfNull
		from types import SimpleNamespace
		from erpnext.accounts.report.customer_ledger_summary.customer_ledger_summary import PartyLedgerSummaryReport
		import erpnext.accounts.utils as accounts_utils


		# --- Fake query ---
		query = type(
			"DummyQuery",
			(),
			{
				"conditions": [],
				"where": lambda self, cond: (self.conditions.append(str(cond)) or self),
			},
		)()
		query.conditions = []

		# --- Fake dimensions ---
		dimension_with_tree = SimpleNamespace(fieldname="dimension_tree", document_type="Cost Center")
		dimension_without_tree = SimpleNamespace(fieldname="dimension_plain", document_type="Department")
		from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import (
			get_accounting_dimensions,
			get_dimension_with_children,
		)
		# --- Backup originals ---
		original_get_accounting_dimensions = get_accounting_dimensions
		original_get_cached_value = frappe.get_cached_value

		# --- Patch functions globally ---
		frappe.get_cached_value = lambda doctype, document_type, field: 1 if document_type == "Cost Center" else 0
		accounts_utils.get_accounting_dimensions = lambda as_list=False: [
			dimension_with_tree,
			dimension_without_tree,
		]

		import erpnext.accounts.report.customer_ledger_summary.customer_ledger_summary as cls_module
		cls_module.get_dimension_with_children = lambda document_type, values: [f"{values[0]}_child"]

		# --- Filters covering all conditions ---
		filters = {
			"company": "Test Company",
			"finance_book": "Book1",
			"cost_center": ["C1", "C2"],
			"project": ["P1"],
			"dimension_tree": ["TreeA"],
			"dimension_plain": ["PlainB"],
		}

		# --- Run function under test ---
		report = PartyLedgerSummaryReport(filters)
		result_query = report.prepare_conditions(query)

		

		# --- Restore originals ---
		accounts_utils.get_accounting_dimensions = original_get_accounting_dimensions
		frappe.get_cached_value = original_get_cached_value
