# Copyright (c) 2018, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt


import unittest

import frappe
from frappe.utils import today

from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
from erpnext.accounts.report.sales_payment_summary.sales_payment_summary import (
	get_mode_of_payment_details,
	get_mode_of_payments,
)

test_dependencies = ["Sales Invoice"]


class TestSalesPaymentSummary(unittest.TestCase):
	@classmethod
	def setUpClass(self):
		create_records()
		pes = frappe.get_all("Payment Entry")
		jes = frappe.get_all("Journal Entry")
		sis = frappe.get_all("Sales Invoice")
		for pe in pes:
			frappe.db.set_value("Payment Entry", pe.name, "docstatus", 2)
		for je in jes:
			frappe.db.set_value("Journal Entry", je.name, "docstatus", 2)
		for si in sis:
			frappe.db.set_value("Sales Invoice", si.name, "docstatus", 2)

	def test_execute_and_get_pos_columns_TC_ACC_700(self):
		# --- Case 1: Non-POS filter ---
		non_pos_filters = {"is_pos": 0, "from_date": "1900-01-01", "to_date": today(), "company": "_Test Company"}
		columns, data = frappe.get_attr("erpnext.accounts.report.sales_payment_summary.sales_payment_summary.execute")(non_pos_filters)

		self.assertIsInstance(columns, list)
		self.assertGreater(len(columns), 0)
		self.assertIn("Date", columns[0])
		self.assertIn("Payments", columns[-1])
		self.assertIsInstance(data, list)

		# --- Case 2: POS filter ---
		pos_filters = {"is_pos": 1, "from_date": "1900-01-01", "to_date": today(), "company": "_Test Company"}
		columns, data = frappe.get_attr("erpnext.accounts.report.sales_payment_summary.sales_payment_summary.execute")(pos_filters)

		self.assertEqual(columns, frappe.get_attr("erpnext.accounts.report.sales_payment_summary.sales_payment_summary.get_pos_columns")())
		self.assertTrue(any("Warehouse" in col for col in columns))
		self.assertTrue(any("Cost Center" in col for col in columns))
		self.assertIsInstance(data, list)

		# --- Case 3: Empty filters (default path coverage) ---
		columns, data = frappe.get_attr("erpnext.accounts.report.sales_payment_summary.sales_payment_summary.execute")({})
		self.assertIsInstance(columns, list)
		self.assertIsInstance(data, list)

	def test_get_columns_and_get_pos_sales_payment_data_TC_ACC_701(self):
		# Import functions directly
		get_columns = frappe.get_attr("erpnext.accounts.report.sales_payment_summary.sales_payment_summary.get_columns")
		get_pos_columns = frappe.get_attr("erpnext.accounts.report.sales_payment_summary.sales_payment_summary.get_pos_columns")
		get_pos_sales_payment_data = frappe.get_attr("erpnext.accounts.report.sales_payment_summary.sales_payment_summary.get_pos_sales_payment_data")

		# --- Case 1: Non-POS columns ---
		filters = {"is_pos": 0}
		columns = get_columns(filters)

		self.assertIsInstance(columns, list)
		self.assertEqual(len(columns), 6)
		self.assertIn("Date", columns[0])
		self.assertIn("Payments", columns[-1])
		self.assertNotIn("Warehouse", " ".join(columns))

		# --- Case 2: POS columns ---
		filters = {"is_pos": 1}
		columns = get_columns(filters)

		self.assertEqual(columns, get_pos_columns())
		self.assertTrue(any("Warehouse" in col for col in columns))
		self.assertTrue(any("Cost Center" in col for col in columns))

		# --- Case 3: get_pos_sales_payment_data ---
		# We'll mock frappe.db.sql via monkey patch to simulate DB return rows
		fake_row = {
			"posting_date": "2025-10-27",
			"owner": "test_user@example.com",
			"mode_of_payment": "Cash",
			"net_total": 1000.0,
			"total_taxes": 50.0,
			"paid_amount": 1050.0,
			"warehouse": "Main Warehouse",
			"cost_center": "Main - _TC",
		}

		# Patch get_pos_invoice_data to return mock data
		from unittest.mock import patch

		with patch(
			"erpnext.accounts.report.sales_payment_summary.sales_payment_summary.get_pos_invoice_data",
			return_value=[fake_row],
		):
			data = get_pos_sales_payment_data(filters)

		# Verify structure
		self.assertEqual(len(data), 1)
		self.assertEqual(data[0][0], fake_row["posting_date"])
		self.assertEqual(data[0][1], fake_row["owner"])
		self.assertEqual(data[0][2], fake_row["mode_of_payment"])
		self.assertEqual(data[0][3], fake_row["net_total"])
		self.assertEqual(data[0][4], fake_row["total_taxes"])
		self.assertEqual(data[0][5], fake_row["paid_amount"])
		self.assertEqual(data[0][6], fake_row["warehouse"])
		self.assertEqual(data[0][7], fake_row["cost_center"])

	def test_get_sales_payment_data_TC_ACC_702(self):
		from unittest.mock import patch
		from frappe.utils import cstr
		import frappe

		# Import function to test
		get_sales_payment_data = frappe.get_attr(
			"erpnext.accounts.report.sales_payment_summary.sales_payment_summary.get_sales_payment_data"
		)

		# Prepare dummy data using frappe._dict
		fake_invoice = frappe._dict({
			"posting_date": frappe.utils.now(),
			"owner": "test_user@example.com",
			"net_total": 5000,
			"total_taxes": 250,
			"paid_amount": 5250,
		})
		owner_posting_date = fake_invoice["owner"] + cstr(fake_invoice["posting_date"])

		# Mock return values for helper functions
		with patch(
			"erpnext.accounts.report.sales_payment_summary.sales_payment_summary.get_sales_invoice_data",
			return_value=[fake_invoice],
		), patch(
			"erpnext.accounts.report.sales_payment_summary.sales_payment_summary.get_mode_of_payments",
			return_value={owner_posting_date: ["Cash", "Credit Card"]},
		), patch(
			"erpnext.accounts.report.sales_payment_summary.sales_payment_summary.get_mode_of_payment_details",
			return_value={owner_posting_date: [("Cash", 2000), ("Credit Card", 3000)]},
		):

			# Columns mock (not used heavily but required by function signature)
			columns = ["Date", "Owner", "Payment Mode", "Sales and Returns", "Taxes", "Payments"]

			# --- Case 1: Without payment_detail (default path) ---
			filters = {"payment_detail": 0}
			data = get_sales_payment_data(filters, columns)

			self.assertEqual(len(data), 1)
			self.assertEqual(data[0][0], fake_invoice["posting_date"])
			self.assertEqual(data[0][1], fake_invoice["owner"])
			self.assertIn("Cash", data[0][2])  # Combined mode_of_payments string
			self.assertEqual(data[0][3], fake_invoice["net_total"])
			self.assertEqual(data[0][4], fake_invoice["total_taxes"])
			self.assertEqual(data[0][5], 5000)  # total_payment sum of 2000+3000

			# --- Case 2: With payment_detail = True ---
			filters = {"payment_detail": 1}
			data = get_sales_payment_data(filters, columns)

			# Should have multiple rows: 1 main + 2 mode-of-payment rows
			self.assertEqual(len(data), 3)

			# Check the first summary row
			self.assertEqual(data[0][:3], [fake_invoice["posting_date"], fake_invoice["owner"], " "])
			# Check one of the detailed payment rows
			self.assertIn(("Cash", 2000), [tuple([r[2], r[5]]) for r in data[1:]])
			self.assertIn(("Credit Card", 3000), [tuple([r[2], r[5]]) for r in data[1:]])

	def test_get_conditions_TC_ACC_703(self):
		import frappe

		get_conditions = frappe.get_attr(
			"erpnext.accounts.report.sales_payment_summary.sales_payment_summary.get_conditions"
		)

		# --- Case 1: No filters ---
		conditions = get_conditions({})
		self.assertEqual(conditions, "1=1")

		# --- Case 2: With all filters ---
		filters = {
			"from_date": "2025-01-01",
			"to_date": "2025-12-31",
			"company": "SmartMoviz Pvt Ltd",
			"customer": "Prateek RT",
			"owner": "admin@example.com",
			"is_pos": 1,
		}

		conditions = get_conditions(filters)

		# Each expected condition should exist in the SQL string
		self.assertIn("a.posting_date >= %(from_date)s", conditions)
		self.assertIn("a.posting_date <= %(to_date)s", conditions)
		self.assertIn("a.company=%(company)s", conditions)
		self.assertIn("a.customer = %(customer)s", conditions)
		self.assertIn("a.owner = %(owner)s", conditions)
		self.assertIn("a.is_pos = %(is_pos)s", conditions)

		# It should start with '1=1'
		self.assertTrue(conditions.startswith("1=1"))

		# --- Case 3: Partial filters (edge case) ---
		filters = {"customer": "John Doe"}
		conditions = get_conditions(filters)
		self.assertIn("a.customer = %(customer)s", conditions)
		self.assertNotIn("a.posting_date", conditions)

	def test_get_pos_invoice_data_TC_ACC_704(self):
		from unittest.mock import patch
		import frappe

		# Import function to test
		get_pos_invoice_data = frappe.get_attr(
			"erpnext.accounts.report.sales_payment_summary.sales_payment_summary.get_pos_invoice_data"
		)

		# Dummy filters
		filters = {
			"from_date": "2025-01-01",
			"to_date": "2025-12-31",
			"company": "SmartMoviz Pvt Ltd",
			"is_pos": 1,
		}

		# Mock SQL result
		fake_result = [
			{
				"posting_date": "2025-10-27",
				"owner": "admin@example.com",
				"net_total": 10000,
				"total_taxes": 500,
				"paid_amount": 10500,
				"outstanding_amount": 0,
				"mode_of_payment": "Cash",
				"warehouse": "Main Warehouse",
				"cost_center": "Sales - SM",
			}
		]

		with patch(
			"erpnext.accounts.report.sales_payment_summary.sales_payment_summary.get_conditions",
			return_value="a.company=%(company)s and a.is_pos=%(is_pos)s",
		) as mock_get_conditions, patch(
			"frappe.db.sql", return_value=fake_result
		) as mock_sql:

			result = get_pos_invoice_data(filters)

			# Ensure the SQL was executed once
			mock_sql.assert_called_once()
			mock_get_conditions.assert_called_once_with(filters)

			# Ensure the query string contains required clauses
			executed_query = mock_sql.call_args[0][0]
			self.assertIn("FROM `tabSales Invoice Item`", executed_query)
			self.assertIn("JOIN", executed_query)
			self.assertIn("GROUP BY owner, posting_date", executed_query)
			self.assertIn("AND a.company=%(company)s and a.is_pos=%(is_pos)s", executed_query)

			# Ensure filters were passed correctly
			self.assertEqual(mock_sql.call_args[0][1], filters)

			# Ensure returned data matches the mock result
			self.assertEqual(result, fake_result)
			self.assertEqual(result[0]["mode_of_payment"], "Cash")
			self.assertEqual(result[0]["warehouse"], "Main Warehouse")

	def test_get_sales_invoice_data_TC_ACC_705(self):
		from unittest.mock import patch
		import frappe

		# Import the function to test
		get_sales_invoice_data = frappe.get_attr(
			"erpnext.accounts.report.sales_payment_summary.sales_payment_summary.get_sales_invoice_data"
		)

		# Define dummy filters
		filters = {
			"from_date": "2025-01-01",
			"to_date": "2025-12-31",
			"company": "SmartMoviz Pvt Ltd",
		}

		# Fake SQL result
		fake_result = [
			{
				"posting_date": "2025-10-27",
				"owner": "test_user@example.com",
				"net_total": 12000,
				"total_taxes": 600,
				"paid_amount": 12600,
				"outstanding_amount": 0,
			}
		]

		with patch(
			"erpnext.accounts.report.sales_payment_summary.sales_payment_summary.get_conditions",
			return_value="a.company=%(company)s",
		) as mock_get_conditions, patch(
			"frappe.db.sql", return_value=fake_result
		) as mock_sql:

			# Call the function
			result = get_sales_invoice_data(filters)

			# Verify helper function was called
			mock_get_conditions.assert_called_once_with(filters)

			# Verify SQL was executed
			mock_sql.assert_called_once()

			# Verify SQL query structure
			executed_query = mock_sql.call_args[0][0]
			self.assertIn("from `tabSales Invoice` a", executed_query)
			self.assertIn("where a.docstatus = 1", executed_query)
			self.assertIn("group by", executed_query)
			self.assertIn("a.company=%(company)s", executed_query)

			# Ensure filters were passed to frappe.db.sql
			self.assertEqual(mock_sql.call_args[0][1], filters)

			# Ensure return value matches fake result
			self.assertEqual(result, fake_result)
			self.assertEqual(result[0]["owner"], "test_user@example.com")
			self.assertEqual(result[0]["net_total"], 12000)
			self.assertEqual(result[0]["total_taxes"], 600)

	def test_get_invoices_TC_ACC_707(self):
		from unittest.mock import patch

		# Import the target function
		get_invoices = frappe.get_attr(
			"erpnext.accounts.report.sales_payment_summary.sales_payment_summary.get_invoices"
		)

		# Case 1: When invoices exist
		filters = {"from_date": "2025-01-01", "to_date": "2025-12-31", "company": "Test Company"}
		fake_result = [{"name": "SINV-0001"}, {"name": "SINV-0002"}]

		with patch(
			"erpnext.accounts.report.sales_payment_summary.sales_payment_summary.get_conditions",
			return_value="1=1",
		), patch(
			"frappe.db.sql", return_value=fake_result
		) as mock_sql:

			result = get_invoices(filters)

			# Assertions
			self.assertEqual(result, fake_result)
			mock_sql.assert_called_once()

		# Case 2: When no invoices exist
		with patch(
			"erpnext.accounts.report.sales_payment_summary.sales_payment_summary.get_conditions",
			return_value="1=1",
		), patch(
			"frappe.db.sql", return_value=[]
		):
			result = get_invoices({})
			self.assertEqual(result, [])

		# Case 3: When filters are None
		with patch(
			"erpnext.accounts.report.sales_payment_summary.sales_payment_summary.get_conditions",
			return_value="1=1",
		), patch(
			"frappe.db.sql", return_value=[{"name": "SINV-0003"}]
		):
			result = get_invoices(None)
			self.assertEqual(result, [{"name": "SINV-0003"}])

	


	def test_get_mode_of_payments(self):
		filters = get_filters()

		for _dummy in range(2):
			si = create_sales_invoice_record()
			si.insert()
			si.submit()

			if int(si.name[-3:]) % 2 == 0:
				bank_account = "_Test Cash - _TC"
				mode_of_payment = "Cash"
			else:
				bank_account = "_Test Bank - _TC"
				mode_of_payment = "Credit Card"

			pe = get_payment_entry("Sales Invoice", si.name, bank_account=bank_account)
			pe.reference_no = "_Test"
			pe.reference_date = today()
			pe.mode_of_payment = mode_of_payment
			pe.insert(ignore_permissions=True)
			pe.submit()

		mop = get_mode_of_payments(filters)
		self.assertTrue("Credit Card" in next(iter(mop.values())))
		self.assertTrue("Cash" in next(iter(mop.values())))

		# Cancel all Cash payment entry and check if this mode of payment is still fetched.
		payment_entries = frappe.get_all(
			"Payment Entry",
			filters={"mode_of_payment": "Cash", "docstatus": 1},
			fields=["name", "docstatus"],
		)
		for payment_entry in payment_entries:
			pe = frappe.get_doc("Payment Entry", payment_entry.name)
			pe.cancel()

		mop = get_mode_of_payments(filters)
		self.assertTrue("Credit Card" in next(iter(mop.values())))
		self.assertTrue("Cash" not in next(iter(mop.values())))

	def test_get_mode_of_payments_details(self):
		filters = get_filters()

		for _dummy in range(2):
			si = create_sales_invoice_record()
			si.insert()
			si.submit()

			if int(si.name[-3:]) % 2 == 0:
				bank_account = "_Test Cash - _TC"
				mode_of_payment = "Cash"
			else:
				bank_account = "_Test Bank - _TC"
				mode_of_payment = "Credit Card"

			pe = get_payment_entry("Sales Invoice", si.name, bank_account=bank_account)
			pe.reference_no = "_Test"
			pe.reference_date = today()
			pe.mode_of_payment = mode_of_payment
			pe.insert(ignore_permissions=True)
			pe.submit()

		mopd = get_mode_of_payment_details(filters)

		mopd_values = next(iter(mopd.values()))
		for mopd_value in mopd_values:
			if mopd_value[0] == "Credit Card":
				cc_init_amount = mopd_value[1]

		# Cancel one Credit Card Payment Entry and check that it is not fetched in mode of payment details.
		payment_entries = frappe.get_all(
			"Payment Entry",
			filters={"mode_of_payment": "Credit Card", "docstatus": 1},
			fields=["name", "docstatus"],
		)
		for payment_entry in payment_entries[:1]:
			pe = frappe.get_doc("Payment Entry", payment_entry.name)
			pe.cancel()

		mopd = get_mode_of_payment_details(filters)
		mopd_values = next(iter(mopd.values()))
		for mopd_value in mopd_values:
			if mopd_value[0] == "Credit Card":
				cc_final_amount = mopd_value[1]

		self.assertTrue(cc_init_amount > cc_final_amount)


