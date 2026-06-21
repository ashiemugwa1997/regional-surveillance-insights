from django.contrib import admin

from . import models

admin.site.site_header = "Regional Surveillance Insights — Admin"
admin.site.site_title = "Surveillance Admin"


@admin.register(models.Country)
class CountryAdmin(admin.ModelAdmin):
    list_display = ("iso3", "country_name", "afro_subregion", "priority_country")
    list_filter = ("afro_subregion", "priority_country")
    search_fields = ("iso3", "country_name")


@admin.register(models.DiseaseSurveillance)
class DiseaseSurveillanceAdmin(admin.ModelAdmin):
    list_display = (
        "country", "year", "disease", "cases_reported", "deaths_reported",
        "case_fatality_ratio_pct", "is_valid",
    )
    list_filter = ("is_valid", "disease", "year")
    search_fields = ("country__country_name",)


@admin.register(models.Outbreak)
class OutbreakAdmin(admin.ModelAdmin):
    list_display = (
        "outbreak_id", "country", "year", "disease", "cases", "deaths",
        "time_to_detection_days",
    )
    list_filter = ("disease", "year")


for _model in (
    models.Population, models.LaboratoryCapacity, models.ReportingMetric,
    models.Workforce, models.Funding,
):
    admin.site.register(_model)
