import unittest
from unittest.mock import patch, MagicMock
from datetime import date
import types

import frappe
import available_batch_report  # assuming your file is named available_batch_report.py


class TestAvailableBatchReport(unittest.TestCase):
    def setUp(self):
        # Setup common filters
        self.filters = types.SimpleNamespace(
            item_code=None,
            batch_no=None,
            to_date=date.today(),
            include_expired_batches=False,
            warehouse=None,
            warehouse_type=None,
            show_item_name=False,
        )

    @patch('available_batch_report.get_data')
    @patch('available_batch_report.get_columns')
    def test_execute(self, mock_get_columns, mock_get_data):
        mock_get_data.return_value = ['data']
        mock_get_columns.return_value = ['columns']

        columns, data = available_batch_report.execute(self.filters)

        mock_get_data.assert_called_once_with(self.filters)
        mock_get_columns.assert_called_once_with(self.filters)
        self.assertEqual(columns, ['columns'])
        self.assertEqual(data, ['data'])

    def test_get_columns_with_and_without_item_name(self):
        # Without show_item_name
        filters = types.SimpleNamespace(show_item_name=False)
        columns = available_batch_report.get_columns(filters)
        self.assertTrue(any(col['fieldname'] == 'item_code' for col in columns))
        self.assertFalse(any(col['fieldname'] == 'item_name' for col in columns))

        # With show_item_name
        filters = types.SimpleNamespace(show_item_name=True)
        columns = available_batch_report.get_columns(filters)
        self.assertTrue(any(col['fieldname'] == 'item_name' for col in columns))

    def test_parse_batchwise_data(self):
        # balance_qty == 0 should be skipped
        batchwise_data = {
            ('item1', 'warehouse1', 'batch1'): types.SimpleNamespace(balance_qty=0),
            ('item2', 'warehouse1', 'batch2'): types.SimpleNamespace(balance_qty=10),
        }
        result = available_batch_report.parse_batchwise_data(batchwise_data)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].balance_qty, 10)

    @patch('available_batch_report.frappe.qb.DocType')
    @patch('available_batch_report.get_query_based_on_filters')
    def test_get_batchwise_data_from_stock_ledger(self, mock_get_query, mock_doctype):
        filters = types.SimpleNamespace()
        # Mock table and batch
        mock_table = MagicMock()
        mock_batch = MagicMock()
        mock_doctype.side_effect = [mock_table, mock_batch]

        # Mock query
        mock_query = MagicMock()
        mock_query.run.return_value = [
            {'item_code': 'item1', 'warehouse': 'warehouse1', 'batch_no': 'batch1', 'expiry_date': None, 'balance_qty': 10}
        ]
        mock_get_query.return_value = mock_query

        data = available_batch_report.get_batchwise_data_from_stock_ledger(filters)

        self.assertIn(('item1', 'warehouse1', 'batch1'), data)
        self.assertEqual(data[('item1', 'warehouse1', 'batch1')]['balance_qty'], 10)

    @patch('available_batch_report.frappe.qb.DocType')
    @patch('available_batch_report.get_query_based_on_filters')
    @patch('available_batch_report.flt', side_effect=lambda x: x)
    def test_get_batchwise_data_from_serial_batch_bundle(self, mock_flt, mock_get_query, mock_doctype):
        batchwise_data = {
            ('item1', 'warehouse1', 'batch1'): types.SimpleNamespace(balance_qty=5),
        }
        filters = types.SimpleNamespace()
        mock_table = MagicMock()
        mock_ch_table = MagicMock()
        mock_batch = MagicMock()
        mock_doctype.side_effect = [mock_table, mock_ch_table, mock_batch]

        mock_query = MagicMock()
        # Two entries: one matching existing key and one new key
        mock_query.run.return_value = [
            {'item_code': 'item1', 'warehouse': 'warehouse1', 'batch_no': 'batch1', 'expiry_date': None, 'balance_qty': 10},
            {'item_code': 'item2', 'warehouse': 'warehouse2', 'batch_no': 'batch2', 'expiry_date': None, 'balance_qty': 15},
        ]
        mock_get_query.return_value = mock_query

        result = available_batch_report.get_batchwise_data_from_serial_batch_bundle(batchwise_data, filters)

        self.assertEqual(result[('item1', 'warehouse1', 'batch1')].balance_qty, 15)  # 5 + 10
        self.assertIn(('item2', 'warehouse2', 'batch2'), result)
        self.assertEqual(result[('item2', 'warehouse2', 'batch2')].balance_qty, 15)

    @patch('available_batch_report.frappe.db.get_value')
    @patch('available_batch_report.frappe.get_all')
    def test_get_query_based_on_filters(self, mock_get_all, mock_get_value):
        # Setup mock filters
        filters = types.SimpleNamespace(
            item_code='item1',
            batch_no='batch1',
            to_date=date.today(),
            include_expired_batches=False,
            warehouse='WH1',
            warehouse_type=None,
            show_item_name=True,
        )

        # Mock query object with method chaining
        class QueryMock:
            def __init__(self):
                self.calls = []

            def where(self, *args):
                self.calls.append(('where', args))
                return self

            def select(self, *args):
                self.calls.append(('select', args))
                return self

        query = QueryMock()
        batch = MagicMock()
        table = MagicMock()

        # Mock warehouse lft, rgt values
        mock_get_value.return_value = (1, 10)
        mock_get_all.return_value = ['WH1', 'WH2']

        new_query = available_batch_report.get_query_based_on_filters(query, batch, table, filters)

        self.assertIs(new_query, query)
        # Check that where and select were called
        where_calls = [call for call in query.calls if call[0] == 'where']
        select_calls = [call for call in query.calls if call[0] == 'select']
        self.assertTrue(where_calls)
        self.assertTrue(select_calls)

    @patch('available_batch_report.get_batchwise_data_from_stock_ledger')
    @patch('available_batch_report.get_batchwise_data_from_serial_batch_bundle')
    @patch('available_batch_report.parse_batchwise_data')
    def test_get_data(self, mock_parse, mock_serial, mock_stock):
        filters = types.SimpleNamespace()
        mock_stock.return_value = {'key': 'stock'}
        mock_serial.return_value = {'key': 'serial'}
        mock_parse.return_value = ['parsed']

        result = available_batch_report.get_data(filters)

        mock_stock.assert_called_once_with(filters)
        mock_serial.assert_called_once_with({'key': 'stock'}, filters)
        mock_parse.assert_called_once_with({'key': 'serial'})
        self.assertEqual(result, ['parsed'])


if __name__ == "__main__":
    unittest.main()
