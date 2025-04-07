# Copyright (c) 2024, VINOD GAJJALA and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate


class PaymentReconciliationRecord(Document):
	def on_submit(self):
		self.create_payment_ledger_entries()
		
	def on_cancel(self):
		frappe.throw(_("Cancelling records is not allowed."))

	def create_payment_ledger_entries(self):
		"""Create Payment Ledger Entries for each allocation"""
		for allocation in self.allocation:
			if allocation.unreconcile:
				continue
				
			account_type = "Receivable" if self.party_type == "Customer" else "Payable"
			
			self.create_payment_ledger_entry(
				accounting_entry="Credit" if account_type == "Receivable" else "Debit",
				party_type=self.party_type,
				party=self.party,
				amount=abs(flt(allocation.allocated_amount)),
				account=self.receivable__payable_account,
				reference_type=allocation.reference_type,
				reference_name=allocation.reference_name,
				against_voucher_type=allocation.invoice_type,
				against_voucher_no=allocation.invoice_number,
				cost_center=allocation.cost_center
			)

	def create_payment_ledger_entry(self, **kwargs):
		"""Create a new Payment Ledger Entry"""
		ple = frappe.new_doc("Payment Ledger Entry")
		ple.posting_date = self.clearing_date or nowdate()
		ple.company = self.company
		ple.account_type = "Receivable" if self.party_type == "Customer" else "Payable"
		ple.account = kwargs.get("account")
		ple.party_type = kwargs.get("party_type")
		ple.party = kwargs.get("party")
		ple.cost_center = kwargs.get("cost_center")
			
		ple.voucher_type =kwargs.get('reference_type')
		ple.voucher_no = kwargs.get('reference_name')
		ple.against_voucher_type = kwargs.get("against_voucher_type")
		ple.against_voucher_no = kwargs.get("against_voucher_no")
		ple.amount = kwargs.get("amount")
		
		ple.remarks = f"Against {kwargs.get('against_voucher_type')} {kwargs.get('against_voucher_no')}"
		
		ple.flags.ignore_permissions = True
		ple.submit()