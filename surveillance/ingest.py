# Upsert an uploaded CSV/Excel file into a dataset. Existing rows (matched on their
# natural key) are flagged and updated rather than duplicated; new rows are inserted.
# Reused by the upload page; same flag-and-quarantine rules as the ETL.

import logging

import pandas as pd

from . import models

logger = logging.getLogger(__name__)


def _clean(v):
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


def _i(v):
    v = _clean(v)
    return None if v is None else int(round(float(v)))


def _f(v):
    v = _clean(v)
    return None if v is None else float(v)


def _s(v):
    v = _clean(v)
    return None if v is None else str(v).strip()


def _d(v):
    v = _clean(v)
    if v is None:
        return None
    ts = pd.to_datetime(v, errors="coerce")
    return None if pd.isna(ts) else ts.date()


# dataset key -> spec. pk = primary-key column; key = extra composite-key columns;
# fk = rows carry an iso3 that must already exist in the Country table.
DATASETS = {
    "countries": dict(
        model=models.Country, label="Country reference", pk="iso3",
        fields={"country_name": _s, "afro_subregion": _s, "latitude": _f,
                "longitude": _f, "priority_country": _i}),
    "population": dict(
        model=models.Population, label="Population", fk=True, key=["year"],
        fields={"total_population": _i, "under5_population": _i,
                "urban_population_pct": _f}),
    "disease_surveillance": dict(
        model=models.DiseaseSurveillance, label="Disease surveillance",
        fk=True, key=["year", "disease"], flag=True,
        fields={"cases_reported": _i, "deaths_reported": _i,
                "attack_rate_per_100k": _f, "case_fatality_ratio_pct": _f}),
    "outbreaks": dict(
        model=models.Outbreak, label="Outbreaks", pk="outbreak_id", fk=True,
        fields={"year": _i, "disease": _s, "start_date": _d, "duration_days": _i,
                "time_to_detection_days": _i, "cases": _i, "deaths": _i}),
    "laboratory_capacity": dict(
        model=models.LaboratoryCapacity, label="Laboratory capacity",
        fk=True, key=["year"],
        fields={"total_public_labs": _i, "labs_iso15189_accredited": _i,
                "iso15189_accreditation_pct": _f, "avg_turnaround_time_days": _f,
                "diagnostic_tests_per_100k": _f}),
    "reporting_metrics": dict(
        model=models.ReportingMetric, label="Reporting metrics",
        fk=True, key=["year"],
        fields={"timeliness_pct": _f, "completeness_pct": _f,
                "idsr_weekly_compliance_pct": _f}),
    "workforce": dict(
        model=models.Workforce, label="Workforce", fk=True, key=["year"],
        fields={"epidemiologists_total": _i, "epidemiologists_per_100k": _f,
                "feltp_trained_total": _i, "feltp_trained_pct": _f,
                "lab_technicians_total": _i, "lab_technicians_per_100k": _f}),
    "funding": dict(
        model=models.Funding, label="Funding", fk=True, key=["year"],
        fields={"total_funding_usd": _i, "domestic_funding_usd": _i,
                "external_funding_usd": _i, "funding_per_capita_usd": _f,
                "domestic_funding_share_pct": _f}),
}


def read_table(uploaded_file):
    """Read an uploaded file as a DataFrame, auto-detecting CSV vs Excel by content.

    Detection is based on the file's magic bytes (not the extension), so a
    mislabelled or extension-less file is still handled correctly:
      * XLSX is a ZIP archive  -> starts with PK\\x03\\x04
      * legacy XLS is OLE2      -> starts with \\xd0\\xcf\\x11\\xe0
    Anything else is treated as CSV.
    """
    head = uploaded_file.read(8)
    uploaded_file.seek(0)
    if isinstance(head, str):  # text-mode handle -> definitely not a binary spreadsheet
        return pd.read_csv(uploaded_file)
    if head[:4] == b"PK\x03\x04" or head[:4] == b"\xd0\xcf\x11\xe0":
        return pd.read_excel(uploaded_file)
    return pd.read_csv(uploaded_file)


def _quality_flags(defaults):
    """Flag under-ascertainment (deaths>cases / CFR>100%) — kept, not dropped."""
    notes = []
    cfr = defaults.get("case_fatality_ratio_pct")
    cases, deaths = defaults.get("cases_reported"), defaults.get("deaths_reported")
    if cfr is not None and cfr > 100:
        notes.append("CFR>100% (under-ascertainment)")
    if cases is not None and deaths is not None and deaths > cases:
        notes.append("deaths>cases (under-ascertainment)")
    defaults["under_ascertainment"] = bool(notes)
    defaults["quality_notes"] = "; ".join(notes)
    return bool(notes)


def ingest(dataset, df):
    """Upsert the DataFrame; return a report of new / existing / flagged / errors."""
    spec = DATASETS[dataset]
    model = spec["model"]
    iso_valid = set(models.Country.objects.values_list("iso3", flat=True))
    report = {"dataset": spec["label"], "rows": len(df), "created": 0,
              "existing": 0, "flagged": 0, "errors": []}

    for n, row in enumerate(df.to_dict("records"), start=2):  # row 1 is the header
        try:
            lookup, defaults = {}, {}

            iso = None
            if spec.get("fk"):
                iso = _s(row.get("iso3"))
                if iso not in iso_valid:
                    raise ValueError(f"unknown country '{iso}'")

            if spec.get("pk"):
                pkval = _s(row.get(spec["pk"]))
                if not pkval:
                    raise ValueError(f"missing {spec['pk']}")
                lookup[spec["pk"]] = pkval
                if iso is not None:
                    defaults["country_id"] = iso
            else:
                if iso is not None:
                    lookup["country_id"] = iso
                for k in spec.get("key", []):
                    lookup[k] = _i(row.get(k)) if k == "year" else _s(row.get(k))

            for col, fn in spec["fields"].items():
                if col in row:
                    defaults[col] = fn(row.get(col))

            flagged = _quality_flags(defaults) if spec.get("flag") else False

            _, created = model.objects.update_or_create(defaults=defaults, **lookup)
            report["created" if created else "existing"] += 1
            if flagged:
                report["flagged"] += 1
        except Exception as exc:  # noqa: BLE001 - report bad rows, keep going
            report["errors"].append(f"row {n}: {exc}")

    return report
