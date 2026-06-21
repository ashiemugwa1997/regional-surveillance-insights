from django.urls import reverse

from .base import LoadedDataTestCase


class ViewTests(LoadedDataTestCase):
    def test_pages_return_200(self):
        for name in ("surveillance:dashboard", "surveillance:support",
                     "surveillance:data_table"):
            resp = self.client.get(reverse(name))
            self.assertEqual(resp.status_code, 200, name)

    def test_data_table_filters(self):
        resp = self.client.get(
            reverse("surveillance:data_table"), {"year": "2025", "country": "NGA"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Nigeria")
