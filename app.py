from pathlib import Path
import logging
import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from clinic import CASES, benchmark, connect

app = FastAPI(title='Query Clinic', version='1.0.0')

class Experiment(BaseModel):
    case_id: str
    samples: int = Field(default=5, ge=3, le=9, strict=True)

@app.get('/')
def home(): return FileResponse(Path(__file__).parent / 'static/index.html')

@app.get('/api/health')
def health():
    try:
        with connect() as conn: conn.execute('SELECT 1 FROM clinic.orders LIMIT 1')
        return {'status': 'ready'}
    except (psycopg.Error, RuntimeError):
        raise HTTPException(503, 'Database unavailable or not seeded')

@app.get('/api/cases')
def cases():
    return [{'id': key, 'title': c['title'], 'sql': c['sql'], 'reason': c['why'], 'tradeoff': c['tradeoff']}
            for key, c in CASES.items()]

@app.post('/api/benchmark')
def run(body: Experiment):
    if body.case_id not in CASES: raise HTTPException(404, 'Unknown query case')
    try: return benchmark(body.case_id, body.samples)
    except (psycopg.Error, RuntimeError):
        logging.exception('Benchmark failed')
        raise HTTPException(503, 'Experiment failed; check database readiness and server logs')

@app.get('/api/runs')
def runs():
    try:
        with connect() as conn:
            rows = conn.execute('SELECT id, created_at, report FROM clinic.runs ORDER BY id DESC LIMIT 20').fetchall()
        return [{'id': r[0], 'created_at': r[1], **r[2]} for r in rows]
    except (psycopg.Error, RuntimeError):
        raise HTTPException(503, 'Database unavailable or not seeded')
