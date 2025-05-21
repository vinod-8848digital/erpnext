# Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils.file_manager import save_file


class DummyFile:
    def __init__(self, file_name):
        self.file_name = file_name

class TestRemittanceofTDScertificate(FrappeTestCase):
	def setUp(self):
		content = b"Dummy content"
		self.test_file = save_file(
			fname="test_attachment.txt",
			content=content,
			dt="User",
			dn=frappe.session.user,
			folder=None,
			decode=False
		)
		self.test_item = {"file_name": self.test_file.file_name}
		
	def test_get_pan_list_TC_B_187(self):
		files = [
			DummyFile("ABCDE1234F_pan.pdf"),
			DummyFile("XYZ9876543_other.pdf"),
			DummyFile("invalid_file.txt")
		]

		from erpnext.buying.doctype.remittance_of_tds_certificate.remittance_of_tds_certificate import get_pan_list 
		result = get_pan_list(files)

		expected = [
			{"file_name": "ABCDE1234F_pan.pdf", "pan": "ABCDE1234F"},
			{"file_name": "XYZ9876543_other.pdf", "pan": "XYZ9876543"}
		]

		self.assertEqual(result, expected)

	def test_create_attachment_TC_B_188(self):
		from erpnext.buying.doctype.remittance_of_tds_certificate.remittance_of_tds_certificate import create_attachment 
		result = create_attachment(self.test_item)

		self.assertIn("fname", result)
		self.assertIn("fcontent", result)
		self.assertEqual(result["fname"], "test_attachment.txt")
		self.assertEqual(result["fcontent"], b"Dummy content")

	def test_get_emails_and_unrecored_pan_list_TC_B_189(self):
		from erpnext.buying.doctype.remittance_of_tds_certificate.remittance_of_tds_certificate import get_emails_and_unrecored_pan_list

		frappe.get_doc({
			"doctype": "Supplier",
			"supplier_name": "Supplier With Email",
			"pan": "ABCDE1234F",
			"email_id": "supplier@example.com"
		}).insert(ignore_if_duplicate=True)

		frappe.get_doc({
			"doctype": "Supplier",
			"supplier_name": "Supplier Without Email",
			"pan": "DGAPK9160G",
			"email_id": ""
		}).insert(ignore_if_duplicate=True)

		test_data = [
			{"pan": "ABCDE1234F", "file_name": "file1.pdf"}, 
			{"pan": "DGAPK9160G", "file_name": "file2.pdf"},
			{"pan": "DGAPK9160T", "file_name": "file3.pdf"}   
			]


		unrecorded_pan, emails_and_pan_list, pan_without_emails = get_emails_and_unrecored_pan_list(test_data)

		self.assertEqual(len(emails_and_pan_list), 1)
		self.assertEqual(emails_and_pan_list[0]["pan"], "ABCDE1234F")
		self.assertEqual(emails_and_pan_list[0]["status"], "Success")

		self.assertEqual(len(pan_without_emails), 1)
		self.assertEqual(pan_without_emails[0]["pan"], "DGAPK9160G")
		self.assertEqual(pan_without_emails[0]["status"], "Failure")

		self.assertEqual(len(unrecorded_pan), 1)
		self.assertEqual(unrecorded_pan[0]["pan"], "DGAPK9160T")
		self.assertEqual(unrecorded_pan[0]["status"], "Failure")

	def test_get_email_list_TC_B_225(self):
		frappe.get_doc({
			"doctype": "Supplier",
			"supplier_name": "Supplier With Email",
			"pan": "ABCDE1234F",
			"email_id": "email@domain.com"
		}).insert(ignore_if_duplicate=True)

		frappe.get_doc({
			"doctype": "Supplier",
			"supplier_name": "Supplier Without Email",
			"pan": "DGAPK9160G",
			"email_id": ""
		}).insert(ignore_if_duplicate=True)

		doc = frappe.get_doc({
			"doctype": "Your Custom Doctype",
			"some_field": "Some Value"
		}).insert()

		filenames = ["PAN123_certificate.pdf", "PAN456_certificate.pdf", "PAN789_certificate.pdf"]
		for fname in filenames:
			frappe.get_doc({
				"doctype": "File",
				"file_name": fname,
				"attached_to_doctype": doc.doctype,
				"attached_to_name": doc.name,
				"is_private": 1
			}).insert()

		from erpnext.buying.doctype.remittance_of_tds_certificate.remittance_of_tds_certificate import get_email_list, get_pan_list
		import erpnext.buying.doctype.remittance_of_tds_certificate.remittance_of_tds_certificate

		def mock_get_pan_list(certificate_name_list):
			return [
				{"pan": "ABCDE1234F", "file_name": "PAN123_certificate.pdf"},
				{"pan": "DGAPK9160G", "file_name": "PAN456_certificate.pdf"},
				{"pan": "DGAPK9160T", "file_name": "PAN789_certificate.pdf"},
			]

		erpnext.buying.doctype.remittance_of_tds_certificate.remittance_of_tds_certificate.get_pan_list = mock_get_pan_list

		emails_and_pan_list = get_email_list(doc)

		self.assertEqual(len(emails_and_pan_list), 1)
		self.assertEqual(emails_and_pan_list[0]["pan"], "PAN123")

		error_logs = doc.error_logs
		self.assertEqual(len(error_logs), 3)

		statuses = [log.status for log in error_logs]
		self.assertIn("Success", statuses)
		self.assertIn("Failure", statuses)



