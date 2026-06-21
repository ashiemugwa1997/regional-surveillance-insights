# Architecture

## System overview

```mermaid
flowchart LR
    subgraph Source
        CSV[(8 CSV files<br/>20 countries x 5 yrs)]
    end

    subgraph ETL["ETL (Django management command)"]
        P[Profile<br/>etl/profile_data.py]
        L[load_data<br/>validate / flag / load]
    end

    subgraph DB["MySQL 8.4"]
        REF[(Country<br/>reference)]
        FACT[(Fact tables:<br/>population, surveillance,<br/>outbreaks, lab, reporting,<br/>workforce, funding)]
    end

    subgraph App["Django app"]
        AN[analysis.py<br/>Support-Need Index]
        V[views + templates]
    end

    B[Browser<br/>dashboard / support / data table]

    CSV --> P --> L --> REF
    L --> FACT
    REF --> AN
    FACT --> AN
    AN --> V --> B

    classDef store fill:#0a3d62,color:#fff;
    class REF,FACT,CSV store;
```

All of this runs as two Docker Compose services: `db` (MySQL) and `web` (Django).
The `web` container waits for the database, migrates, runs the ETL, then serves the app.

## Data model (schema)

```mermaid
erDiagram
    Country ||--o{ Population : has
    Country ||--o{ DiseaseSurveillance : has
    Country ||--o{ Outbreak : has
    Country ||--o{ LaboratoryCapacity : has
    Country ||--o{ ReportingMetric : has
    Country ||--o{ Workforce : has
    Country ||--o{ Funding : has

    Country {
        char iso3 PK
        string country_name
        string afro_subregion
        float latitude
        float longitude
        int priority_country
    }
    Population {
        char country_id FK
        int year
        bigint total_population
        bigint under5_population
        float urban_population_pct
    }
    DiseaseSurveillance {
        char country_id FK
        int year
        string disease
        bigint cases_reported
        bigint deaths_reported
        float attack_rate_per_100k
        float case_fatality_ratio_pct
        bool is_valid
        string quality_notes
    }
    Outbreak {
        char outbreak_id PK
        char country_id FK
        int year
        string disease
        date start_date
        int duration_days
        int time_to_detection_days
        int cases
        int deaths
    }
    LaboratoryCapacity {
        char country_id FK
        int year
        int total_public_labs
        int labs_iso15189_accredited
        float iso15189_accreditation_pct
        float avg_turnaround_time_days
        float diagnostic_tests_per_100k
    }
    ReportingMetric {
        char country_id FK
        int year
        float timeliness_pct
        float completeness_pct
        float idsr_weekly_compliance_pct
    }
    Workforce {
        char country_id FK
        int year
        int epidemiologists_total
        float epidemiologists_per_100k
        int feltp_trained_total
        float feltp_trained_pct
        int lab_technicians_total
        float lab_technicians_per_100k
    }
    Funding {
        char country_id FK
        int year
        bigint total_funding_usd
        bigint domestic_funding_usd
        bigint external_funding_usd
        float funding_per_capita_usd
        float domestic_funding_share_pct
    }
```

`Country` is the single reference (dimension) table; every other table is a fact
table on a `(country, year)` key — a star-style layout that matches the panel shape
of the source data. Each fact table has a unique constraint on its key, and the
columns most used for filtering (`year`, `disease`, `afro_subregion`,
`priority_country`, `is_valid`) are indexed.
