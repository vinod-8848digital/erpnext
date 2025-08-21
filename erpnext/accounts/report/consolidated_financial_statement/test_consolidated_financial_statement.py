import unittest
from unittest.mock import MagicMock
import frappe
from erpnext.accounts.report.consolidated_financial_statement.consolidated_financial_statement import (
    validate_entries
)

class TestConsolidatedFinancialStatement(unittest.TestCase):
    def setUp(self):
        self.key = "1001 - Cash Account"
        self.entry = MagicMock()
        self.entry.account = "Cash Account"

    def test_existing_key_no_changes_TC_ACC_514(self):
        accounts_by_name = {self.key: {"account_name": "Cash Account"}}
        accounts = [{"name": "existing_account"}]
        
        original_accounts_by_name = accounts_by_name.copy()
        original_accounts = accounts.copy()

        validate_entries(self.key, self.entry, accounts_by_name, accounts)

        self.assertEqual(accounts_by_name, original_accounts_by_name)
        self.assertEqual(accounts, original_accounts)