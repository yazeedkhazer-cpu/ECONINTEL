"""Assert the ECONINTEL agreed 32-indicator register and 100-point research allocation."""
from pathlib import Path
import re, json, unittest
ROOT=Path(__file__).resolve().parents[1]
class WeightRegistryTest(unittest.TestCase):
    def test_register(self):
        s=(ROOT/'assets/app.js').read_text()
        a=re.search(r'const LABOR_WEIGHTS=Object\.freeze\((\{[^;]+\})\);',s)
        self.assertIsNotNone(a)
        w=json.loads(a.group(1))
        self.assertEqual(32,len(w))
        self.assertEqual(100,sum(w.values()))
        self.assertNotIn('isman',w)
        self.assertNotIn('isserv',w)
        self.assertEqual(set(w),set(re.findall(r"\{id:'([^']+)'",(ROOT/'assets/seed.js').read_text()))-{'isman','isserv'})
    def test_nav_and_register_page(self):
        self.assertIn('data-page="weights"',(ROOT/'index.html').read_text())
        self.assertIn('weights:renderWeights',(ROOT/'assets/app.js').read_text())
    def test_declared_coverage(self):
        s=(ROOT/'scripts/update_all.py').read_text()
        self.assertIn("'total':32",s)
if __name__=='__main__':unittest.main()
