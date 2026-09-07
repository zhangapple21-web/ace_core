import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.stock_data_reliability import _fresh_probe, _normalize_quote


def test_pytdx_single_digit_servertime_is_normalized_to_parseable_iso_timestamp():
    fields = _normalize_quote(
        {"price": 9.13, "last_close": 9.08, "vol": 100, "servertime": "9:32:21.570"}
    )

    assert "T09:32:21.570+08:00" in fields["time"]
    assert datetime.fromisoformat(fields["time"]).hour == 9
    assert _fresh_probe({"freshness_at": fields["time"], "started_at": fields["time"]}) is True