def get_filters():
	return {"from_date": "1900-01-01", "to_date": today(), "company": "_Test Company"}


def create_sales_invoice_record(qty=1):
	# return sales invoice doc object
	return frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"customer": frappe.get_doc("Customer", {"customer_name": "Prestiga-Biz"}).name,
			"company": "_Test Company",
			"due_date": today(),
			"posting_date": today(),
			"currency": "INR",
			"taxes_and_charges": "",
			"debit_to": "Debtors - _TC",
			"taxes": [],
			"items": [
				{
					"doctype": "Sales Invoice Item",
					"item_code": frappe.get_doc("Item", {"item_name": "Consulting"}).name,
					"qty": qty,
					"rate": 10000,
					"income_account": "Sales - _TC",
					"cost_center": "Main - _TC",
					"expense_account": "Cost of Goods Sold - _TC",
				}
			],
		}
	)


def create_records():
	if frappe.db.exists("Customer", "Prestiga-Biz"):
		return

	# customer
	frappe.get_doc(
		{
			"customer_group": "_Test Customer Group",
			"customer_name": "Prestiga-Biz",
			"customer_type": "Company",
			"doctype": "Customer",
			"territory": "_Test Territory",
		}
	).insert()

	# item
	item = frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": "Consulting",
			"item_name": "Consulting",
			"item_group": "All Item Groups",
			"company": "_Test Company",
			"is_stock_item": 0,
		}
	).insert()

	# item price
	frappe.get_doc(
		{
			"doctype": "Item Price",
			"price_list": "Standard Selling",
			"item_code": item.item_code,
			"price_list_rate": 10000,
		}
	).insert()
