from typing import Dict, Any, Optional

class ParquetResolution:
    def __init__(self, 
                 resolved_path: str,
                 source: Optional[str],
                 symbol: Optional[str],
                 date: Optional[str],
                 hour: Optional[str],
                 timestamp_found: str):
        self.resolved_path = resolved_path
        self.source = source
        self.symbol = symbol
        self.date = date
        self.hour = hour
        self.timestamp_found = timestamp_found

    def to_dict(self) -> Dict[str, Any]:
        return {
            "resolved_path": self.resolved_path,
            "source": self.source,
            "symbol": self.symbol,
            "date": self.date,
            "hour": self.hour,
            "timestamp_found": self.timestamp_found
        }

class ResolverError(Exception):
    pass
