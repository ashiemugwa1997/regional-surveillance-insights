import pandas as pd
from django.conf import settings

from surveillance import models

from .base import LoadedDataTestCase

RAW = settings.BASE_DIR / "data" / "raw"


class ETLTests(LoadedDataTestCase):
    def test_row_counts_match_source(self):
        cases = [
            ("countries.csv", models.Country),
            ("population.csv", models.Population),
            ("disease_surveillance.csv", models.DiseaseSurveillance),
            ("outbreaks.csv", models.Outbreak),
            ("laboratory_capacity.csv", models.LaboratoryCapacity),
            ("reporting_metrics.csv", models.ReportingMetric),
            ("workforce.csv", models.Workforce),
            ("funding.csv", models.Funding),
        ]
        for fname, model in cases:
            expected = len(pd.read_csv(RAW / fname))
            self.assertEqual(model.objects.count(), expected, fname)

    def test_quarantine_matches_source_rules(self):
        # The quarantined count is derived from the same rules applied to the source,
        # not a hard-coded number.
        df = pd.read_csv(RAW / "disease_surveillance.csv")
        expected = int(((df["case_fatality_ratio_pct"] > 100) |
                        (df["deaths_reported"] > df["cases_reported"])).sum())
        flagged = models.DiseaseSurveillance.objects.filter(is_valid=False)
        self.assertEqual(flagged.count(), expected)
        self.assertEqual(flagged.filter(quality_notes="").count(), 0)

    def test_missing_values_kept_null(self):
        df = pd.read_csv(RAW / "funding.csv")
        missing = df[df["external_funding_usd"].isna()]
        self.assertGreater(len(missing), 0)  # the source genuinely has gaps
        for _, r in missing.iterrows():
            obj = models.Funding.objects.get(country_id=r["iso3"], year=int(r["year"]))
            self.assertIsNone(obj.external_funding_usd)
