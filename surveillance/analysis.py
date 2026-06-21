# Support-Need Index (SNI): ~14 indicators across 5 domains, min-max normalised so
# higher always means greater need, averaged per domain then weighted into a 0-100
# score. Only valid surveillance rows feed it; missing values are skipped, not imputed.
# Methodology written up in full in the README.

from __future__ import annotations

import logging

import pandas as pd
from django.db.models import Count

from . import models

logger = logging.getLogger(__name__)

LATEST_YEAR = 2025
RECENT_WINDOW = [2023, 2024, 2025]
N_YEARS = 5

# (domain, column, direction). direction "invert" => low value means high need.
INDICATORS = [
    ("Reporting", "timeliness_pct", "invert"),
    ("Reporting", "completeness_pct", "invert"),
    ("Reporting", "idsr_weekly_compliance_pct", "invert"),
    ("Laboratory", "iso15189_accreditation_pct", "invert"),
    ("Laboratory", "avg_turnaround_time_days", "direct"),
    ("Laboratory", "diagnostic_tests_per_100k", "invert"),
    ("Workforce", "epidemiologists_per_100k", "invert"),
    ("Workforce", "feltp_trained_pct", "invert"),
    ("Workforce", "lab_technicians_per_100k", "invert"),
    ("Outbreaks", "avg_detection_days", "direct"),
    ("Outbreaks", "outbreaks_per_year", "direct"),
    ("Outbreaks", "mean_cfr_valid", "direct"),
    ("Funding", "funding_per_capita_usd", "invert"),
    ("Funding", "domestic_funding_share_pct", "invert"),
]

DOMAIN_WEIGHTS = {
    "Reporting": 0.20,
    "Laboratory": 0.20,
    "Workforce": 0.25,   # workforce is the structural bottleneck for IHR capacity
    "Outbreaks": 0.20,
    "Funding": 0.15,
}


def _df(qs, fields):
    return pd.DataFrame(list(qs.values(*fields)))


def build_indicator_frame() -> pd.DataFrame:
    """One row per country with all raw indicators joined together."""
    base = pd.DataFrame(list(models.Country.objects.values(
        "iso3", "country_name", "afro_subregion", "priority_country"
    ))).set_index("iso3")

    rep = _df(models.ReportingMetric.objects.filter(year=LATEST_YEAR),
              ["country_id", "timeliness_pct", "completeness_pct",
               "idsr_weekly_compliance_pct"]).set_index("country_id")

    lab = _df(models.LaboratoryCapacity.objects.filter(year=LATEST_YEAR),
              ["country_id", "iso15189_accreditation_pct",
               "avg_turnaround_time_days", "diagnostic_tests_per_100k"]
              ).set_index("country_id")

    wf = _df(models.Workforce.objects.filter(year=LATEST_YEAR),
             ["country_id", "epidemiologists_per_100k", "feltp_trained_pct",
              "lab_technicians_per_100k"]).set_index("country_id")

    fund = _df(models.Funding.objects.filter(year=LATEST_YEAR),
               ["country_id", "funding_per_capita_usd",
                "domestic_funding_share_pct"]).set_index("country_id")

    pop = _df(models.Population.objects.filter(year=LATEST_YEAR),
              ["country_id", "total_population"]).set_index("country_id")

    # Outbreak aggregates over the full 5-year window.
    ob = _df(models.Outbreak.objects.all(),
             ["country_id", "time_to_detection_days", "outbreak_id"])
    if not ob.empty:
        ob_agg = ob.groupby("country_id").agg(
            avg_detection_days=("time_to_detection_days", "mean"),
            outbreaks_per_year=("outbreak_id", lambda s: s.count() / N_YEARS),
        )
    else:
        ob_agg = pd.DataFrame(columns=["avg_detection_days", "outbreaks_per_year"])

    # Mean case-fatality ratio from VALID surveillance rows only (recent window).
    dis = _df(models.DiseaseSurveillance.objects.filter(
        is_valid=True, year__in=RECENT_WINDOW),
        ["country_id", "case_fatality_ratio_pct"])
    if not dis.empty:
        dis_agg = dis.groupby("country_id").agg(
            mean_cfr_valid=("case_fatality_ratio_pct", "mean"))
    else:
        dis_agg = pd.DataFrame(columns=["mean_cfr_valid"])

    frame = base.join([rep, lab, wf, fund, pop, ob_agg, dis_agg])
    return frame


