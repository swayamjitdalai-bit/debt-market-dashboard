import unittest
from unittest.mock import patch
from app import report


class TenorSeriesTests(unittest.TestCase):
    def test_dates_without_instrument_do_not_shift_later_yields(self):
        trade = {'amount_cr': 25}
        def trades(conn, date, instrument, market):
            return [trade] if date == '2026-10-21' else []
        def summary(rows):
            return [{'tenor_label': '12 Months', 'weighted_avg': 6.7,
                     'low': 6.7, 'high': 6.7, 'volume_cr': 25}] if rows else []
        with patch.object(report.db, 'trade_dates', return_value=['2026-10-21', '2026-10-20']), \
             patch.object(report.db, 'trades', side_effect=trades), \
             patch.object(report.derive, 'tenor_summary', side_effect=summary):
            result = report.tenor_series(None, 'CP', 30, '2026-10-21')
        self.assertEqual(result['dates'], ['2026-10-20', '2026-10-21'])
        self.assertEqual([p['wavg'] for p in result['tenors']['12 Months']], [None, 6.7])
        for values in result['tenors'].values():
            self.assertEqual([p['date'] for p in values], result['dates'])
        self.assertEqual(len(result['volume']), len(result['dates']))
