import json
import logging

from django.shortcuts import render

from . import analysis, models

logger = logging.getLogger(__name__)


def dashboard(request):
    context = {
        "summary": analysis.summary_indicators(),
        "charts": json.dumps(analysis.chart_data()),
        "recommendations": analysis.recommendations(),
    }
    return render(request, "surveillance/dashboard.html", context)


def support(request):
    rows = analysis.support_table()
    context = {
        "rows": rows,
        "weights": analysis.DOMAIN_WEIGHTS,
        "high": [r for r in rows if r["tier"] == "High need"],
    }
    return render(request, "surveillance/support.html", context)


def data_table(request):
    """Country-year fact table with country/year/disease filters and search."""
    year = request.GET.get("year", "")
    iso3 = request.GET.get("country", "")

    qs = (models.ReportingMetric.objects.select_related("country")
          .order_by("country__country_name", "year"))
    if year:
        qs = qs.filter(year=year)
    if iso3:
        qs = qs.filter(country__iso3=iso3)

    # Join the per-(country, year) facts into flat rows for the table.
    def idx(model):
        f = {}
        m = model.objects.all()
        if year:
            m = m.filter(year=year)
        if iso3:
            m = m.filter(country__iso3=iso3)
        for o in m:
            f[(o.country_id, o.year)] = o
        return f

    pop = idx(models.Population)
    lab = idx(models.LaboratoryCapacity)
    wf = idx(models.Workforce)
    fund = idx(models.Funding)

    rows = []
    for r in qs:
        key = (r.country_id, r.year)
        p, l, w, fnd = pop.get(key), lab.get(key), wf.get(key), fund.get(key)
        rows.append({
            "country": r.country.country_name,
            "iso3": r.country_id,
            "year": r.year,
            "population": getattr(p, "total_population", None),
            "timeliness": r.timeliness_pct,
            "completeness": r.completeness_pct,
            "idsr": r.idsr_weekly_compliance_pct,
            "lab_accred": getattr(l, "iso15189_accreditation_pct", None),
            "turnaround": getattr(l, "avg_turnaround_time_days", None),
            "epi_100k": getattr(w, "epidemiologists_per_100k", None),
            "funding_pc": getattr(fnd, "funding_per_capita_usd", None),
            "dom_share": getattr(fnd, "domestic_funding_share_pct", None),
        })

    context = {
        "rows": rows,
        "countries": models.Country.objects.order_by("country_name"),
        "years": list(range(2021, 2026)),
        "sel_year": year,
        "sel_country": iso3,
    }
    return render(request, "surveillance/data_table.html", context)
