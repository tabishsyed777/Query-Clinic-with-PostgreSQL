"""Fixed-query PostgreSQL index experiments with transactional cleanup."""
import hashlib
import json
import os
from pathlib import Path
from statistics import median
import psycopg
from psycopg.types.json import Jsonb

CASES = {
 'customer_history': {
  'title': 'Customer order history',
  'sql': 'SELECT id, ordered_at, status FROM clinic.orders WHERE customer_id = %s ORDER BY ordered_at DESC, id DESC',
  'params': (1241,),
  'index': 'CREATE INDEX qc_customer_history ON clinic.orders (customer_id, ordered_at DESC, id DESC)',
  'why': 'An index beginning with customer_id narrows the lookup and supplies the requested date ordering.',
  'tradeoff': 'Adds storage and maintenance work on inserts and customer/date updates.'},
 'daily_revenue': {
  'title': 'Paid revenue for one day',
  'sql': "SELECT o.product_id, SUM(o.quantity * p.price) AS revenue FROM clinic.orders o JOIN clinic.products p ON p.id = o.product_id WHERE o.status = 'paid' AND o.ordered_at >= %s AND o.ordered_at < %s GROUP BY o.product_id ORDER BY o.product_id",
  'params': ('2025-06-15', '2025-06-16'),
  'index': "CREATE INDEX qc_paid_day ON clinic.orders (ordered_at) INCLUDE (product_id, quantity) WHERE status = 'paid'",
  'why': 'A partial index stores paid orders and restricts the scan to the selected day. Included columns may reduce heap access when visibility permits.',
  'tradeoff': 'Useful for paid-order lookups; other statuses cannot use this partial index.'},
 'pending_queue': {
  'title': 'Oldest pending orders',
  'sql': "SELECT id, ordered_at FROM clinic.orders WHERE status = 'pending' ORDER BY ordered_at, id LIMIT 50",
  'params': (),
  'index': "CREATE INDEX qc_pending_queue ON clinic.orders (ordered_at, id) WHERE status = 'pending'",
  'why': 'A partial ordered index lets PostgreSQL stop after the first 50 pending orders.',
  'tradeoff': 'Status changes must update membership in the index.'}
}
INDEXES = ('qc_customer_history', 'qc_paid_day', 'qc_pending_queue')
LOCK_ID = 81923741

def connect():
    url = os.environ.get('DATABASE_URL')
    if not url:
        raise RuntimeError('Set DATABASE_URL to the dedicated Query Clinic PostgreSQL database.')
    return psycopg.connect(url, connect_timeout=5)

def initialize():
    with connect() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(%s)', (LOCK_ID,))
        conn.execute(Path(__file__).with_name('schema.sql').read_text(), prepare=False)

def digest(rows):
    return hashlib.sha256(json.dumps(rows, default=str, separators=(',', ':')).encode()).hexdigest()

def explain(conn, case):
    return conn.execute('EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) '+case['sql'], case['params']).fetchone()[0][0]

def measure(conn, case, samples):
    # Warm each variant once; EXPLAIN timing excludes Python serialization and API overhead.
    explain(conn, case)
    plans = [explain(conn, case) for _ in range(samples)]
    rows = conn.execute(case['sql'], case['params']).fetchall()
    return {'median_ms': median(p['Execution Time'] for p in plans),
            'samples_ms': [p['Execution Time'] for p in plans],
            'row_count': len(rows), 'result_hash': digest(rows), 'plan': plans[-1]['Plan']}

def benchmark(case_id, samples=5):
    if case_id not in CASES: raise ValueError('Unknown query case')
    if type(samples) is not int or not 3 <= samples <= 9: raise ValueError('Samples must be between 3 and 9')
    case = CASES[case_id]
    with connect() as conn:
        with conn.transaction(force_rollback=True):
            conn.execute("SET LOCAL statement_timeout = '15s'")
            conn.execute("SET LOCAL lock_timeout = '5s'")
            conn.execute('SELECT pg_advisory_xact_lock(%s)', (LOCK_ID,))
            # Hold writes to keep before/after result comparison meaningful.
            conn.execute('LOCK TABLE clinic.orders, clinic.products IN SHARE MODE')
            for name in INDEXES: conn.execute('DROP INDEX IF EXISTS clinic.'+name)
            before = measure(conn, case, samples)
            conn.execute(case['index'])
            after = measure(conn, case, samples)
            if before['result_hash'] != after['result_hash']:
                raise RuntimeError('Query results changed during experiment')
            report = {'case_id': case_id, 'title': case['title'], 'sql': case['sql'],
                'parameters': case['params'], 'recommendation': case['index'],
                'reason': case['why'], 'tradeoff': case['tradeoff'], 'before': before, 'after': after,
                'speedup': round(before['median_ms'] / after['median_ms'], 2) if after['median_ms'] else None,
                'results_match': True, 'samples': samples,
                'method': 'Warm-cache, baseline first, fixed seed data. Index DDL rolls back; speedups vary by hardware and cache.'}
        # Experiment has rolled back. Persist only its evidence.
        run_id = conn.execute('INSERT INTO clinic.runs(report) VALUES (%s) RETURNING id', (Jsonb(report),)).fetchone()[0]
    return {'id': run_id, **report}

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['seed', 'benchmark'])
    parser.add_argument('--case', choices=list(CASES), default='customer_history')
    args = parser.parse_args()
    if args.command == 'seed':
        initialize()
        print('Seeded 5,000 customers, 200 products and 100,000 orders.')
    else: print(json.dumps(benchmark(args.case), indent=2, default=str))