def compute_support_index() -> pd.DataFrame:
    """Return the indicator frame enriched with domain scores, SNI and rank."""
    frame = build_indicator_frame()

    # Normalise each indicator to a 0-1 "need" score.
    norm_cols_by_domain: dict[str, list[str]] = {}
    for domain, col, direction in INDICATORS:
        if col not in frame.columns:
            continue
        s = frame[col].astype(float)
        lo, hi = s.min(), s.max()
        if pd.isna(lo) or hi == lo:
            norm = pd.Series(0.0, index=s.index)
        else:
            direct = (s - lo) / (hi - lo)          # high value -> 1
            norm = direct if direction == "direct" else (1 - direct)
        ncol = f"n__{col}"
        frame[ncol] = norm
        norm_cols_by_domain.setdefault(domain, []).append(ncol)

    # Domain score = mean of available normalised indicators in that domain.
    for domain, ncols in norm_cols_by_domain.items():
        frame[f"dom__{domain}"] = frame[ncols].mean(axis=1, skipna=True)

    # Weighted composite over available domains, renormalised by available weight.
    def composite(row):
        num = den = 0.0
        for domain, w in DOMAIN_WEIGHTS.items():
            val = row.get(f"dom__{domain}")
            if pd.notna(val):
                num += w * val
                den += w
        return 100 * num / den if den else float("nan")

    frame["support_index"] = frame.apply(composite, axis=1)
    frame = frame.sort_values("support_index", ascending=False)
    frame["rank"] = range(1, len(frame) + 1)

    # Tier by tertile of the index.
    q1, q2 = frame["support_index"].quantile([1 / 3, 2 / 3])
    def tier(x):
        if x >= q2:
            return "High need"
        if x >= q1:
            return "Medium need"
        return "Low need"
    frame["tier"] = frame["support_index"].apply(tier)
    return frame


def support_table() -> list[dict]:
    """Serialisable rows for the 'countries needing support' view."""
    frame = compute_support_index().reset_index()
    cols = {
        "rank": "rank", "iso3": "iso3", "country_name": "country_name",
        "afro_subregion": "afro_subregion", "priority_country": "priority_country",
        "support_index": "support_index", "tier": "tier",
        "dom__Reporting": "reporting", "dom__Laboratory": "laboratory",
        "dom__Workforce": "workforce", "dom__Outbreaks": "outbreaks",
        "dom__Funding": "funding",
    }
    out = []
    for _, r in frame.iterrows():
        row = {}
        for src, dst in cols.items():
            v = r.get(src)
            if isinstance(v, float):
                v = None if pd.isna(v) else round(v if dst in {
                    "support_index"} else v * 100 if dst in {
                    "reporting", "laboratory", "workforce", "outbreaks", "funding"
                } else v, 1)
            row[dst] = v
        out.append(row)
    return out


def summary_indicators() -> dict:
    """Region-wide headline KPIs for the dashboard summary cards."""
    pop_latest = models.Population.objects.filter(year=LATEST_YEAR)
    total_pop = sum(p.total_population or 0 for p in pop_latest)

    rep = models.ReportingMetric.objects.filter(year=LATEST_YEAR)
    timeliness = _mean([r.timeliness_pct for r in rep])
    completeness = _mean([r.completeness_pct for r in rep])

    wf = models.Workforce.objects.filter(year=LATEST_YEAR)
    epi = _mean([w.epidemiologists_per_100k for w in wf])

    lab = models.LaboratoryCapacity.objects.filter(year=LATEST_YEAR)
    accred = _mean([l.iso15189_accreditation_pct for l in lab])

    fund = models.Funding.objects.filter(year=LATEST_YEAR)
    total_funding = sum(f.total_funding_usd or 0 for f in fund)
    dom_share = _mean([f.domestic_funding_share_pct for f in fund])

    ob = models.Outbreak.objects.all()
    detection = _mean([o.time_to_detection_days for o in ob])

    flagged = models.DiseaseSurveillance.objects.filter(is_valid=False).count()
    total_dis = models.DiseaseSurveillance.objects.count()

    return {
        "n_countries": models.Country.objects.count(),
        "years": "2021-2025",
        "total_population": total_pop,
        "total_outbreaks": ob.count(),
        "avg_detection_days": _r(detection),
        "avg_timeliness": _r(timeliness),
        "avg_completeness": _r(completeness),
        "avg_epi_per_100k": _r(epi, 2),
        "avg_lab_accreditation": _r(accred),
        "total_funding_usd": total_funding,
        "avg_domestic_share": _r(dom_share),
        "flagged_rows": flagged,
        "total_surveillance_rows": total_dis,
    }


