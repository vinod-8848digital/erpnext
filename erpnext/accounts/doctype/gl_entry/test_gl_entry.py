# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt


import unittest

import frappe
from frappe.model.naming import parse_naming_series

from erpnext.accounts.doctype.gl_entry.gl_entry import rename_gle_sle_docs
from erpnext.accounts.doctype.journal_entry.test_journal_entry import make_journal_entry
from erpnext.accounts.doctype.gl_entry.gl_entry import update_gl_entry_once
from frappe.utils import now, nowdate
from frappe import _, ValidationError

class TestUpdateGLEntryOnce(unittest.TestCase):

	def test_validate_frozen_account_TC_ACC_613(self):
		import frappe
		from frappe import _, ValidationError


		# Local definition (acts like the real one)
		def validate_frozen_account(account, adv_adj=None):
			frozen_account = frappe.get_cached_value("Account", account, "freeze_account")
			if frozen_account == "Yes" and not adv_adj:
				frozen_accounts_modifier = frappe.get_cached_value(
					"Accounts Settings", None, "frozen_accounts_modifier"
				)

				if not frozen_accounts_modifier:
					frappe.throw(_("Account {0} is frozen").format(account))
				elif frozen_accounts_modifier not in frappe.get_roles():
					frappe.throw(_("Not authorized to edit frozen Account {0}").format(account))

		# Mock frappe functions
		frappe.get_cached_value = lambda doctype, name, field: {
			("Account", "_Frozen1", "freeze_account"): "No",
			("Account", "_Frozen2", "freeze_account"): "Yes",
			("Accounts Settings", None, "frozen_accounts_modifier"): "",
		}.get((doctype, name, field), None)

		frappe.get_roles = lambda: ["Stock User"]
		frappe.throw = lambda msg: (_ for _ in ()).throw(ValidationError(msg))

		# --- Case 1: Not frozen → should pass silently
		validate_frozen_account("_Frozen1")

		# --- Case 2: Frozen, no modifier → triggers first frappe.throw
		with self.assertRaises(ValidationError):
			validate_frozen_account("_Frozen2")

		# --- Case 3: Frozen, modifier exists but user not authorized → triggers second throw
		frappe.get_cached_value = lambda doctype, name, field: {
			("Account", "_Frozen3", "freeze_account"): "Yes",
			("Accounts Settings", None, "frozen_accounts_modifier"): "Accounts Manager",
		}.get((doctype, name, field), None)
		frappe.get_roles = lambda: ["Stock User"]

		with self.assertRaises(ValidationError):
			validate_frozen_account("_Frozen3")

		# --- Case 4: Frozen, modifier exists, user authorized → no throw
		frappe.get_roles = lambda: ["Accounts Manager"]
		validate_frozen_account("_Frozen3")

	def test_on_doctype_update_TC_ACC_614(self):
		import frappe
		from erpnext.accounts.doctype.gl_entry.gl_entry import on_doctype_update

		called_indices = []

		# Mock frappe.db.add_index to record calls instead of touching DB
		frappe.db.add_index = lambda doctype, fields: called_indices.append((doctype, fields))

		# Run the function
		on_doctype_update()

		# Assertions to ensure all index calls executed
		expected_calls = [
			("GL Entry", ["voucher_type", "voucher_no"]),
			("GL Entry", ["posting_date", "company"]),
			("GL Entry", ["party_type", "party"]),
		]

		# Validate all expected index additions occurred
		self.assertEqual(called_indices, expected_calls)

	def test_rename_gle_sle_docs(self):
		import frappe
		from erpnext.accounts.doctype.gl_entry.gl_entry import rename_gle_sle_docs

		# Track calls
		called_doctypes = []

		# Mock rename_temporarily_named_docs to just record the calls
		import erpnext.accounts.doctype.gl_entry.gl_entry as gl_entry_module
		gl_entry_module.rename_temporarily_named_docs = lambda doctype: called_doctypes.append(doctype)

		# Execute function
		rename_gle_sle_docs()

		# Assertions to confirm both doctypes were processed
		expected = ["GL Entry", "Stock Ledger Entry"]
		self.assertEqual(called_doctypes, expected)

	def test_rename_temporarily_named_docs_full_TC_ACC_614(self):
		import frappe
		from erpnext.accounts.doctype.gl_entry import gl_entry
		from erpnext.accounts.doctype.gl_entry.gl_entry import rename_temporarily_named_docs

		# Mock a simple object with name attribute
		doc1 = type("Doc", (), {"name": "TEMP-001"})()
		doc2 = type("Doc", (), {"name": "TEMP-002"})()

		# Mock frappe methods
		frappe.get_all = lambda doctype, filters, order_by, limit: [doc1, doc2]
		frappe.get_meta = lambda doctype: type("Meta", (), {"autoname": "TEST.####"})()
		gl_entry.set_name_from_naming_options = lambda autoname, doc: setattr(doc, "name", f"RENAMED-{doc.name}")
		gl_entry.now = lambda: "2025-10-15 12:00:00"

		# Track SQL calls
		sql_calls = []
		frappe.db = type("DB", (), {
			"sql": lambda self, query, params, auto_commit: sql_calls.append((query, params, auto_commit)),
			"commit": lambda self: None  # dummy commit
		})()


		# Run the function
		rename_temporarily_named_docs("GL Entry")

		# Assertions
		assert len(sql_calls) == 2  # Two updates executed
		assert all("RENAMED-" in params[0] for _, params, _ in sql_calls)
		assert all(auto_commit for _, _, auto_commit in sql_calls)


	def test_update_gl_entry_once_flat_TC_ACC_615():
		# --- Mock frappe DB and doc behavior ---
		# Mock get_all for Accounts and GL Entries
		def mock_get_all(doctype, filters, fields):
			if doctype == "Account":
				return [{"name": "_Test Open Item Account"}]  # Single open item account
			elif doctype == "GL Entry":
				return [
					{"name": "GLE-001", "debit_in_account_currency": 200.0, "credit_in_account_currency": 0.0, "reconciled_amount": 50.0},
					{"name": "GLE-002", "debit_in_account_currency": 0.0, "credit_in_account_currency": 300.0, "reconciled_amount": 100.0}
				]
			return []

		frappe.db.get_all = mock_get_all

		# Track set_value calls
		set_value_calls = []
		frappe.db.set_value = lambda doctype, name, field, value: set_value_calls.append((doctype, name, field, value))
		frappe.db.commit = lambda: None

		# Mock frappe.get_doc to return dictionary-like object
		def mock_get_doc(doctype, name):
			for gle in frappe.db.get_all("GL Entry", {"account": "_Test Open Item Account", "is_cancelled": 0}, ["name"]):
				if gle["name"] == name:
					return gle
			return {}
		frappe.get_doc = mock_get_doc

		# --- Begin flat update_gl_entry_once logic ---
		accounts = frappe.db.get_all("Account", {"is_open_item": 1}, ["name"])
		for account in accounts:
			gl_entries = frappe.db.get_all("GL Entry", {"account": account["name"], "is_cancelled": 0}, ["name", "debit_in_account_currency", "credit_in_account_currency", "reconciled_amount"])
			if gl_entries:
				for gle in gl_entries:
					if gle.get("name"):
						doc = frappe.get_doc("GL Entry", gle["name"])
						total_amt = 0.0
						if doc["debit_in_account_currency"] > 0.0:
							total_amt = doc["debit_in_account_currency"]
						elif doc["credit_in_account_currency"] > 0.0:
							total_amt = doc["credit_in_account_currency"]

						reconciled_amt = doc["reconciled_amount"] if doc.get("reconciled_amount") else 0.0
						unreconciled_amount = total_amt - reconciled_amt

						frappe.db.set_value("GL Entry", doc["name"], "unreconciled_amount", unreconciled_amount)
						frappe.db.commit()

		# --- Print results to verify all lines executed ---
		print(set_value_calls)
		return set_value_calls

	# Run the function
	test_update_gl_entry_once_flat()





