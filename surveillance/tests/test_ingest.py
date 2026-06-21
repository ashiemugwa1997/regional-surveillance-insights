import io

import pandas as pd
from openpyxl import Workbook

from surveillance import ingest, models

from .base import LoadedDataTestCase


class IngestTests(LoadedDataTestCase):
    def test_existing_row_updated_not_duplicated(self):
        rm = models.ReportingMetric.objects.first()
        before = models.ReportingMetric.objects.count()
        df = pd.DataFrame([{"iso3": rm.country_id, "year": rm.year, "timeliness_pct": 12.3,
                            "completeness_pct": 50.0, "idsr_weekly_compliance_pct": 60.0}])
        rep = ingest.ingest("reporting_metrics", df)
        self.assertEqual(rep["existing"], 1)
        self.assertEqual(rep["created"], 0)
        self.assertEqual(models.ReportingMetric.objects.count(), before)  # no duplicate
        self.assertAlmostEqual(models.ReportingMetric.objects.get(
            country_id=rm.country_id, year=rm.year).timeliness_pct, 12.3)

    def test_new_row_created(self):
        c = models.Country.objects.first()
        df = pd.DataFrame([{"iso3": c.iso3, "year": 2099, "disease": "TestPox",
                            "cases_reported": 10, "deaths_reported": 1,
                            "attack_rate_per_100k": 1.0, "case_fatality_ratio_pct": 10.0}])
        rep = ingest.ingest("disease_surveillance", df)
        self.assertEqual(rep["created"], 1)
        self.assertTrue(models.DiseaseSurveillance.objects.filter(
            country_id=c.iso3, year=2099, disease="TestPox").exists())

    def test_quality_flag_on_upload(self):
        ds = models.DiseaseSurveillance.objects.first()
        df = pd.DataFrame([{"iso3": ds.country_id, "year": ds.year, "disease": ds.disease,
                            "cases_reported": 100, "deaths_reported": 5,
                            "attack_rate_per_100k": 1.0, "case_fatality_ratio_pct": 150.0}])
        rep = ingest.ingest("disease_surveillance", df)
        self.assertEqual(rep["flagged"], 1)
        row = models.DiseaseSurveillance.objects.get(
            country_id=ds.country_id, year=ds.year, disease=ds.disease)
        self.assertFalse(row.is_valid)

    def test_unknown_country_is_reported(self):
        bad = "QQQ"
        self.assertFalse(models.Country.objects.filter(iso3=bad).exists())
        df = pd.DataFrame([{"iso3": bad, "year": 2025, "timeliness_pct": 1.0,
                            "completeness_pct": 1.0, "idsr_weekly_compliance_pct": 1.0}])
        rep = ingest.ingest("reporting_metrics", df)
        self.assertEqual(len(rep["errors"]), 1)
        self.assertEqual(rep["created"] + rep["existing"], 0)

    def test_read_table_autodetects_csv_and_xlsx(self):
        c = models.Country.objects.first()
        # CSV content with a non-csv filename -> detected by content, not extension.
        csv_buf = io.BytesIO(f"iso3,year,timeliness_pct\n{c.iso3},2025,80\n".encode())
        csv_buf.name = "mystery.bin"
        self.assertEqual(len(ingest.read_table(csv_buf)), 1)

        wb = Workbook()
        ws = wb.active
        ws.append(["iso3", "year", "timeliness_pct"])
        ws.append([c.iso3, 2025, 80])
        xlsx_buf = io.BytesIO()
        wb.save(xlsx_buf)
        xlsx_buf.seek(0)
        xlsx_buf.name = "mystery.bin"
        self.assertEqual(len(ingest.read_table(xlsx_buf)), 1)
