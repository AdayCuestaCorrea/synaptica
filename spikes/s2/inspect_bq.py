"""S2 · What the BigQuery sandbox did to the dataset: expiration of the dataset and tables.

Writes a Markdown table to $GITHUB_STEP_SUMMARY (or stdout). Uses google-cloud-bigquery,
which comes with dbt-bigquery, and the credentials written by google-github-actions/auth.
"""

import os
import sys

from google.cloud import bigquery


def main() -> None:
    project, dataset_id = os.environ["GCP_PROJECT"], os.environ.get("BQ_DATASET", "synaptica_s2")
    client = bigquery.Client(project=project)
    dataset = client.get_dataset(f"{project}.{dataset_id}")
    default_ms = dataset.default_table_expiration_ms
    lines = [
        f"### BigQuery dataset `{dataset_id}` ({dataset.location})",
        "",
        f"- Default table expiration: {default_ms / 86_400_000 if default_ms else None} days",
        "",
        "| Table | Type | Rows | Expires |",
        "|---|---|---|---|",
    ]
    for item in client.list_tables(dataset):
        table = client.get_table(item.reference)
        lines.append(
            f"| {table.table_id} | {table.table_type} | {table.num_rows} | {table.expires} |"
        )
    out = "\n".join(lines) + "\n"
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(out)
    sys.stdout.write(out)


if __name__ == "__main__":
    main()
