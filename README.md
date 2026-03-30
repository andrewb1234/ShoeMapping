# ShoeMapping: RunRepeat Crawler (Phase 1)

This repository now contains the first data collection step for the shoe recommendation engine: a crawler that discovers shoe pages on `https://runrepeat.com/` and extracts shoe-specific **Lab Test Results**.

## What it stores

Each record is keyed by:

- `shoe_id = "<brand>::<full_shoe_name>"`

And includes:

- `brand`
- `shoe_name`
- `source_url`
- `lab_test_results` (metric/value pairs from the shoe column, i.e. left of `Average`)
- `crawled_at`

Output file defaults to:

- `data/runrepeat_lab_tests.json`

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

Quick test crawl:

```bash
python3 -m crawler.runrepeat_crawler --max-shoes 20 --workers 4
```

Larger crawl:

```bash
python3 -m crawler.runrepeat_crawler --workers 8
```

Custom output:

```bash
python3 -m crawler.runrepeat_crawler --output data/runrepeat_lab_tests_full.json
```

## Notes

- URL discovery is sitemap-based (`robots.txt` + sitemap traversal).
- Candidate pages are filtered to likely single-slug shoe pages.
- The crawler skips pages where it cannot find `Lab Test Results` in table format.
- Re-runs are incremental: existing output is loaded and merged by `shoe_id`.
