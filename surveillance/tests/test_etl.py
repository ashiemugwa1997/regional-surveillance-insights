from surveillance import models

from .base import LoadedDataTestCase


class ETLTests(LoadedDataTestCase):
    def test_reference_and_panel_counts(self):
        self.assertEqual(models.Country.objects.count(), 20)
        for m in (models.Population, models.Funding, models.Workforce,
                  models.LaboratoryCapacity, models.ReportingMetric):
            self.assertEqual(m.objects.count(), 100)
        self.assertEqual(models.Outbreak.objects.count(), 386)

    def test_quarantine_flags_impossible_rows(self):
        # 14 surveillance rows are impossible/contradictory (CFR>100 / deaths>cases).
        invalid = models.DiseaseSurveillance.objects.filter(is_valid=False)
        self.assertEqual(invalid.count(), 14)
        # Every flagged row carries a reason.
        self.assertEqual(invalid.filter(quality_notes="").count(), 0)

    def test_missing_values_kept_null_not_fabricated(self):
        # Missing funding components stay NULL rather than being imputed.
        self.assertTrue(
            models.Funding.objects.filter(external_funding_usd__isnull=True).exists()
        )
