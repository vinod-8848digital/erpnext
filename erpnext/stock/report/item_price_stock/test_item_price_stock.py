import frappe
from frappe.tests.utils import FrappeTestCase
from erpnext.stock.report.item_price_stock import item_price_stock
from erpnext.accounts.doctype.pricing_rule.test_pricing_rule import make_item_price


class TestItemPriceStockReport(FrappeTestCase):
	def setUp(self):
		super().setUp()



		self.item_code = "TEST-ITEM-PRICE-STOCK"
		self.hsn_code = "10010010"
		self.brand = "TestBrand"
		self.warehouse = "_Test Warehouse - _TC"
		self.buying_price_list = "Test Buying PL"
		self.selling_price_list = "Test Selling PL"



		if not frappe.db.exists("Company", "_Test Company"):
			frappe.get_doc({
				"doctype": "Company",
				"company_name": "_Test Company",
				"company_type": "Company",
				"default_currency": "INR",
				"country": "India",
				"company_email": "test@example.com",
				"abbr": "_TC"
			}).insert()

		# Create Brand
		if not frappe.db.exists("Brand", self.brand):
			frappe.get_doc({
				"doctype": "Brand",
				"brand": self.brand
			}).insert()

		# Create GST HSN Code
		if not frappe.db.exists("GST HSN Code", self.hsn_code):
			frappe.get_doc({
				"doctype": "GST HSN Code",
				"hsn_code": self.hsn_code,
				"description": "Test HSN Code for automation"
			}).insert()

		# Create Warehouse
		if not frappe.db.exists("Warehouse", self.warehouse):
			frappe.get_doc({
				"doctype": "Warehouse",
				"warehouse_name": self.warehouse,
				"company": "_Test Company"
			}).insert()

		# Create Item
		if not frappe.db.exists("Item", self.item_code):
			frappe.get_doc({
				"doctype": "Item",
				"item_code": self.item_code,
				"item_name": "Test Item for Price Stock",
				"stock_uom": "Nos",
				"is_stock_item": 1,
				"brand": self.brand,
				"gst_hsn_code": self.hsn_code
			}).insert()

		# Create Price Lists
		for price_list_name, buying, selling in [
			(self.buying_price_list, 1, 0),
			(self.selling_price_list, 0, 1)
		]:
			if not frappe.db.exists("Price List", price_list_name):
				frappe.get_doc({
					"doctype": "Price List",
					"price_list_name": price_list_name,
					"buying": buying,
					"selling": selling
				}).insert()

		# Create Item Prices
		if not frappe.db.exists("Item Price", {"item_code": self.item_code, "price_list": self.buying_price_list}):
			self.buying_price_doc = frappe.get_doc({
				"doctype": "Item Price",
				"item_code": self.item_code,
				"price_list": self.buying_price_list,
				"price_list_rate": 75.0,
				"buying": 1
			}).insert()
		else:
			self.buying_price_doc = frappe.get_doc("Item Price", {
				"item_code": self.item_code,
				"price_list": self.buying_price_list
			})

		if not frappe.db.exists("Item Price", {"item_code": self.item_code, "price_list": self.selling_price_list}):
			self.selling_price_doc = frappe.get_doc({
				"doctype": "Item Price",
				"item_code": self.item_code,
				"price_list": self.selling_price_list,
				"price_list_rate": 125.0,
				"selling": 1
			}).insert()
		else:
			self.selling_price_doc = frappe.get_doc("Item Price", {
				"item_code": self.item_code,
				"price_list": self.selling_price_list
			})

		# Create Bin (stock availability)
		if not frappe.db.exists("Bin", {"item_code": self.item_code, "warehouse": self.warehouse}):
			frappe.get_doc({
				"doctype": "Bin",
				"item_code": self.item_code,
				"warehouse": self.warehouse,
				"actual_qty": 30
			}).insert(ignore_permissions=True)

	# Test 1: Execute function end-to-end
	def test_execute_returns_data(self):
		columns, data = item_price_stock.execute({"item_code": self.item_code})
		self.assertTrue(columns)
		self.assertTrue(data)
		self.assertEqual(data[0]["item_code"], self.item_code)

	# Test 2: Columns structure
	def test_get_columns_structure(self):
		columns = item_price_stock.get_columns()
		expected_fields = [
			"item_code", "item_name", "brand", "warehouse",
			"stock_available", "buying_price_list", "buying_rate",
			"selling_price_list", "selling_rate"
		]
		fieldnames = [col["fieldname"] for col in columns]
		for field in expected_fields:
			self.assertIn(field, fieldnames)

	# Test 3: get_data calls the main logic
	def test_get_data_calls_main_logic(self):
		data = item_price_stock.get_data({"item_code": self.item_code}, item_price_stock.get_columns())
		self.assertIsInstance(data, list)
		self.assertGreaterEqual(len(data), 1)

	# Test 4: get_item_price_qty_data function directly
	def test_get_item_price_qty_data_function(self):
		data = item_price_stock.get_item_price_qty_data({"item_code": self.item_code})
		self.assertGreaterEqual(len(data), 1)

		record = data[0]
		self.assertEqual(record["item_code"], self.item_code)
		self.assertEqual(record["stock_available"], 30)
		self.assertEqual(record["buying_price_list"], self.buying_price_list)
		self.assertEqual(record["buying_rate"], 75.0)
		# self.assertEqual(record["selling_price_list"], self.selling_price_list)
		# self.assertEqual(record["selling_rate"], 125.0)

	# Test 5: get_price_map function independently
	def test_get_price_map_functionality(self):
		price_list_names = [self.buying_price_doc.name, self.selling_price_doc.name]

		# Buying map
		buying_map = item_price_stock.get_price_map(price_list_names, buying=1)
		self.assertIn(self.buying_price_doc.name, buying_map)
		self.assertEqual(buying_map[self.buying_price_doc.name]["Buying Price List"], self.buying_price_list)
		self.assertEqual(buying_map[self.buying_price_doc.name]["Buying Rate"], 75.0)

		# Selling map
		selling_map = item_price_stock.get_price_map(price_list_names, selling=1)
		self.assertIn(self.selling_price_doc.name, selling_map)
		self.assertEqual(selling_map[self.selling_price_doc.name]["Selling Price List"], self.selling_price_list)
		self.assertEqual(selling_map[self.selling_price_doc.name]["Selling Rate"], 125.0)

		# Empty input
		empty = item_price_stock.get_price_map([])
		self.assertEqual(empty, {})


