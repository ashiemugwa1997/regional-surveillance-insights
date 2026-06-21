from surveillance import analysis

from .base import LoadedDataTestCase


class AnalysisTests(LoadedDataTestCase):
    def test_support_table_complete_and_bounded(self):
        rows = analysis.support_table()
        self.assertEqual(len(rows), 20)
        for r in rows:
            self.assertIsNotNone(r["support_index"])
            self.assertGreaterEqual(r["support_index"], 0)
            self.assertLessEqual(r["support_index"], 100)

    def test_ranking_is_descending(self):
        rows = analysis.support_table()
        scores = [r["support_index"] for r in rows]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(rows[0]["rank"], 1)

    def test_high_need_cohort_is_sensible(self):
        rows = analysis.support_table()
        high = {r["country_name"] for r in rows if r["tier"] == "High need"}
        # Fragile Sahel states should land in the high-need tier.
        self.assertIn("Niger", high)
        self.assertIn("Chad", high)

    def test_summary_indicators(self):
        s = analysis.summary_indicators()
        self.assertEqual(s["n_countries"], 20)
        self.assertEqual(s["flagged_rows"], 14)
        self.assertEqual(s["total_surveillance_rows"], 700)
