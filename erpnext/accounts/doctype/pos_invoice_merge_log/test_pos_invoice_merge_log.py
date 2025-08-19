# Copyright (c) 2020, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt

import json
import unittest

import frappe
from frappe.tests.utils import change_settings
from frappe.utils import (
	flt,
	getdate,
	nowdate,
)

from erpnext.accounts.doctype.pos_closing_entry.test_pos_closing_entry import init_user_and_profile
from erpnext.accounts.doctype.pos_invoice.pos_invoice import make_sales_return
from erpnext.accounts.doctype.pos_invoice.test_pos_invoice import create_pos_invoice
from erpnext.accounts.doctype.pos_invoice_merge_log.pos_invoice_merge_log import (
	check_scheduler_status,
	consolidate_pos_invoices,
)
from erpnext.accounts.doctype.pos_opening_entry.test_pos_opening_entry import create_opening_entry
from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice
from erpnext.stock.doctype.serial_and_batch_bundle.test_serial_and_batch_bundle import (
	get_serial_nos_from_bundle,
)
from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry


class TestPOSInvoiceMergeLog(unittest.TestCase):
	def test_consolidated_invoice_creation(self):
		frappe.db.sql("delete from `tabPOS Invoice`")

		try:
			test_user, pos_profile = init_user_and_profile()

			pos_inv = create_pos_invoice(rate=300, do_not_submit=1)
			pos_inv.append(
				"payments",
				{"mode_of_payment": "Cash", "account": "Cash - _TC", "amount": pos_inv.grand_total},
			)
			pos_inv.save()
			pos_inv.submit()

			pos_inv2 = create_pos_invoice(rate=3200, do_not_submit=1)
			pos_inv2.append(
				"payments",
				{"mode_of_payment": "Cash", "account": "Cash - _TC", "amount": pos_inv2.grand_total},
			)
			pos_inv2.save()
			pos_inv2.submit()

			pos_inv3 = create_pos_invoice(customer="_Test Customer 2", rate=2300, do_not_submit=1)
			pos_inv3.append(
				"payments",
				{"mode_of_payment": "Cash", "account": "Cash - _TC", "amount": pos_inv3.grand_total},
			)
			pos_inv3.save()
			pos_inv3.submit()

			frappe.flags.in_test = True
			consolidate_pos_invoices()

			pos_inv.load_from_db()
			self.assertTrue(frappe.db.exists("Sales Invoice", pos_inv.consolidated_invoice))

			pos_inv3.load_from_db()
			self.assertTrue(frappe.db.exists("Sales Invoice", pos_inv3.consolidated_invoice))

			self.assertFalse(pos_inv.consolidated_invoice == pos_inv3.consolidated_invoice)

		finally:
			frappe.flags.in_test = False
			frappe.set_user("Administrator")
			frappe.db.sql("delete from `tabPOS Profile`")
			frappe.db.sql("delete from `tabPOS Invoice`")

	def test_consolidated_credit_note_creation(self):
		frappe.db.sql("delete from `tabPOS Invoice`")

		try:
			test_user, pos_profile = init_user_and_profile()

			pos_inv = create_pos_invoice(rate=300, do_not_submit=1)
			pos_inv.append(
				"payments",
				{"mode_of_payment": "Cash", "account": "Cash - _TC", "amount": pos_inv.grand_total},
			)
			pos_inv.save()
			pos_inv.submit()

			pos_inv2 = create_pos_invoice(rate=3200, do_not_submit=1)
			pos_inv2.append(
				"payments",
				{"mode_of_payment": "Cash", "account": "Cash - _TC", "amount": pos_inv2.grand_total},
			)
			pos_inv2.save()
			pos_inv2.submit()

			pos_inv3 = create_pos_invoice(customer="_Test Customer 2", rate=2300, do_not_submit=1)
			pos_inv3.append(
				"payments",
				{"mode_of_payment": "Cash", "account": "Cash - _TC", "amount": pos_inv3.grand_total},
			)
			pos_inv3.save()
			pos_inv3.submit()

			pos_inv_cn = make_sales_return(pos_inv.name)
			pos_inv_cn.set("payments", [])
			grand_total = pos_inv_cn.grand_total
			cash_amount = round(grand_total * 0.3, 2)
			bank_amount = round(grand_total * 0.7, 2)
			pos_inv_cn.append(
				"payments", {"mode_of_payment": "Cash", "account": "Cash - _TC", "amount": cash_amount}
			)
			pos_inv_cn.append(
				"payments",
				{"mode_of_payment": "Bank Draft", "account": "_Test Bank - _TC", "amount": bank_amount},
			)
			pos_inv_cn.paid_amount = grand_total
			pos_inv_cn.submit()
			frappe.flags.in_test = True

			consolidate_pos_invoices()

			pos_inv.load_from_db()
			self.assertTrue(frappe.db.exists("Sales Invoice", pos_inv.consolidated_invoice))

			pos_inv3.load_from_db()
			self.assertTrue(frappe.db.exists("Sales Invoice", pos_inv3.consolidated_invoice))

			pos_inv_cn.load_from_db()
			self.assertTrue(frappe.db.exists("Sales Invoice", pos_inv_cn.consolidated_invoice))
			consolidated_credit_note = frappe.get_doc("Sales Invoice", pos_inv_cn.consolidated_invoice)
			self.assertEqual(consolidated_credit_note.is_return, 1)
			self.assertEqual(consolidated_credit_note.payments[0].mode_of_payment, "Cash")
			self.assertEqual(consolidated_credit_note.payments[0].amount, -100)
			self.assertEqual(consolidated_credit_note.payments[1].mode_of_payment, "Bank Draft")
			self.assertEqual(consolidated_credit_note.payments[1].amount, -200)

		finally:
			frappe.flags.in_test = False
			frappe.set_user("Administrator")
			frappe.db.sql("delete from `tabPOS Profile`")
			frappe.db.sql("delete from `tabPOS Invoice`")

	def test_consolidated_invoice_item_taxes(self):
		frappe.db.sql("delete from `tabPOS Invoice`")

		try:
			inv = create_pos_invoice(qty=1, rate=100, do_not_save=True)

			inv.append(
				"taxes",
				{
					"account_head": "_Test Account VAT - _TC",
					"charge_type": "On Net Total",
					"cost_center": "_Test Cost Center - _TC",
					"description": "VAT",
					"doctype": "Sales Taxes and Charges",
					"rate": 9,
				},
			)
			inv.insert()
			inv.payments[0].amount = inv.grand_total
			inv.save()
			inv.submit()

			inv2 = create_pos_invoice(qty=1, rate=100, do_not_save=True)
			inv2.get("items")[0].item_code = "_Test Item 2"
			inv2.append(
				"taxes",
				{
					"account_head": "_Test Account VAT - _TC",
					"charge_type": "On Net Total",
					"cost_center": "_Test Cost Center - _TC",
					"description": "VAT",
					"doctype": "Sales Taxes and Charges",
					"rate": 5,
				},
			)
			inv2.insert()
			inv2.payments[0].amount = inv.grand_total
			inv2.save()
			inv2.submit()

			frappe.flags.in_test = True
			consolidate_pos_invoices()
			inv.load_from_db()

			consolidated_invoice = frappe.get_doc("Sales Invoice", inv.consolidated_invoice)
			item_wise_tax_detail = json.loads(consolidated_invoice.get("taxes")[0].item_wise_tax_detail)

			tax_rate, amount = item_wise_tax_detail.get("_Test Item")
			self.assertEqual(tax_rate, 9)
			self.assertEqual(amount, 9)

			tax_rate2, amount2 = item_wise_tax_detail.get("_Test Item 2")
			self.assertEqual(tax_rate2, 5)
			self.assertEqual(amount2, 5)
		finally:
			frappe.flags.in_test = False
			frappe.set_user("Administrator")
			frappe.db.sql("delete from `tabPOS Profile`")
			frappe.db.sql("delete from `tabPOS Invoice`")

	def test_consolidation_round_off_error_1(self):
		"""
		Test round off error in consolidated invoice creation if POS Invoice has inclusive tax
		"""

		frappe.db.sql("delete from `tabPOS Invoice`")

		try:
			make_stock_entry(
				to_warehouse="_Test Warehouse - _TC",
				item_code="_Test Item",
				rate=8000,
				qty=10,
			)

			test_user, pos_profile = init_user_and_profile()
			pos_profile_doc = frappe.get_doc("POS Profile", pos_profile.name)
			pos_profile_doc.allow_partial_payment = 1
			pos_profile_doc.save(ignore_permissions=True)

			inv = create_pos_invoice(qty=3, rate=10000, do_not_save=True, pos_profile=pos_profile)
			inv.append(
				"taxes",
				{
					"account_head": "_Test Account VAT - _TC",
					"charge_type": "On Net Total",
					"cost_center": "_Test Cost Center - _TC",
					"description": "VAT",
					"doctype": "Sales Taxes and Charges",
					"rate": 7.5,
					"included_in_print_rate": 1,
				},
			)
			inv.append(
				"payments", {"mode_of_payment": "Cash", "account": "Cash - _TC", "amount": inv.grand_total}
			)
			inv.save(ignore_permissions=True)
			inv.submit()

			inv2 = create_pos_invoice(qty=3, rate=10000, do_not_save=True, pos_profile=pos_profile)
			inv2.append(
				"taxes",
				{
					"account_head": "_Test Account VAT - _TC",
					"charge_type": "On Net Total",
					"cost_center": "_Test Cost Center - _TC",
					"description": "VAT",
					"doctype": "Sales Taxes and Charges",
					"rate": 7.5,
					"included_in_print_rate": 1,
				},
			)
			inv2.append(
				"payments", {"mode_of_payment": "Cash", "account": "Cash - _TC", "amount": inv2.grand_total}
			)
			inv2.save(ignore_permissions=True)
			inv2.submit()

			frappe.flags.in_test = True
			consolidate_pos_invoices()

			inv.load_from_db()
			consolidated_invoice = frappe.get_doc("Sales Invoice", inv.consolidated_invoice)
			self.assertEqual(consolidated_invoice.outstanding_amount, 0)
			self.assertEqual(consolidated_invoice.status, "Paid")

		finally:
			frappe.flags.in_test = False
			frappe.set_user("Administrator")
			frappe.db.sql("delete from `tabPOS Profile`")
			frappe.db.sql("delete from `tabPOS Invoice`")

	def test_consolidation_round_off_error_2(self):
		"""
		Test the same case as above but with an Unpaid POS Invoice
		"""
		frappe.db.sql("delete from `tabPOS Invoice`")

		try:
			make_stock_entry(
				to_warehouse="_Test Warehouse - _TC",
				item_code="_Test Item",
				rate=8000,
				qty=10,
			)

			test_user, pos_profile = init_user_and_profile()
			pos_profile_doc = frappe.get_doc("POS Profile", pos_profile.name)
			pos_profile_doc.allow_partial_payment = 1
			pos_profile_doc.save(ignore_permissions=True)

			inv = create_pos_invoice(qty=6, rate=10000, do_not_save=True, pos_profile=pos_profile)
			inv.append(
				"taxes",
				{
					"account_head": "_Test Account VAT - _TC",
					"charge_type": "On Net Total",
					"cost_center": "_Test Cost Center - _TC",
					"description": "VAT",
					"doctype": "Sales Taxes and Charges",
					"rate": 7.5,
					"included_in_print_rate": 1,
				},
			)
			inv.append(
				"payments", {"mode_of_payment": "Cash", "account": "Cash - _TC", "amount": inv.grand_total}
			)
			inv.save(ignore_permissions=True)
			inv.submit()

			inv2 = create_pos_invoice(qty=6, rate=10000, do_not_save=True, pos_profile=pos_profile)
			inv2.append(
				"taxes",
				{
					"account_head": "_Test Account VAT - _TC",
					"charge_type": "On Net Total",
					"cost_center": "_Test Cost Center - _TC",
					"description": "VAT",
					"doctype": "Sales Taxes and Charges",
					"rate": 7.5,
					"included_in_print_rate": 1,
				},
			)
			inv2.append(
				"payments", {"mode_of_payment": "Cash", "account": "Cash - _TC", "amount": inv2.grand_total}
			)
			inv2.save(ignore_permissions=True)
			inv2.submit()

			inv3 = create_pos_invoice(qty=3, rate=600, do_not_save=True, pos_profile=pos_profile)
			inv3.append(
				"payments", {"mode_of_payment": "Cash", "account": "Cash - _TC", "amount": inv3.grand_total}
			)
			inv3.save(ignore_permissions=True)
			inv3.submit()
			frappe.flags.in_test = True
			consolidate_pos_invoices()

			inv.load_from_db()
			consolidated_invoice = frappe.get_doc("Sales Invoice", inv.consolidated_invoice)
			self.assertNotEqual(consolidated_invoice.outstanding_amount, 800)
			self.assertEqual(consolidated_invoice.status, "Paid")

		finally:
			frappe.flags.in_test = False
			frappe.set_user("Administrator")
			frappe.db.sql("delete from `tabPOS Profile`")
			frappe.db.sql("delete from `tabPOS Invoice`")

	@change_settings(
		"System Settings", {"number_format": "#,###.###", "currency_precision": 3, "float_precision": 3}
	)
	def test_consolidation_round_off_error_3(self):
		frappe.db.sql("delete from `tabPOS Invoice`")

		try:
			make_stock_entry(
				to_warehouse="_Test Warehouse - _TC",
				item_code="_Test Item",
				rate=8000,
				qty=10,
			)
			test_user, pos_profile = init_user_and_profile()
			pos_profile_doc = frappe.get_doc("POS Profile", pos_profile.name)
			pos_profile_doc.allow_partial_payment = 1
			pos_profile_doc.save(ignore_permissions=True)

			item_rates = [69, 59, 29]
			for _i in [1, 2]:
				inv = create_pos_invoice(is_return=1, do_not_save=1, pos_profile=pos_profile)
				inv.items = []
				for rate in item_rates:
					inv.append(
						"items",
						{
							"item_code": "_Test Item",
							"warehouse": "_Test Warehouse - _TC",
							"qty": -1,
							"rate": rate,
							"income_account": "Sales - _TC",
							"expense_account": "Cost of Goods Sold - _TC",
							"cost_center": "_Test Cost Center - _TC",
						},
					)
				inv.append(
					"taxes",
					{
						"account_head": "_Test Account VAT - _TC",
						"charge_type": "On Net Total",
						"cost_center": "_Test Cost Center - _TC",
						"description": "VAT",
						"doctype": "Sales Taxes and Charges",
						"rate": 15,
						"included_in_print_rate": 1,
					},
				)
				inv.payments = []
				payment_amount = inv.grand_total
				inv.append(
					"payments",
					{"mode_of_payment": "Cash", "account": "Cash - _TC", "amount": payment_amount},
				)
				inv.paid_amount = payment_amount
				inv.save(ignore_permissions=True)
				inv.submit()
			frappe.flags.in_test = True
			consolidate_pos_invoices()

			inv.load_from_db()
			consolidated_invoice = frappe.get_doc("Sales Invoice", inv.consolidated_invoice)
			self.assertEqual(consolidated_invoice.status, "Return")
			self.assertEqual(consolidated_invoice.rounding_adjustment, -0.002)

		finally:
			frappe.flags.in_test = False
			frappe.set_user("Administrator")
			frappe.db.sql("delete from `tabPOS Profile`")
			frappe.db.sql("delete from `tabPOS Invoice`")

	def test_consolidation_rounding_adjustment(self):
		"""
		Test if the rounding adjustment is calculated correctly
		"""
		frappe.db.sql("delete from `tabPOS Invoice`")

		try:
			make_stock_entry(
				to_warehouse="_Test Warehouse - _TC",
				item_code="_Test Item",
				rate=8000,
				qty=10,
			)

			test_user, pos_profile = init_user_and_profile()
			pos_profile_doc = frappe.get_doc("POS Profile", pos_profile.name)
			pos_profile_doc.allow_partial_payment = 1
			pos_profile_doc.save(ignore_permissions=True)

			inv = create_pos_invoice(qty=1, rate=69.5, do_not_save=True, pos_profile=pos_profile)
			inv.append(
				"payments", {"mode_of_payment": "Cash", "account": "Cash - _TC", "amount": inv.grand_total}
			)
			inv.save(ignore_permissions=True)
			inv.submit()

			inv2 = create_pos_invoice(qty=1, rate=59.5, do_not_save=True, pos_profile=pos_profile)
			inv2.append(
				"payments", {"mode_of_payment": "Cash", "account": "Cash - _TC", "amount": inv2.grand_total}
			)
			inv2.save(ignore_permissions=True)
			inv2.submit()
			frappe.flags.in_test = True
			consolidate_pos_invoices()

			inv.load_from_db()
			consolidated_invoice = frappe.get_doc("Sales Invoice", inv.consolidated_invoice)
			self.assertEqual(consolidated_invoice.rounding_adjustment, 1)

		finally:
			frappe.flags.in_test = False
			frappe.set_user("Administrator")
			frappe.db.sql("delete from `tabPOS Profile`")
			frappe.db.sql("delete from `tabPOS Invoice`")

	def test_serial_no_case_1(self):
		"""
		Create a POS Invoice with serial no
		Create a Return Invoice with serial no
		Create a POS Invoice with serial no again
		Consolidate the invoices

		The first POS Invoice should be consolidated with a separate single Merge Log
		The second and third POS Invoice should be consolidated with a single Merge Log
		"""

		from erpnext.stock.doctype.stock_entry.test_stock_entry import make_serialized_item

		frappe.db.sql("delete from `tabPOS Invoice`")

		try:
			create_uom("_Test UOM")
			se = make_serialized_item()
			serial_no = get_serial_nos_from_bundle(se.get("items")[0].serial_and_batch_bundle)[0]

			test_user, pos_profile = init_user_and_profile()
			pos_profile_doc = frappe.get_doc("POS Profile", pos_profile.name)
			pos_profile_doc.allow_partial_payment = 1
			pos_profile_doc.save(ignore_permissions=True)

			pos_inv = create_pos_invoice(
				item_code="_Test Serialized Item With Series",
				serial_no=[serial_no],
				qty=1,
				rate=100,
				do_not_submit=1,
				pos_profile=pos_profile,
			)
			pos_inv.append(
				"payments",
				{"mode_of_payment": "Cash", "account": "Cash - _TC", "amount": pos_inv.grand_total},
			)
			pos_inv.save(ignore_permissions=True)
			pos_inv.submit()

			pos_inv_cn = make_sales_return(pos_inv.name)
			pos_inv_cn.paid_amount = -100
			pos_inv_cn.submit()

			pos_inv2 = create_pos_invoice(
				item_code="_Test Serialized Item With Series",
				serial_no=[serial_no],
				qty=1,
				rate=100,
				do_not_submit=1,
				pos_profile=pos_profile,
			)
			pos_inv2.append(
				"payments",
				{"mode_of_payment": "Cash", "account": "Cash - _TC", "amount": pos_inv2.grand_total},
			)
			pos_inv2.save(ignore_permissions=True)
			pos_inv2.submit()
			frappe.flags.in_test = True
			consolidate_pos_invoices()

			pos_inv.load_from_db()
			pos_inv2.load_from_db()

			self.assertNotEqual(pos_inv.consolidated_invoice, pos_inv2.consolidated_invoice)

		finally:
			frappe.flags.in_test = False
			frappe.set_user("Administrator")
			frappe.db.sql("delete from `tabPOS Profile`")
			frappe.db.sql("delete from `tabPOS Invoice`")

	def test_check_scheduler_status_TC_ACC_340(self):
		frappe.flags.in_test = False

		try:
			frappe.db.set_single_value("System Settings", "enable_scheduler", 0)
			with self.assertRaises(frappe.ValidationError) as err:
				check_scheduler_status()

			self.assertIn("scheduler is inactive. cannot enqueue job.", str(err.exception).lower())
		finally:
			frappe.flags.in_test = True
			frappe.db.set_single_value("System Settings", "enable_scheduler", 1)

	def test_cancel_merge_logs_TC_AC_355(self):
		"""
		Create a POS Invoice
		Create POS Invoice Merge Log for the invoice
		Check the status of the POS Invoice Marge Log
		Call the cancel_merge_logs function
		Check the status of the POS Invoice Marge Log
		"""

		from erpnext.accounts.doctype.pos_invoice_merge_log.pos_invoice_merge_log import cancel_merge_logs

		frappe.db.sql("delete from `tabPOS Invoice`")

		# Create a POS Invoice

		test_user, pos_profile = init_user_and_profile()
		opening_entry = create_opening_entry(pos_profile, test_user.name)
		pos_profile_doc = frappe.get_doc("POS Profile", pos_profile.name)
		pos_profile_doc.allow_partial_payment = 1
		pos_profile_doc.save(ignore_permissions=True)
		inv = create_pos_invoice(qty=1, rate=70, do_not_save=True, pos_profile=pos_profile)
		inv.append("payments", {"mode_of_payment": "Cash", "account": "Cash - _TC", "amount": 80})
		inv.save(ignore_permissions=True)

		inv.submit()
		self.assertEqual(opening_entry.status, "Open")

		if not frappe.db.exists("Fiscal Year", "2025-2026"):
			frappe.get_doc(
				{
					"doctype": "Fiscal Year",
					"year": "2025-2026",
					"year_start_date": getdate("2025-04-01"),
					"year_end_date": getdate("2026-03-31"),
					"disabled": 0,
					"companies": [{"company": pos_profile_doc.company}],
				}
			).insert(ignore_permissions=True)

		# Create Merge Log for the invoice
		merge_logs = make_merge_log([{"name": inv.name}])

		# check before cancelling
		self.assertTrue(merge_logs)
		merge_log_doc = frappe.get_doc("POS Invoice Merge Log", merge_logs[0])
		self.assertEqual(merge_log_doc.docstatus, 1)  # Submitted

		# Cancel the merge log(s)
		cancel_merge_logs(merge_logs, closing_entry=None)

		# Validate that merge log is cancelled
		cancelled_merge_log = frappe.get_doc("POS Invoice Merge Log", merge_logs[0])
		self.assertEqual(cancelled_merge_log.docstatus, 2)  # Cancelled

	def test_get_error_message_TC_AC_356(self):
		from erpnext.accounts.doctype.pos_invoice_merge_log.pos_invoice_merge_log import get_error_message

		msg = "Error Message"
		result = get_error_message(msg)
		self.assertEqual(result, msg)

	def test_get_serial_and_batch_bundles_TC_ACC_373(self):
		pos_invoices = []
		test_user, pos_profile = init_user_and_profile()

		pos_profile_doc = frappe.get_doc("POS Profile", pos_profile.name)
		pos_profile_doc.allow_partial_payment = 1
		pos_profile_doc.save(ignore_permissions=True)
		inv = create_pos_invoice(qty=1, rate=70, do_not_save=True, pos_profile=pos_profile)
		inv.append("payments", {"mode_of_payment": "Cash", "account": "Cash - _TC", "amount": 70})
		inv.save(ignore_permissions=True)

		inv.submit()

		inv01 = create_pos_invoice(qty=1, rate=70, do_not_save=True, pos_profile=pos_profile)
		inv01.append("payments", {"mode_of_payment": "Cash", "account": "Cash - _TC", "amount": 70})
		inv01.save(ignore_permissions=True)

		inv01.submit()
		pos_invoices.append(inv.name)
		pos_invoices.append(inv01.name)

		if pos_invoices:
			serial_and_batch_bundle = frappe.get_all(
				"POS Invoice Item",
				filters={
					"docstatus": 1,
					"parent": ["in", pos_invoices],
					"serial_and_batch_bundle": ["is", "set"],
				},
				pluck="serial_and_batch_bundle",
			)

		self.assertEqual(serial_and_batch_bundle, [])


def make_merge_log(invoices):
	merge_logs = []

	merge_log = frappe.new_doc("POS Invoice Merge Log")
	merge_log.posting_date = getdate(nowdate())

	for inv in invoices:
		inv_data = frappe.db.get_values(
			"POS Invoice", inv.get("name"), ["customer", "posting_date", "grand_total"], as_dict=1
		)[0]

		merge_log.customer = inv_data.customer
		merge_log.append(
			"pos_invoices",
			{
				"pos_invoice": inv.get("name"),
				"customer": inv_data.customer,
				"posting_date": inv_data.posting_date,
				"grand_total": inv_data.grand_total,
			},
		)

	merge_log.save(ignore_permissions=True)
	merge_log.submit()

	merge_logs.append(merge_log.name)
	return merge_logs


def create_uom(uom):
	existing_uom = frappe.db.get_value("UOM", filters={"uom_name": uom}, fieldname="uom_name")
	if existing_uom:
		return existing_uom
	else:
		new_uom = frappe.new_doc("UOM")
		new_uom.uom_name = uom
		new_uom.save(ignore_permissions=True)
		return new_uom.uom_name