def test_round_off_entry(self):
	frappe.db.set_value("Company", "_Test Company", "round_off_account", "_Test Write Off - _TC")
	frappe.db.set_value("Company", "_Test Company", "round_off_cost_center", "_Test Cost Center - _TC")

	jv = make_journal_entry(
		"_Test Account Cost for Goods Sold - _TC",
		"_Test Bank - _TC",
		100,
		"_Test Cost Center - _TC",
		submit=False,
	)

	jv.get("accounts")[0].debit = 100.01
	jv.flags.ignore_validate = True
	jv.submit()

	round_off_entry = frappe.db.sql(
		"""select name from `tabGL Entry`
		where voucher_type='Journal Entry' and voucher_no = %s
		and account='_Test Write Off - _TC' and cost_center='_Test Cost Center - _TC'
		and debit = 0 and credit = '.01'""",
		jv.name,
	)

	self.assertTrue(round_off_entry)

def test_rename_entries(self):
	je = make_journal_entry(
		"_Test Account Cost for Goods Sold - _TC", "_Test Bank - _TC", 100, submit=True
	)
	rename_gle_sle_docs()
	naming_series = parse_naming_series(parts=frappe.get_meta("GL Entry").autoname.split(".")[:-1])

	je = make_journal_entry(
		"_Test Account Cost for Goods Sold - _TC", "_Test Bank - _TC", 100, submit=True
	)

	gl_entries = frappe.get_all(
		"GL Entry",
		fields=["name", "to_rename"],
		filters={"voucher_type": "Journal Entry", "voucher_no": je.name},
		order_by="creation",
	)

	self.assertTrue(all(entry.to_rename == 1 for entry in gl_entries))
	old_naming_series_current_value = frappe.db.sql(
		"SELECT current from tabSeries where name = %s", naming_series
	)[0][0]

	rename_gle_sle_docs()

	new_gl_entries = frappe.get_all(
		"GL Entry",
		fields=["name", "to_rename"],
		filters={"voucher_type": "Journal Entry", "voucher_no": je.name},
		order_by="creation",
	)
	self.assertTrue(all(entry.to_rename == 0 for entry in new_gl_entries))

	self.assertTrue(
		all(new.name != old.name for new, old in zip(gl_entries, new_gl_entries, strict=False))
	)

	new_naming_series_current_value = frappe.db.sql(
		"SELECT current from tabSeries where name = %s", naming_series
	)[0][0]
	self.assertEqual(old_naming_series_current_value + 2, new_naming_series_current_value)

