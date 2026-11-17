import os
import psycopg
import pytest
from fastapi.testclient import TestClient
from app import app
from clinic import CASES, INDEXES, benchmark, connect, digest, initialize

client = TestClient(app)
db = pytest.mark.skipif(not os.getenv('DATABASE_URL'), reason='Requires dedicated PostgreSQL DATABASE_URL')

def test_catalog_and_dashboard():
    response = client.get('/api/cases')
    assert response.status_code == 200
    assert {c['id'] for c in response.json()} == set(CASES)
    assert 'Query Clinic' in client.get('/').text

def test_unknown_case_rejected_without_database():
    assert client.post('/api/benchmark', json={'case_id': 'DROP TABLE orders'}).status_code == 404

@pytest.mark.parametrize('samples', [0, 2, 10, True, 3.5])
def test_sample_limits(samples):
    assert client.post('/api/benchmark', json={'case_id': 'pending_queue', 'samples': samples}).status_code == 422

def test_digest_preserves_result_differences():
    assert digest([(1, 'paid')]) == digest([(1, 'paid')])
    assert digest([(1, 'paid')]) != digest([(2, 'paid')])

def test_missing_database_is_reported(monkeypatch):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    assert client.get('/api/health').status_code == 503
    assert client.get('/api/runs').status_code == 503
    assert client.post('/api/benchmark', json={'case_id': 'pending_queue'}).status_code == 503

@db
def test_seed_is_idempotent():
    initialize()
    initialize()
    with connect() as conn:
        assert conn.execute('SELECT count(*) FROM clinic.orders').fetchone()[0] == 100000
        assert conn.execute('SELECT count(*) FROM clinic.customers').fetchone()[0] == 5000
        assert conn.execute('SELECT count(*) FROM clinic.products').fetchone()[0] == 200

@db
@pytest.mark.parametrize('values', [
    (200001, 999999, 1, 1, 'paid'),
    (200001, 1, 999999, 1, 'paid'),
    (200001, 1, 1, 0, 'paid'),
    (200001, 1, 1, 1, 'invalid')])
def test_integrity_constraints(values):
    with pytest.raises(psycopg.IntegrityError):
        with connect() as conn:
            conn.execute("INSERT INTO clinic.orders VALUES (%s,%s,%s,'2025-01-01',%s,%s)", values)

@db
def test_transaction_rolls_back_partial_order():
    with pytest.raises(psycopg.errors.CheckViolation):
        with connect() as conn:
            conn.execute("INSERT INTO clinic.customers VALUES (900001,'rollback@example.test','Rollback')")
            conn.execute("INSERT INTO clinic.orders VALUES (200001,900001,1,'2025-01-01',0,'paid')")
    with connect() as conn:
        assert conn.execute('SELECT count(*) FROM clinic.customers WHERE id=900001').fetchone()[0] == 0

@db
@pytest.mark.parametrize('case_id', list(CASES))
def test_real_comparison_and_cleanup(case_id):
    report = benchmark(case_id, 3)
    assert report['results_match']
    assert report['before']['result_hash'] == report['after']['result_hash']
    assert report['before']['row_count'] > 0
    assert len(report['before']['samples_ms']) == 3
    assert report['before']['median_ms'] >= 0
    assert report['after']['median_ms'] >= 0
    with connect() as conn:
        indexes = conn.execute("SELECT indexname FROM pg_indexes WHERE schemaname='clinic'").fetchall()
        assert not set(INDEXES).intersection(r[0] for r in indexes)
        assert conn.execute('SELECT report FROM clinic.runs WHERE id=%s',(report['id'],)).fetchone()[0]['results_match']

@db
def test_failed_experiment_rolls_back_index(monkeypatch):
    import clinic
    original = clinic.measure
    counter = 0
    def fail_after_index(*args):
        nonlocal counter
        counter += 1
        if counter == 2: raise RuntimeError('simulated measurement failure')
        return original(*args)
    monkeypatch.setattr(clinic, 'measure', fail_after_index)
    with pytest.raises(RuntimeError, match='simulated'):
        benchmark('customer_history', 3)
    with connect() as conn:
        assert conn.execute("SELECT to_regclass('clinic.qc_customer_history')").fetchone()[0] is None

@db
def test_http_benchmark_and_history():
    assert client.get('/api/health').status_code == 200
    response = client.post('/api/benchmark',json={'case_id':'pending_queue','samples':3})
    assert response.status_code == 200
    assert response.json()['results_match']
    assert any(r['id'] == response.json()['id'] for r in client.get('/api/runs').json())
