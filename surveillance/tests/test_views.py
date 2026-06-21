from django.urls import reverse

from surveillance import models

from .base import LoadedDataTestCase


class ViewTests(LoadedDataTestCase):
    def test_pages_return_200(self):
        for name in ("surveillance:dashboard", "surveillance:support",
                     "surveillance:data_table", "surveillance:map",
                     "surveillance:data_quality", "surveillance:upload"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

    def test_data_table_filters(self):
        rm = models.ReportingMetric.objects.select_related("country").first()
        resp = self.client.get(reverse("surveillance:data_table"),
                               {"year": str(rm.year), "country": rm.country_id})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, rm.country.country_name)

    def test_country_detail_page(self):
        c = models.Country.objects.first()
        resp = self.client.get(reverse("surveillance:country_detail", args=[c.iso3]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, c.country_name)

    def test_country_detail_unknown_404(self):
        bad = "QQQ"
        self.assertFalse(models.Country.objects.filter(iso3=bad).exists())
        resp = self.client.get(reverse("surveillance:country_detail", args=[bad]))
        self.assertEqual(resp.status_code, 404)

    def test_exports(self):
        csv = self.client.get(reverse("surveillance:export_support", args=["csv"]))
        self.assertEqual(csv.status_code, 200)
        self.assertEqual(csv["Content-Type"], "text/csv")
        xlsx = self.client.get(reverse("surveillance:export_data", args=["xlsx"]))
        self.assertEqual(xlsx.status_code, 200)
        self.assertIn("spreadsheetml", xlsx["Content-Type"])
