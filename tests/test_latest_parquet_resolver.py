import unittest
import os
import shutil
import tempfile
import pandas as pd
from pathlib import Path

from context.latest_parquet_resolver.resolver import resolve_latest_parquet
from context.latest_parquet_resolver.schemas import ResolverError

class TestLatestParquetResolver(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        
        # Valid older parquet
        self.valid_old_dir = os.path.join(self.test_dir, "source=okx_ws", "symbol=BTC-USDT-SWAP", "date=2026-04-24", "hour=03")
        os.makedirs(self.valid_old_dir, exist_ok=True)
        self.valid_old_path = os.path.join(self.valid_old_dir, "part-old.parquet")
        
        pd.DataFrame([{
            'timestamp': 1777088176047, 'exchange': 'okx', 'symbol': 'BTC-USDT-SWAP',
            'instrument_type': 'SWAP', 'source': 'okx_ws', 'timeframe': '1m',
            'open': 100.0, 'high': 105.0, 'low': 95.0, 'close': 102.0, 'volume': 10.0,
            'confirm': True
        }]).to_parquet(self.valid_old_path)
        
        # Invalid newer parquet (missing OHLCV columns)
        self.invalid_new_dir = os.path.join(self.test_dir, "source=okx_ws", "symbol=BTC-USDT-SWAP", "date=2026-04-25", "hour=04")
        os.makedirs(self.invalid_new_dir, exist_ok=True)
        self.invalid_new_path = os.path.join(self.invalid_new_dir, "part-new-invalid.parquet")
        
        pd.DataFrame([{
            'timestamp': 1777088176047, 'exchange': 'okx', 'symbol': 'BTC-USDT-SWAP'
        }]).to_parquet(self.invalid_new_path)
        
        # Empty parquet
        self.empty_new_dir = os.path.join(self.test_dir, "source=okx_ws", "symbol=BTC-USDT-SWAP", "date=2026-04-25", "hour=05")
        os.makedirs(self.empty_new_dir, exist_ok=True)
        self.empty_new_path = os.path.join(self.empty_new_dir, "part-new-empty.parquet")
        
        pd.DataFrame().to_parquet(self.empty_new_path)
        
        # Valid newer parquet (ETH symbol)
        self.eth_new_dir = os.path.join(self.test_dir, "source=okx_ws", "symbol=ETH-USDT-SWAP", "date=2026-04-25", "hour=05")
        os.makedirs(self.eth_new_dir, exist_ok=True)
        self.eth_new_path = os.path.join(self.eth_new_dir, "part-new-eth.parquet")
        
        pd.DataFrame([{
            'timestamp': 1777088176047, 'exchange': 'okx', 'symbol': 'ETH-USDT-SWAP',
            'instrument_type': 'SWAP', 'source': 'okx_ws', 'timeframe': '1m',
            'open': 100.0, 'high': 105.0, 'low': 95.0, 'close': 102.0, 'volume': 10.0,
            'confirm': True
        }]).to_parquet(self.eth_new_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_resolver_finds_newest_valid_parquet_skipping_invalid(self):
        # Even though there are newer invalid ones, it should skip them and return valid_old
        resolution = resolve_latest_parquet(self.test_dir, symbol_filter="BTC-USDT-SWAP")
        
        self.assertEqual(resolution.resolved_path, self.valid_old_path)
        self.assertEqual(resolution.symbol, "BTC-USDT-SWAP")
        self.assertEqual(resolution.date, "2026-04-24")

    def test_resolver_respects_symbol_filter(self):
        resolution = resolve_latest_parquet(self.test_dir, symbol_filter="ETH-USDT-SWAP")
        self.assertEqual(resolution.resolved_path, self.eth_new_path)
        self.assertEqual(resolution.symbol, "ETH-USDT-SWAP")
        self.assertEqual(resolution.date, "2026-04-25")

    def test_resolver_fails_if_no_valid_exists(self):
        # We delete the valid ones
        os.remove(self.valid_old_path)
        os.remove(self.eth_new_path)
        
        with self.assertRaises(ResolverError):
            resolve_latest_parquet(self.test_dir)

if __name__ == '__main__':
    unittest.main()