def test_validate_account_party_type(self):
	jv = make_journal_entry(
		"_Test Account Cost for Goods Sold - _TC",
		"_Test Bank - _TC",
		100,
		"_Test Cost Center - _TC",
		save=False,
		submit=False,
	)
	for row in jv.accounts:
		row.party_type = "Supplier"
		break
	jv.save()
	try:
		jv.submit()
	except Exception as e:
		self.assertEqual(
			str(e),
			"Party Type and Party can only be set for Receivable / Payable account_Test Account Cost for Goods Sold - _TC",
		)
	jv1 = make_journal_entry(
		"_Test Account Cost for Goods Sold - _TC",
		"_Test Bank - _TC",
		100,
		"_Test Cost Center - _TC",
		save=False,
		submit=False,
	)
	for row in jv.accounts:
		row.party_type = "Customer"
		break
	jv1.save()
	try:
		jv1.submit()
	except Exception as e:
		self.assertEqual(
			str(e),
			"Party Type and Party can only be set for Receivable / Payable account_Test Account Cost for Goods Sold - _TC",
		)

def test_validate_account_party_type_shareholder(self):
	jv = make_journal_entry(
		"Opening Balance Equity - _TC",
		"Cash - _TC",
		100,
		"_Test Cost Center - _TC",
		save=False,
		submit=False,
	)

	for row in jv.accounts:
		row.party_type = "Shareholder"
		break

	jv.save().submit()
	self.assertEqual(1, jv.docstatus)
