import unittest
import os
import pandas as pd
from context.market_snapshot_builder.ingestion_loader import load_real_ingestion_snapshot
from context.market_snapshot_builder.schemas import BuilderValidationError

class TestRealIngestionSnapshotLoader(unittest.TestCase):

    def setUp(self):
        self.test_dir = os.path.dirname(__file__)
        self.valid_parquet = os.path.join(self.test_dir, "test_valid_ohlcv.parquet")
        self.missing_ts_parquet = os.path.join(self.test_dir, "test_missing_ts.parquet")
        self.negative_price_parquet = os.path.join(self.test_dir, "test_negative_price.parquet")
        self.invalid_bounds_parquet = os.path.join(self.test_dir, "test_invalid_bounds.parquet")
        
        # Valid data
        pd.DataFrame([{
            'timestamp': 1777088176047, 'exchange': 'okx', 'symbol': 'BTC-USDT-SWAP',
            'instrument_type': 'SWAP', 'source': 'okx_ws', 'timeframe': '1m',
            'open': 100.0, 'high': 105.0, 'low': 95.0, 'close': 102.0, 'volume': 10.0,
            'confirm': True
        }]).to_parquet(self.valid_parquet)

        # Missing timestamp
        pd.DataFrame([{
            'open': 100.0, 'high': 105.0, 'low': 95.0, 'close': 102.0, 'volume': 10.0
        }]).to_parquet(self.missing_ts_parquet)

        # Negative price
        pd.DataFrame([{
            'timestamp': 1777088176047,
            'open': -100.0, 'high': 105.0, 'low': 95.0, 'close': 102.0, 'volume': 10.0
        }]).to_parquet(self.negative_price_parquet)

        # Invalid bounds
        pd.DataFrame([{
            'timestamp': 1777088176047,
            'open': 100.0, 'high': 105.0, 'low': 110.0, 'close': 102.0, 'volume': 10.0
        }]).to_parquet(self.invalid_bounds_parquet)

    def tearDown(self):
        for f in [self.valid_parquet, self.missing_ts_parquet, self.negative_price_parquet, self.invalid_bounds_parquet]:
            if os.path.exists(f):
                os.remove(f)

    def test_local_fixture_loads_successfully(self):
        snapshot = load_real_ingestion_snapshot(self.valid_parquet)
        self.assertEqual(snapshot.price, 102.0)
        self.assertEqual(snapshot.asset, "BTC-USDT-SWAP")
        self.assertEqual(snapshot.risk_mode, "Watch only. Confirmation required.")

    def test_missing_timestamp_fails_closed(self):
        with self.assertRaises(BuilderValidationError):
            load_real_ingestion_snapshot(self.missing_ts_parquet)

    def test_negative_price_fails_closed(self):
        with self.assertRaises(BuilderValidationError):
            load_real_ingestion_snapshot(self.negative_price_parquet)

    def test_invalid_ohlcv_bounds_fails_closed(self):
        with self.assertRaises(BuilderValidationError):
            load_real_ingestion_snapshot(self.invalid_bounds_parquet)

if __name__ == '__main__':
    unittest.main()
