# Copyright (c) 2023, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt

import frappe
from frappe import qb
from frappe.query_builder.functions import Sum
from frappe.tests.utils import FrappeTestCase, change_settings
from frappe.utils import add_days, getdate, nowdate, today

from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
from erpnext.accounts.doctype.payment_request.payment_request import make_payment_request
from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice
from erpnext.accounts.test.accounts_mixin import AccountsTestMixin
from erpnext.accounts.utils import get_fiscal_year
from erpnext.stock.doctype.item.test_item import make_item
from erpnext.stock.doctype.purchase_receipt.test_purchase_receipt import get_gl_entries, make_purchase_receipt


class TestRepostAccountingLedger(AccountsTestMixin, FrappeTestCase):
	def setUp(self):
		self.create_company()
		self.create_customer()
		self.create_item()
		update_repost_settings()

	def tearDown(self):
		frappe.db.rollback()

	def test_01_basic_functions(self):
		si = create_sales_invoice(
			item=self.item,
			company=self.company,
			customer=self.customer,
			debit_to=self.debit_to,
			parent_cost_center=self.cost_center,
			cost_center=self.cost_center,
			rate=100,
		)

		preq = frappe.get_doc(
			make_payment_request(
				dt=si.doctype,
				dn=si.name,
				payment_request_type="Inward",
				party_type="Customer",
				party=si.customer,
			)
		)
		preq.save().submit()

		# Test Validation Error
		ral = frappe.new_doc("Repost Accounting Ledger")
		ral.company = self.company
		ral.delete_cancelled_entries = True
		ral.append("vouchers", {"voucher_type": si.doctype, "voucher_no": si.name})
		ral.append(
			"vouchers", {"voucher_type": preq.doctype, "voucher_no": preq.name}
		)  # this should throw validation error
		self.assertRaises(frappe.ValidationError, ral.save)
		ral.vouchers.pop()
		preq.cancel()
		preq.delete()

		pe = get_payment_entry(si.doctype, si.name)
		pe.save().submit()
		ral.append("vouchers", {"voucher_type": pe.doctype, "voucher_no": pe.name})
		ral.save()

		# manually set an incorrect debit amount in DB
		gle = frappe.db.get_all("GL Entry", filters={"voucher_no": si.name, "account": self.debit_to})
		frappe.db.set_value("GL Entry", gle[0], "debit", 90)

		gl = qb.DocType("GL Entry")
		res = (
			qb.from_(gl)
			.select(gl.voucher_no, Sum(gl.debit).as_("debit"), Sum(gl.credit).as_("credit"))
			.where((gl.voucher_no == si.name) & (gl.is_cancelled == 0))
			.groupby(gl.voucher_no)
			.run()
		)

		# Assert incorrect ledger balance
		self.assertNotEqual(res[0], (si.name, 100, 100))

		# Submit repost document
		ral.save().submit()

		res = (
			qb.from_(gl)
			.select(gl.voucher_no, Sum(gl.debit).as_("debit"), Sum(gl.credit).as_("credit"))
			.where((gl.voucher_no == si.name) & (gl.is_cancelled == 0))
			.groupby(gl.voucher_no)
			.run()
		)

		# Ledger should reflect correct amount post repost
		self.assertEqual(res[0], (si.name, 100, 100))

	def test_02_deferred_accounting_valiations(self):
		si = create_sales_invoice(
			item=self.item,
			company=self.company,
			customer=self.customer,
			debit_to=self.debit_to,
			parent_cost_center=self.cost_center,
			cost_center=self.cost_center,
			rate=100,
			do_not_submit=True,
		)
		si.items[0].enable_deferred_revenue = True
		si.items[0].deferred_revenue_account = self.deferred_revenue
		si.items[0].service_start_date = nowdate()
		si.items[0].service_end_date = add_days(nowdate(), 90)
		si.save().submit()

		ral = frappe.new_doc("Repost Accounting Ledger")
		ral.company = self.company
		ral.append("vouchers", {"voucher_type": si.doctype, "voucher_no": si.name})
		self.assertRaises(frappe.ValidationError, ral.save)

	@change_settings("Accounts Settings", {"delete_linked_ledger_entries": 1})
	def test_04_pcv_validation(self):
		# Clear old GL entries so PCV can be submitted.
		gl = frappe.qb.DocType("GL Entry")
		qb.from_(gl).delete().where(gl.company == self.company).run()

		si = create_sales_invoice(
			item=self.item,
			company=self.company,
			customer=self.customer,
			debit_to=self.debit_to,
			parent_cost_center=self.cost_center,
			cost_center=self.cost_center,
			rate=100,
		)
		fy = get_fiscal_year(today(), company=self.company)
		pcv = frappe.get_doc(
			{
				"doctype": "Period Closing Voucher",
				"transaction_date": today(),
				"posting_date": today(),
				"company": self.company,
				"period_start_date": frappe.utils.getdate(fy[1]),
				"period_end_date": frappe.utils.getdate(fy[2]),
				"fiscal_year": fy[0],
				"cost_center": self.cost_center,
				"closing_account_head": self.retained_earnings,
				"remarks": "test",
			}
		)
		pcv.save().submit()

		ral = frappe.new_doc("Repost Accounting Ledger")
		ral.company = self.company
		ral.append("vouchers", {"voucher_type": si.doctype, "voucher_no": si.name})
		self.assertRaises(frappe.ValidationError, ral.save)

		pcv.reload()
		pcv.cancel()
		pcv.delete()

	def test_03_deletion_flag_and_preview_function(self):
		si = create_sales_invoice(
			item=self.item,
			company=self.company,
			customer=self.customer,
			debit_to=self.debit_to,
			parent_cost_center=self.cost_center,
			cost_center=self.cost_center,
			rate=100,
		)

		pe = get_payment_entry(si.doctype, si.name)
		pe.save().submit()

		# with deletion flag set
		ral = frappe.new_doc("Repost Accounting Ledger")
		ral.company = self.company
		ral.delete_cancelled_entries = True
		ral.append("vouchers", {"voucher_type": si.doctype, "voucher_no": si.name})
		ral.append("vouchers", {"voucher_type": pe.doctype, "voucher_no": pe.name})
		ral.save().submit()

		self.assertIsNone(frappe.db.exists("GL Entry", {"voucher_no": si.name, "is_cancelled": 1}))
		self.assertIsNone(frappe.db.exists("GL Entry", {"voucher_no": pe.name, "is_cancelled": 1}))

	def test_05_without_deletion_flag(self):
		si = create_sales_invoice(
			item=self.item,
			company=self.company,
			customer=self.customer,
			debit_to=self.debit_to,
			parent_cost_center=self.cost_center,
			cost_center=self.cost_center,
			rate=100,
		)

		pe = get_payment_entry(si.doctype, si.name)
		pe.save().submit()

		# without deletion flag set
		ral = frappe.new_doc("Repost Accounting Ledger")
		ral.company = self.company
		ral.delete_cancelled_entries = False
		ral.append("vouchers", {"voucher_type": si.doctype, "voucher_no": si.name})
		ral.append("vouchers", {"voucher_type": pe.doctype, "voucher_no": pe.name})
		ral.save().submit()

		self.assertIsNotNone(frappe.db.exists("GL Entry", {"voucher_no": si.name, "is_cancelled": 1}))
		self.assertIsNotNone(frappe.db.exists("GL Entry", {"voucher_no": pe.name, "is_cancelled": 1}))

	def test_06_repost_purchase_receipt(self):
		from erpnext.accounts.doctype.account.test_account import create_account

		provisional_account = create_account(
			account_name="Provision Account",
			parent_account="Current Liabilities - _TC",
			company=self.company,
		)

		another_provisional_account = create_account(
			account_name="Another Provision Account",
			parent_account="Current Liabilities - _TC",
			company=self.company,
		)

		company = frappe.get_doc("Company", self.company)
		company.enable_provisional_accounting_for_non_stock_items = 1
		company.default_provisional_account = provisional_account
		company.save()

		test_cc = company.cost_center
		default_expense_account = company.default_expense_account

		item = make_item(properties={"is_stock_item": 0})

		pr = make_purchase_receipt(company=self.company, item_code=item.name, rate=1000.0, qty=1.0)
		pr_gl_entries = get_gl_entries(pr.doctype, pr.name, skip_cancelled=True)
		expected_pr_gles = [
			{"account": provisional_account, "debit": 0.0, "credit": 1000.0, "cost_center": test_cc},
			{"account": default_expense_account, "debit": 1000.0, "credit": 0.0, "cost_center": test_cc},
		]
		self.assertEqual(expected_pr_gles, pr_gl_entries)

		# change the provisional account
		frappe.db.set_value(
			"Purchase Receipt Item",
			pr.items[0].name,
			"provisional_expense_account",
			another_provisional_account,
		)

		repost_doc = frappe.new_doc("Repost Accounting Ledger")
		repost_doc.company = self.company
		repost_doc.delete_cancelled_entries = True
		repost_doc.append("vouchers", {"voucher_type": pr.doctype, "voucher_no": pr.name})
		repost_doc.save().submit()

		pr_gles_after_repost = get_gl_entries(pr.doctype, pr.name, skip_cancelled=True)
		expected_pr_gles_after_repost = [
			{"account": default_expense_account, "debit": 1000.0, "credit": 0.0, "cost_center": test_cc},
			{"account": another_provisional_account, "debit": 0.0, "credit": 1000.0, "cost_center": test_cc},
		]
		self.assertEqual(len(pr_gles_after_repost), len(expected_pr_gles_after_repost))
		self.assertEqual(expected_pr_gles_after_repost, pr_gles_after_repost)

		# teardown
		repost_doc.cancel()
		repost_doc.delete()

		pr.reload()
		pr.cancel()

		company.enable_provisional_accounting_for_non_stock_items = 0
		company.default_provisional_account = None
		company.save()

	def test_validate_for_closed_fiscal_year(self):
		frappe.set_user("Administrator")

		existing_fiscal_years = check_existing_fiscal_years(getdate("2023-04-01"), getdate("2024-03-31"))
		if not existing_fiscal_years:
			fy = frappe.get_doc(
				{
					"doctype": "Fiscal Year",
					"year": "2023-2024",
					"year_start_date": getdate("2023-04-01"),
					"year_end_date": getdate("2024-03-31"),
					"disabled": 0,
					"companies": [{"company": "_Test Company"}],
				}
			).insert(ignore_permissions=True)
		else:
			fy_name = existing_fiscal_years[0]
			fy = frappe.get_doc("Fiscal Year", fy_name)
			if not any(c.company == "_Test Company" for c in fy.companies):
				fy.append("companies", {"company": "_Test Company"})
				fy.disabled = 0
				fy.save(ignore_permissions=True)

		si = create_sales_invoice(
			item=self.item,
			company=self.company,
			customer=self.customer,
			debit_to=self.debit_to,
			parent_cost_center=self.cost_center,
			cost_center=self.cost_center,
			posting_date=getdate("2024-03-31"),
			rate=100,
		)
		si.submit()

		pe = get_payment_entry(si.doctype, si.name)
		pe.posting_date = getdate("2024-03-31")
		pe.save().submit()

		pcv = frappe.get_doc(
			{
				"doctype": "Period Closing Voucher",
				"company": self.company,
				"closing_account_head": "Creditors - " + self.company_abbr,
				"period_start_date": getdate("2023-04-01"),
				"period_end_date": getdate("2024-03-31"),
				"posting_date": getdate("2025-12-31"),
				"fiscal_year": fy.name,
				"remarks": "test",
			}
		).insert(ignore_permissions=True)
		pcv.submit()

		ral = frappe.new_doc("Repost Accounting Ledger")
		ral.company = self.company
		ral.delete_cancelled_entries = False
		ral.append("vouchers", {"voucher_type": si.doctype, "voucher_no": si.name})
		ral.append("vouchers", {"voucher_type": pe.doctype, "voucher_no": pe.name})
		ral.save(ignore_permissions=True)

		with self.assertRaises(frappe.ValidationError) as cm:
			ral.validate_for_closed_fiscal_year()

		self.assertEqual(
			str(cm.exception), "Cannot Resubmit Ledger entries for vouchers in Closed fiscal year."
		)

	def test_get_existing_ledger_entries_TC_ACC_371(self):
		si = create_sales_invoice(
			item=self.item,
			company=self.company,
			customer=self.customer,
			debit_to=self.debit_to,
			parent_cost_center=self.cost_center,
			cost_center=self.cost_center,
			rate=100,
		)
		si.submit()

		pe = get_payment_entry(si.doctype, si.name)
		pe.save().submit()

		ral = frappe.new_doc("Repost Accounting Ledger")
		ral.company = self.company
		ral.delete_cancelled_entries = False
		ral.append("vouchers", {"voucher_type": si.doctype, "voucher_no": si.name})
		ral.append("vouchers", {"voucher_type": pe.doctype, "voucher_no": pe.name})
		ral.save()
		ral.submit()

		ral.get_existing_ledger_entries()

		vouchers = [x.voucher_no for x in ral.vouchers]
		gl = qb.DocType("GL Entry")
		expected_gles = (
			qb.from_(gl)
			.select(gl.star)
			.where((gl.voucher_no.isin(vouchers)) & (gl.is_cancelled == 0))
			.run(as_dict=True)
		)

		for gle in expected_gles:
			key = (gle["voucher_type"], gle["voucher_no"])
			self.assertIn(key, ral.gles)
			existing_list = ral.gles[key]["existing"]

			found = any(x["name"] == gle["name"] and x["old"] for x in existing_list)
			self.assertTrue(found)

	def test_get_repost_allowed_types_TC_ACC_372(self):
		from erpnext.accounts.doctype.repost_accounting_ledger.repost_accounting_ledger import (
			get_repost_allowed_types,
		)

		if not frappe.db.exists(
			"Repost Allowed Types",
			{
				"document_type": "Purchase Invoice",
				"parent": "Repost Accounting Ledger Settings",
			},
		):
			settings = frappe.get_single("Repost Accounting Ledger Settings")
			settings.append("allowed_types", {"document_type": "Purchase Invoice", "allowed": 1})
			settings.save()

		# Case 1: Valid doctype "Purchase Invoice"
		allowed_types = get_repost_allowed_types(
			doctype="Repost Allowed Types",
			txt="Purchase Invoice",
			searchfield="document_type",
			start=0,
			page_len=10,
			filters={},
		)

		self.assertTrue(
			any("Purchase Invoice" in row for row in allowed_types),
			"Purchase Invoice should be returned in allowed types",
		)

		# Case 2: Wrong doctype should return empty list
		wrong_types = get_repost_allowed_types(
			doctype="Repost Allowed Types",
			txt="Non Existing Doctype",
			searchfield="document_type",
			start=0,
			page_len=10,
			filters={},
		)

		self.assertEqual(wrong_types, [], "Non Existing Doctype should return an empty list")


def update_repost_settings():
	allowed_types = [
		"Sales Invoice",
		"Purchase Invoice",
		"Payment Entry",
		"Journal Entry",
		"Purchase Receipt",
	]
	repost_settings = frappe.get_doc("Repost Accounting Ledger Settings")
	for x in allowed_types:
		repost_settings.append("allowed_types", {"document_type": x, "allowed": True})
		repost_settings.save()


def check_existing_fiscal_years(start_date, end_date):
	return frappe.get_all(
		"Fiscal Year",
		filters={
			"year_start_date": ("<=", end_date),
			"year_end_date": (">=", start_date),
		},
		fields=["name"],
	)
