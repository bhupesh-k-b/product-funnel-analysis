# Data provenance

Publisher: **Retailrocket**. Original source: [Retailrocket](https://www.kaggle.com/datasets/retailrocket/ecommerce-dataset). Retrieved 2026-10-15. Exact filenames, file sizes, download URLs, and SHA-256 checksums are recorded in [sources.json](../data/sources.json).

The source is CC BY-NC-SA 4.0. All aggregate CSVs, the packaged dashboard, and figures derived from Retailrocket are adaptations under CC BY-NC-SA 4.0. Attribution: Retailrocket; original source linked above. Changes: exact event deduplication, ordered-funnel aggregation, cohort/segment aggregation, visualization. No commercial-use rights are added by this repository. License: https://creativecommons.org/licenses/by-nc-sa/4.0/ .

The MIT license applies to original project code only. It does not relicense third-party data or derived data. Raw files are downloaded locally and excluded from Git.

Run `python -m src.download` from the repository root. It verifies existing files, verifies downloads before replacing them, and rejects upstream changes instead of silently analyzing a different version. Kaggle may redirect downloads to signed storage URLs; this build required no credentials. If anonymous access changes, manually download the source file to `data/raw/` and rerun checksum verification.
