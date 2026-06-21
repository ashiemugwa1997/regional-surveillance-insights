import csv
import json
import logging

from django.http import Http404, HttpResponse
from django.shortcuts import render
from openpyxl import Workbook

from . import analysis, ingest, models

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


def _data_rows(year="", iso3=""):
    """Flatten the per-(country, year) facts into rows for the table/export."""
    qs = (models.ReportingMetric.objects.select_related("country")
          .order_by("country__country_name", "year"))
    if year:
        qs = qs.filter(year=year)
    if iso3:
        qs = qs.filter(country__iso3=iso3)

    def idx(model):
        m = model.objects.all()
        if year:
            m = m.filter(year=year)
        if iso3:
            m = m.filter(country__iso3=iso3)
        return {(o.country_id, o.year): o for o in m}

    pop, lab = idx(models.Population), idx(models.LaboratoryCapacity)
    wf, fund = idx(models.Workforce), idx(models.Funding)

    rows = []
    for r in qs:
        key = (r.country_id, r.year)
        p, l, w, fnd = pop.get(key), lab.get(key), wf.get(key), fund.get(key)
        rows.append({
            "country": r.country.country_name, "iso3": r.country_id, "year": r.year,
            "population": getattr(p, "total_population", None),
            "timeliness": r.timeliness_pct, "completeness": r.completeness_pct,
            "idsr": r.idsr_weekly_compliance_pct,
            "lab_accred": getattr(l, "iso15189_accreditation_pct", None),
            "turnaround": getattr(l, "avg_turnaround_time_days", None),
            "epi_100k": getattr(w, "epidemiologists_per_100k", None),
            "funding_pc": getattr(fnd, "funding_per_capita_usd", None),
            "dom_share": getattr(fnd, "domestic_funding_share_pct", None),
        })
    return rows


def data_table(request):
    """Country-year fact table with country/year filters and search."""
    year = request.GET.get("year", "")
    iso3 = request.GET.get("country", "")
    context = {
        "rows": _data_rows(year, iso3),
        "countries": models.Country.objects.order_by("country_name"),
        "years": list(range(2021, 2026)),
        "sel_year": year,
        "sel_country": iso3,
    }
    return render(request, "surveillance/data_table.html", context)


def map_view(request):
    context = {"points": json.dumps(analysis.map_data())}
    return render(request, "surveillance/map.html", context)


def country_detail(request, iso3):
    data = analysis.country_detail(iso3.upper())
    if not data:
        raise Http404("Country not found")
    data["series_json"] = json.dumps({
        "years": data["years"],
        "reporting": data["reporting"],
        "laboratory": data["laboratory"],
        "workforce": data["workforce"],
        "funding": data["funding"],
    })
    return render(request, "surveillance/country_detail.html", data)


def data_quality(request):
    return render(request, "surveillance/data_quality.html",
                  analysis.data_quality_summary())


def upload(request):
    """Update a dataset from an uploaded CSV/Excel file (upsert + flag existing)."""
    report = error = None
    if request.method == "POST":
        dataset = request.POST.get("dataset")
        uploaded = request.FILES.get("file")
        if dataset not in ingest.DATASETS:
            error = "Please choose a valid dataset."
        elif not uploaded:
            error = "Please choose a CSV or Excel file to upload."
        else:
            try:
                df = ingest.read_table(uploaded)
                report = ingest.ingest(dataset, df)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Upload failed")
                error = f"Could not process the file: {exc}"
    context = {
        "datasets": [(k, v["label"]) for k, v in ingest.DATASETS.items()],
        "report": report,
        "error": error,
    }
    return render(request, "surveillance/upload.html", context)


# ------------------------------------------------------------------- exports
DATA_HEADERS = ["Country", "ISO3", "Year", "Population", "Timeliness %",
                "Completeness %", "IDSR %", "Lab accred %", "Turnaround d",
                "Epi /100k", "Funding/cap $", "Domestic %"]
DATA_KEYS = ["country", "iso3", "year", "population", "timeliness", "completeness",
             "idsr", "lab_accred", "turnaround", "epi_100k", "funding_pc", "dom_share"]

SUPPORT_HEADERS = ["Rank", "ISO3", "Country", "Subregion", "Priority", "SNI",
                   "Tier", "Reporting", "Laboratory", "Workforce", "Outbreaks",
                   "Funding"]
SUPPORT_KEYS = ["rank", "iso3", "country_name", "afro_subregion", "priority_country",
                "support_index", "tier", "reporting", "laboratory", "workforce",
                "outbreaks", "funding"]


def _csv_response(filename, headers, rows):
    resp = HttpResponse(content_type="text/csv")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(resp)
    writer.writerow(headers)
    writer.writerows(rows)
    return resp


def _xlsx_response(filename, headers, rows):
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(list(r))
    resp = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    wb.save(resp)
    return resp


def export_data(request, fmt):
    rows = [[r[k] for k in DATA_KEYS]
            for r in _data_rows(request.GET.get("year", ""),
                                request.GET.get("country", ""))]
    if fmt == "xlsx":
        return _xlsx_response("surveillance_data.xlsx", DATA_HEADERS, rows)
    return _csv_response("surveillance_data.csv", DATA_HEADERS, rows)


def export_support(request, fmt):
    rows = [[r[k] for k in SUPPORT_KEYS] for r in analysis.support_table()]
    if fmt == "xlsx":
        return _xlsx_response("support_ranking.xlsx", SUPPORT_HEADERS, rows)
    return _csv_response("support_ranking.csv", SUPPORT_HEADERS, rows)
