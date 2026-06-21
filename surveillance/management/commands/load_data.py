# ETL: read CSVs -> validate/flag -> coerce types -> bulk insert into MySQL.
# Cleaning policy: keep missing values as NULL (never fabricate), and load-but-flag
# impossible rows (CFR>100, deaths>cases) instead of dropping them. Idempotent:
# clears tables first. Run: python manage.py load_data [--data-dir DIR]

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from surveillance import models

logger = logging.getLogger(__name__)


def clean(value):
    """Convert pandas NaN/NaT to None so MySQL stores a real NULL."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if pd.isna(value):
        return None
    return value


def as_int(value):
    value = clean(value)
    return None if value is None else int(round(float(value)))


def as_float(value):
    value = clean(value)
    return None if value is None else float(value)


class Command(BaseCommand):
    help = "Load the regional surveillance CSV dataset into the database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--data-dir",
            default=str(settings.BASE_DIR / "data" / "raw"),
            help="Directory containing the source CSV files.",
        )

    def handle(self, *args, **options):
        data_dir = Path(options["data_dir"])
        if not data_dir.exists():
            self.stderr.write(self.style.ERROR(f"Data dir not found: {data_dir}"))
            return

        self.stdout.write(self.style.MIGRATE_HEADING(f"Loading from {data_dir}"))

        with transaction.atomic():
            self._flush()
            self._load_countries(data_dir)
            self._load_population(data_dir)
            self._load_disease_surveillance(data_dir)
            self._load_outbreaks(data_dir)
            self._load_laboratory(data_dir)
            self._load_reporting(data_dir)
            self._load_workforce(data_dir)
            self._load_funding(data_dir)

        self.stdout.write(self.style.SUCCESS("\nETL complete."))
        self._summary()

    # ------------------------------------------------------------------ utils
    def _flush(self):
        # Order matters only loosely thanks to CASCADE, but be explicit.
        for model in (
            models.Population, models.DiseaseSurveillance, models.Outbreak,
            models.LaboratoryCapacity, models.ReportingMetric, models.Workforce,
            models.Funding, models.Country,
        ):
            model.objects.all().delete()

    def _ok(self, name, n):
        self.stdout.write(f"  {name:<22} {n:>5} rows")

    # ----------------------------------------------------------------- loaders
    def _load_countries(self, d: Path):
        df = pd.read_csv(d / "countries.csv")
        objs = [
            models.Country(
                iso3=r.iso3,
                country_name=r.country_name,
                afro_subregion=r.afro_subregion,
                latitude=as_float(r.latitude),
                longitude=as_float(r.longitude),
                priority_country=as_int(r.priority_country),
            )
            for r in df.itertuples(index=False)
        ]
        models.Country.objects.bulk_create(objs)
        self._ok("countries", len(objs))

    def _load_population(self, d: Path):
        df = pd.read_csv(d / "population.csv")
        objs = [
            models.Population(
                country_id=r.iso3, year=as_int(r.year),
                total_population=as_int(r.total_population),
                under5_population=as_int(r.under5_population),
                urban_population_pct=as_float(r.urban_population_pct),
            )
            for r in df.itertuples(index=False)
        ]
        models.Population.objects.bulk_create(objs)
        self._ok("population", len(objs))

    def _load_disease_surveillance(self, d: Path):
        df = pd.read_csv(d / "disease_surveillance.csv")
        objs = []
        flagged = 0
        for r in df.itertuples(index=False):
            cases = as_int(r.cases_reported)
            deaths = as_int(r.deaths_reported)
            cfr = as_float(r.case_fatality_ratio_pct)

            notes = []
            if cfr is not None and cfr > 100:
                notes.append("CFR>100 (impossible)")
            if cases is not None and deaths is not None and deaths > cases:
                notes.append("deaths>cases (contradictory)")
            is_valid = not notes
            if not is_valid:
                flagged += 1

            objs.append(models.DiseaseSurveillance(
                country_id=r.iso3, year=as_int(r.year), disease=r.disease,
                cases_reported=cases, deaths_reported=deaths,
                attack_rate_per_100k=as_float(r.attack_rate_per_100k),
                case_fatality_ratio_pct=cfr,
                is_valid=is_valid, quality_notes="; ".join(notes),
            ))
        models.DiseaseSurveillance.objects.bulk_create(objs)
        self._ok("disease_surveillance", len(objs))
        self.stdout.write(self.style.WARNING(
            f"    -> flagged {flagged} invalid rows (quarantined, not dropped)"
        ))

    def _load_outbreaks(self, d: Path):
        df = pd.read_csv(d / "outbreaks.csv")
        objs = [
            models.Outbreak(
                outbreak_id=r.outbreak_id, country_id=r.iso3, year=as_int(r.year),
                disease=r.disease,
                start_date=clean(pd.to_datetime(r.start_date, errors="coerce")),
                duration_days=as_int(r.duration_days),
                time_to_detection_days=as_int(r.time_to_detection_days),
                cases=as_int(r.cases), deaths=as_int(r.deaths),
            )
            for r in df.itertuples(index=False)
        ]
        models.Outbreak.objects.bulk_create(objs)
        self._ok("outbreaks", len(objs))

    def _load_laboratory(self, d: Path):
        df = pd.read_csv(d / "laboratory_capacity.csv")
        objs = [
            models.LaboratoryCapacity(
                country_id=r.iso3, year=as_int(r.year),
                total_public_labs=as_int(r.total_public_labs),
                labs_iso15189_accredited=as_int(r.labs_iso15189_accredited),
                iso15189_accreditation_pct=as_float(r.iso15189_accreditation_pct),
                avg_turnaround_time_days=as_float(r.avg_turnaround_time_days),
                diagnostic_tests_per_100k=as_float(r.diagnostic_tests_per_100k),
            )
            for r in df.itertuples(index=False)
        ]
        models.LaboratoryCapacity.objects.bulk_create(objs)
        self._ok("laboratory_capacity", len(objs))

    def _load_reporting(self, d: Path):
        df = pd.read_csv(d / "reporting_metrics.csv")
        objs = [
            models.ReportingMetric(
                country_id=r.iso3, year=as_int(r.year),
                timeliness_pct=as_float(r.timeliness_pct),
                completeness_pct=as_float(r.completeness_pct),
                idsr_weekly_compliance_pct=as_float(r.idsr_weekly_compliance_pct),
            )
            for r in df.itertuples(index=False)
        ]
        models.ReportingMetric.objects.bulk_create(objs)
        self._ok("reporting_metrics", len(objs))

    def _load_workforce(self, d: Path):
        df = pd.read_csv(d / "workforce.csv")
        objs = [
            models.Workforce(
                country_id=r.iso3, year=as_int(r.year),
                epidemiologists_total=as_int(r.epidemiologists_total),
                epidemiologists_per_100k=as_float(r.epidemiologists_per_100k),
                feltp_trained_total=as_int(r.feltp_trained_total),
                feltp_trained_pct=as_float(r.feltp_trained_pct),
                lab_technicians_total=as_int(r.lab_technicians_total),
                lab_technicians_per_100k=as_float(r.lab_technicians_per_100k),
            )
            for r in df.itertuples(index=False)
        ]
        models.Workforce.objects.bulk_create(objs)
        self._ok("workforce", len(objs))

    def _load_funding(self, d: Path):
        df = pd.read_csv(d / "funding.csv")
        objs = [
            models.Funding(
                country_id=r.iso3, year=as_int(r.year),
                total_funding_usd=as_int(r.total_funding_usd),
                domestic_funding_usd=as_int(r.domestic_funding_usd),
                external_funding_usd=as_int(r.external_funding_usd),
                funding_per_capita_usd=as_float(r.funding_per_capita_usd),
                domestic_funding_share_pct=as_float(r.domestic_funding_share_pct),
            )
            for r in df.itertuples(index=False)
        ]
        models.Funding.objects.bulk_create(objs)
        self._ok("funding", len(objs))

    def _summary(self):
        self.stdout.write(self.style.MIGRATE_HEADING("Row counts:"))
        for label, model in [
            ("countries", models.Country),
            ("population", models.Population),
            ("disease_surveillance", models.DiseaseSurveillance),
            ("outbreaks", models.Outbreak),
            ("laboratory_capacity", models.LaboratoryCapacity),
            ("reporting_metrics", models.ReportingMetric),
            ("workforce", models.Workforce),
            ("funding", models.Funding),
        ]:
            self._ok(label, model.objects.count())
        invalid = models.DiseaseSurveillance.objects.filter(is_valid=False).count()
        self.stdout.write(self.style.WARNING(
            f"  quarantined surveillance rows: {invalid}"
        ))
