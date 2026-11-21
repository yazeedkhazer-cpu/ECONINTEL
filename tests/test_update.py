"""Tests use synthetic BLS-shaped fixtures. They are NOT market data."""
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import update_bls as b


def synthetic_payload(month_count=22, drop=None):
    drop = set(drop or [])
    series = []
    for name, code in b.SERIES.items():
        if name in drop:
            continue
        rows = []
        for i in range(month_count):
            y = 2025 + i // 12
            month = 1 + i % 12
            val = {
                'nfp_level': 150000 + 120 * i,
                'private_level': 123000 + 105 * i,
                'temp_level': 2500 + i,
                'unrate': 4.1 + i / 200,
                'u6': 7.1 + i / 100,
                'part': 62.3,
                'emratio': 60,
                'primeage': 84,
                'unemployed_level': 7000 + 10 * i,
                'wage_level': 36 + i * 0.10,
                'hours': 34.4,
                'jolts': 7500 + 30 * i,
                'hire': 3.4,
                'quits': 2.1,
                'layoff': 1,
                'longterm': 1900,
                'parttime': 4700,
            }[name]
            rows.append({'year': str(y), 'period': f'M{month:02d}', 'value': f'{val:,}'})
        series.append({'seriesID': code, 'data': rows})
    return {'status': 'REQUEST_SUCCEEDED', 'Results': {'series': series}}


class BLSUpdateTests(unittest.TestCase):
    def test_monthly_and_yearly_changes(self):
        parsed = b.parse_payload(synthetic_payload(22))
        result = b.construct(parsed, '2026-11-17T15:00:00+00:00')['metrics']
        self.assertEqual(result['nfp']['value'], 120)
        self.assertEqual(result['temp']['value'], 1)
        self.assertEqual(result['nfp']['date'], '2026-10')  # synthetic final observation
        self.assertEqual(result['jolts']['value'], round((7500 + 30*21)/1000, 5))
        self.assertEqual(result['beveridge']['date'], result['jolts']['date'])
        self.assertAlmostEqual(result['beveridge']['value'], (7500+30*21)/(7000+10*21), places=4)
        self.assertAlmostEqual(result['wage_mom']['value'], 100*((36+21*.1)/(36+20*.1)-1), places=4)
        self.assertTrue(len(result['wage']['history']) == 10)

    def test_missing_previous_month_does_not_fill_gap(self):
        vals = [['2026-07', 100], ['2026-09', 140], ['2026-10', 141]]
        self.assertEqual(b.consecutive_change(vals), [['2026-10', 1]])

    def test_incomplete_payload_is_rejected(self):
        parsed = b.parse_payload(synthetic_payload(drop=['nfp_level']))
        with self.assertRaisesRegex(ValueError, 'missing required'):
            b.construct(parsed, '2026-11-17T15:00:00+00:00')

    def test_failed_api_does_not_claim_success(self):
        with self.assertRaises(ValueError):
            b.parse_payload({'status': 'REQUEST_FAILED', 'message': ['limit exceeded']})

    def test_refuse_future_reference(self):
        parsed = b.parse_payload(synthetic_payload(month_count=24))
        with self.assertRaisesRegex(ValueError, 'future'):
            b.construct(parsed, '2026-11-17T15:00:00+00:00')

    def test_refuse_obsolete_release(self):
        parsed = b.parse_payload(synthetic_payload(month_count=4))
        with self.assertRaisesRegex(ValueError, 'three months old'):
            b.construct(parsed, '2026-11-17T15:00:00+00:00')


if __name__ == '__main__':
    unittest.main()
