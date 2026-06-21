from surveillance import analysis, models

from .base import LoadedDataTestCase


class AnalysisTests(LoadedDataTestCase):
    def test_support_table_complete_and_bounded(self):
        rows = analysis.support_table()
        self.assertEqual(len(rows), models.Country.objects.count())
        for r in rows:
            self.assertIsNotNone(r["support_index"])
            self.assertGreaterEqual(r["support_index"], 0)
            self.assertLessEqual(r["support_index"], 100)

    def test_ranking_is_descending(self):
        rows = analysis.support_table()
        scores = [r["support_index"] for r in rows]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(rows[0]["rank"], 1)

    def test_tiers_are_monotonic(self):
        # High-need countries should always score at or above low-need ones,
        # whichever countries they happen to be.
        rows = analysis.support_table()
        high = [r["support_index"] for r in rows if r["tier"] == "High need"]
        low = [r["support_index"] for r in rows if r["tier"] == "Low need"]
        self.assertTrue(high and low)
        self.assertGreaterEqual(min(high), max(low))

    def test_summary_matches_db(self):
        s = analysis.summary_indicators()
        self.assertEqual(s["n_countries"], models.Country.objects.count())
        self.assertEqual(s["total_surveillance_rows"],
                         models.DiseaseSurveillance.objects.count())
        self.assertEqual(s["flagged_rows"],
                         models.DiseaseSurveillance.objects.filter(is_valid=False).count())