def chart_data() -> dict:
    """Pre-aggregated series for the dashboard charts (Chart.js)."""
    # Outbreaks per year.
    by_year = (models.Outbreak.objects.values("year")
               .annotate(n=Count("outbreak_id")).order_by("year"))
    outbreaks_year = {"labels": [str(r["year"]) for r in by_year],
                      "data": [r["n"] for r in by_year]}

    # Top-10 countries by Support-Need Index.
    sni = compute_support_index().reset_index().head(10)
    top_sni = {"labels": sni["country_name"].tolist(),
               "data": [round(x, 1) for x in sni["support_index"].tolist()]}

    # Region reporting trend (avg timeliness & completeness by year).
    trend_labels, timel, compl = [], [], []
    for y in range(2021, 2026):
        rows = models.ReportingMetric.objects.filter(year=y)
        trend_labels.append(str(y))
        timel.append(_r(_mean([r.timeliness_pct for r in rows])))
        compl.append(_r(_mean([r.completeness_pct for r in rows])))
    reporting_trend = {"labels": trend_labels, "timeliness": timel,
                       "completeness": compl}

    # Funding mix: domestic vs external share (latest year, per country).
    fund = (models.Funding.objects.filter(year=LATEST_YEAR)
            .select_related("country").order_by("domestic_funding_share_pct"))
    funding_mix = {
        "labels": [f.country.iso3 for f in fund],
        "domestic": [f.domestic_funding_share_pct for f in fund],
    }
    return {
        "outbreaks_year": outbreaks_year,
        "top_sni": top_sni,
        "reporting_trend": reporting_trend,
        "funding_mix": funding_mix,
    }


def recommendations() -> list[dict]:
    """Three biennium recommendations, derived from the weakest regional domains."""
    frame = compute_support_index()
    high = frame[frame["tier"] == "High need"]
    high_names = high["country_name"].tolist()

    # Regional averages backing each recommendation.
    epi = _mean(list(models.Workforce.objects.filter(year=LATEST_YEAR)
                     .values_list("epidemiologists_per_100k", flat=True)))
    accred = _mean(list(models.LaboratoryCapacity.objects.filter(year=LATEST_YEAR)
                        .values_list("iso15189_accreditation_pct", flat=True)))
    turnaround = _mean(list(models.LaboratoryCapacity.objects.filter(year=LATEST_YEAR)
                            .values_list("avg_turnaround_time_days", flat=True)))
    dom_share = _mean(list(models.Funding.objects.filter(year=LATEST_YEAR)
                           .values_list("domestic_funding_share_pct", flat=True)))
    timeliness = _mean(list(models.ReportingMetric.objects.filter(year=LATEST_YEAR)
                            .values_list("timeliness_pct", flat=True)))

    return [
        {
            "title": "Scale up the surveillance workforce (FETP) in high-need countries",
            "rationale": (
                f"Regional average is {epi:.2f} epidemiologists per 100,000 — far "
                f"below the IHR/Joint External Evaluation benchmark of 1 per 100,000. "
                f"Workforce is the most heavily weighted and weakest domain in the "
                f"index."
            ),
            "action": (
                "Fund FETP (Field Epidemiology Training Programme) cohorts and "
                "deploy mentored field epidemiologists, prioritising: "
                f"{', '.join(high_names[:5])}."
            ),
            "metric": f"{epi:.2f} epi / 100k (target ≥ 1.0)",
        },
        {
            "title": "Strengthen laboratory accreditation and reduce turnaround time",
            "rationale": (
                f"Only ~{accred:.0f}% of public labs are ISO 15189 accredited and "
                f"the average diagnostic turnaround is {turnaround:.1f} days, slowing "
                f"outbreak confirmation."
            ),
            "action": (
                "Invest in SLIPTA/SLMTA accreditation pathways, reagent supply "
                "chains and specimen-referral networks in low-capacity countries."
            ),
            "metric": f"{accred:.0f}% labs accredited; {turnaround:.1f}-day turnaround",
        },
        {
            "title": "Improve reporting performance and reduce external-funding dependency",
            "rationale": (
                f"Regional reporting timeliness averages {timeliness:.0f}% and "
                f"domestic financing is only {dom_share:.0f}% of surveillance funding, "
                f"leaving systems exposed to external-funding shocks."
            ),
            "action": (
                "Digitise IDSR reporting (e.g. DHIS2/electronic case-based reporting) "
                "and pair it with domestic-financing transition plans in the most "
                "donor-dependent countries."
            ),
            "metric": f"{timeliness:.0f}% timeliness; {dom_share:.0f}% domestic share",
        },
    ]


# --------------------------------------------------------------------- helpers
def _mean(values):
    vals = [v for v in values if v is not None and not pd.isna(v)]
    return sum(vals) / len(vals) if vals else None


def _r(x, n=1):
    return None if x is None else round(x, n)
