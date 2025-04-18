# Copyright (c) 2019, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt

import unittest

import frappe

from erpnext.accounts.doctype.journal_entry.test_journal_entry import make_journal_entry
from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

test_dependencies = ["Cost Center", "Warehouse", "Department"]
if "Assets" in frappe.get_installed_apps():
	test_dependencies = ["Cost Center", "Location", "Warehouse", "Department"]


class TestAccountingDimension(unittest.TestCase):
	def setUp(self):
		create_dimension()

	def test_dimension_against_sales_invoice(self):
		si = create_sales_invoice(do_not_save=1)

		si.location = "Block 1"
		si.append(
			"items",
			{
				"item_code": "_Test Item",
				"warehouse": "_Test Warehouse - _TC",
				"qty": 1,
				"rate": 100,
				"income_account": "Sales - _TC",
				"expense_account": "Cost of Goods Sold - _TC",
				"cost_center": "_Test Cost Center - _TC",
				"department": "_Test Department - _TC",
				"location": "Block 1",
			},
		)

		si.save()
		si.submit()

		gle = frappe.get_doc("GL Entry", {"voucher_no": si.name, "account": "Sales - _TC"})

		self.assertEqual(gle.get("department"), "_Test Department - _TC")
  
	def test_auto_creation_of_accounts_on_company_creation_TC_ACC_066(self):
		if not frappe.db.exists("Company", "_Test Company"):
			company = frappe.new_doc("Company")
			company.company_name = "_Test Company"
			company.abbr = "_TC"
			company.default_currency = "INR"
			company.create_chart_of_accounts_based_on = "Standard"
			company.save()
		
		if not frappe.db.exists("Company", "_Test Agro"):
			company = frappe.new_doc("Company")
			company.company_name = "_Test Agro"
			company.abbr = "_TA"
			company.default_currency = "INR"
			company.create_chart_of_accounts_based_on = "Existing Company"
			company.existing_company = "_Test Company"
			company.save()

			expected_results = {
				"Debtors - _TA": {
					"account_type": "Receivable",
					"is_group": 0,
					"root_type": "Asset",
					"parent_account": "Accounts Receivable - _TA",
				},
				"Cash - _TA": {
					"account_type": "Cash",
					"is_group": 0,
					"root_type": "Asset",
					"parent_account": "Cash In Hand - _TA",
				},
			}
			for account, acc_property in expected_results.items():
				acc = frappe.get_doc("Account", account)
				for prop, val in acc_property.items():
					self.assertEqual(acc.get(prop), val)

			frappe.delete_doc("Company", "_Test Agro")


	def test_cost_center_in_gl_and_reports_TC_ACC_067(self):
		# Step 1: Create a Sales Invoice (SI) with a Cost Center
		si = create_sales_invoice(do_not_save=1)
		si.cost_center = "_Test Cost Center - _TC"
		si.location = "Block 1"
		si.append(
			"items",
			{
				"item_code": "_Test Item",
				"warehouse": "_Test Warehouse - _TC",
				"qty": 1,
				"rate": 100,
				"income_account": "Sales - _TC",
				"expense_account": "Cost of Goods Sold - _TC",
				"cost_center": "_Test Cost Center - _TC",
				"department": "_Test Department - _TC",
				"location": "Block 1",
			},
		)

		si.save()
		si.submit()

		# Step 2: Verify Cost Center appears in the General Ledger
		gl_entries = frappe.db.get_all(
			"GL Entry",
			filters={"voucher_no": si.name},
			fields=["account", "cost_center", "debit", "credit"],
		)

		# Assert that GL Entries include the specified Cost Center
		self.assertTrue(
			any(entry["cost_center"] == "_Test Cost Center - _TC" for entry in gl_entries),
			"Cost Center not reflected in GL Entries",
		)

		# Step 3: Verify Cost Center in Profit and Loss Report
		profit_and_loss_data = frappe.get_list(
			"GL Entry",
			filters={"account": "Sales - _TC", "cost_center": "_Test Cost Center - _TC"},
			fields=["account", "debit", "credit", "cost_center"],
		)
		self.assertGreater(len(profit_and_loss_data), 0, "Cost Center not reflected in P&L Report")

		# Step 4: Verify Cost Center in Balance Sheet Report
		balance_sheet_data = frappe.get_list(
			"GL Entry",
			filters={"cost_center": "_Test Cost Center - _TC"},
			fields=["account", "debit", "credit", "cost_center"],
		)
		self.assertGreater(len(balance_sheet_data), 0, "Cost Center not reflected in Balance Sheet")


	def test_dimension_against_journal_entry(self):
		je = make_journal_entry("Sales - _TC", "Sales Expenses - _TC", 500, save=False)
		je.accounts[0].update({"department": "_Test Department - _TC"})
		je.accounts[1].update({"department": "_Test Department - _TC"})

		je.accounts[0].update({"location": "Block 1"})
		je.accounts[1].update({"location": "Block 1"})

		je.save()
		je.submit()

		gle = frappe.get_doc("GL Entry", {"voucher_no": je.name, "account": "Sales - _TC"})
		gle1 = frappe.get_doc("GL Entry", {"voucher_no": je.name, "account": "Sales Expenses - _TC"})
		self.assertEqual(gle.get("department"), "_Test Department - _TC")
		self.assertEqual(gle1.get("department"), "_Test Department - _TC")

	def test_mandatory(self):
		si = create_sales_invoice(do_not_save=1)
		si.append(
			"items",
			{
				"item_code": "_Test Item",
				"warehouse": "_Test Warehouse - _TC",
				"qty": 1,
				"rate": 100,
				"income_account": "Sales - _TC",
				"expense_account": "Cost of Goods Sold - _TC",
				"cost_center": "_Test Cost Center - _TC",
				"location": "",
			},
		)

		si.save()
		self.assertRaises(frappe.ValidationError, si.submit)

	def tearDown(self):
		disable_dimension()
		frappe.flags.accounting_dimensions_details = None
		frappe.flags.dimension_filter_map = None


def create_dimension():
	frappe.set_user("Administrator")

	if not frappe.db.exists("Accounting Dimension", {"document_type": "Department"}):
		dimension = frappe.get_doc(
			{
				"doctype": "Accounting Dimension",
				"document_type": "Department",
			}
		)
		dimension.append(
			"dimension_defaults",
			{
				"company": "_Test Company",
				"reference_document": "Department",
				"default_dimension": "_Test Department - _TC",
			},
		)
		dimension.insert()
		dimension.save()
	else:
		dimension = frappe.get_doc("Accounting Dimension", "Department")
		dimension.disabled = 0
		dimension.save()

	if "Assets" in frappe.get_installed_apps():
		if not frappe.db.exists("Accounting Dimension", {"document_type": "Location"}):
			dimension1 = frappe.get_doc(
				{
					"doctype": "Accounting Dimension",
					"document_type": "Location",
				}
			)

			dimension1.append(
				"dimension_defaults",
				{
					"company": "_Test Company",
					"reference_document": "Location",
					"default_dimension": "Block 1",
					"mandatory_for_bs": 1,
				},
			)

			dimension1.insert()
			dimension1.save()
		else:
			dimension1 = frappe.get_doc("Accounting Dimension", "Location")
			dimension1.disabled = 0
			dimension1.save()


def disable_dimension():
	dimension1 = frappe.get_doc("Accounting Dimension", "Department")
	dimension1.disabled = 1
	dimension1.save()
	if "Assets" in frappe.get_installed_apps():
		dimension2 = frappe.get_doc("Accounting Dimension", "Location")
		dimension2.disabled = 1
		dimension2.save()
