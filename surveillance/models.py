# Schema: Country is the reference table, everything else is a per-(country, year)
# fact table mirroring the CSV panel (20 countries x 5 years). Indicators that can
# be missing in the source are nullable so we store "no data" instead of faking it.

from django.db import models


class Country(models.Model):
    iso3 = models.CharField(max_length=3, primary_key=True)
    country_name = models.CharField(max_length=120)
    afro_subregion = models.CharField(max_length=40, db_index=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    # 1 = highest priority .. 3 = lowest (from the WHO reference file)
    priority_country = models.PositiveSmallIntegerField(db_index=True)

    class Meta:
        verbose_name_plural = "countries"
        ordering = ["country_name"]

    def __str__(self) -> str:
        return f"{self.country_name} ({self.iso3})"


class TimeSeriesBase(models.Model):
    """Common (country, year) key shared by every fact table."""

    country = models.ForeignKey(Country, on_delete=models.CASCADE)
    year = models.PositiveSmallIntegerField(db_index=True)

    class Meta:
        abstract = True


class Population(TimeSeriesBase):
    total_population = models.BigIntegerField(null=True, blank=True)
    under5_population = models.BigIntegerField(null=True, blank=True)
    urban_population_pct = models.FloatField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["country", "year"], name="uq_population_country_year"
            )
        ]


class DiseaseSurveillance(TimeSeriesBase):
    disease = models.CharField(max_length=60, db_index=True)
    cases_reported = models.BigIntegerField(null=True, blank=True)
    deaths_reported = models.BigIntegerField(null=True, blank=True)
    attack_rate_per_100k = models.FloatField(null=True, blank=True)
    case_fatality_ratio_pct = models.FloatField(null=True, blank=True)

    # Data-quality quarantine fields.
    is_valid = models.BooleanField(default=True, db_index=True)
    quality_notes = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["country", "year", "disease"],
                name="uq_disease_country_year_disease",
            )
        ]
        indexes = [models.Index(fields=["disease", "year"])]


class Outbreak(models.Model):
    outbreak_id = models.CharField(max_length=20, primary_key=True)
    country = models.ForeignKey(Country, on_delete=models.CASCADE)
    year = models.PositiveSmallIntegerField(db_index=True)
    disease = models.CharField(max_length=60, db_index=True)
    start_date = models.DateField(null=True, blank=True)
    duration_days = models.IntegerField(null=True, blank=True)
    time_to_detection_days = models.IntegerField(null=True, blank=True)
    cases = models.IntegerField(null=True, blank=True)
    deaths = models.IntegerField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["country", "year"])]


class LaboratoryCapacity(TimeSeriesBase):
    total_public_labs = models.IntegerField(null=True, blank=True)
    labs_iso15189_accredited = models.IntegerField(null=True, blank=True)
    iso15189_accreditation_pct = models.FloatField(null=True, blank=True)
    avg_turnaround_time_days = models.FloatField(null=True, blank=True)
    diagnostic_tests_per_100k = models.FloatField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["country", "year"], name="uq_lab_country_year"
            )
        ]


class ReportingMetric(TimeSeriesBase):
    timeliness_pct = models.FloatField(null=True, blank=True)
    completeness_pct = models.FloatField(null=True, blank=True)
    idsr_weekly_compliance_pct = models.FloatField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["country", "year"], name="uq_reporting_country_year"
            )
        ]


class Workforce(TimeSeriesBase):
    epidemiologists_total = models.IntegerField(null=True, blank=True)
    epidemiologists_per_100k = models.FloatField(null=True, blank=True)
    feltp_trained_total = models.IntegerField(null=True, blank=True)
    feltp_trained_pct = models.FloatField(null=True, blank=True)
    lab_technicians_total = models.IntegerField(null=True, blank=True)
    lab_technicians_per_100k = models.FloatField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["country", "year"], name="uq_workforce_country_year"
            )
        ]


class Funding(TimeSeriesBase):
    total_funding_usd = models.BigIntegerField(null=True, blank=True)
    domestic_funding_usd = models.BigIntegerField(null=True, blank=True)
    external_funding_usd = models.BigIntegerField(null=True, blank=True)
    funding_per_capita_usd = models.FloatField(null=True, blank=True)
    domestic_funding_share_pct = models.FloatField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["country", "year"], name="uq_funding_country_year"
            )
        ]
