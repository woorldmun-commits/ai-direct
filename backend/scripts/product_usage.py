"""Run from backend: python -m scripts.product_usage --workspace 123 --from-at ... --to-at ..."""
import argparse
import json
import os
from datetime import datetime

import psycopg

from app.insights.product_usage import build


def main():
    parser = argparse.ArgumentParser(description='Read-only workspace usage aggregates; authorized operators only.')
    parser.add_argument('--workspace', required=True, type=int)
    parser.add_argument('--from-at', required=True, type=datetime.fromisoformat)
    parser.add_argument('--to-at', required=True, type=datetime.fromisoformat)
    args = parser.parse_args()
    dsn = os.environ.get('INROU_USAGE_DATABASE_URL')
    if not dsn:
        parser.error('INROU_USAGE_DATABASE_URL for app_rw is required')
    try:
        with psycopg.connect(dsn, autocommit=True, connect_timeout=5) as conn:
            result = build(conn, args.workspace, args.from_at, args.to_at)
    except (ValueError, psycopg.Error):
        parser.exit(2, 'Usage report failed: check role, workspace, timestamps and database availability.\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
