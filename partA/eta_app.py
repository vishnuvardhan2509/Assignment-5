import os, time, uuid
from collections import Counter
import joblib
import pandas as pd
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field, model_validator

bundle = joblib.load(os.getenv('ETA_MODEL', 'data/eta_v1.joblib'))
model = bundle['model']
app = FastAPI()
counts = Counter()
bounds = (.001,.005,.01,.025,.05,.1,.25,.5,1,2,5,float('inf'))
latencies = Counter()
total_time = 0.0

from eta_schema import Delivery, Batch

@app.middleware('http')
async def observe(request: Request, call_next):
    global total_time
    request.state.rid = request.headers.get('X-Request-ID', str(uuid.uuid4()))
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        response = JSONResponse({'error':'internal_server_error', 'request_id':request.state.rid}, status_code=500)
    response.headers['X-Request-ID'] = request.state.rid
    if request.url.path != '/metrics':
        elapsed = time.perf_counter()-start
        counts[(request.url.path,response.status_code)] += 1
        total_time += elapsed
        for b in bounds:
            latencies[b] += elapsed <= b
    return response

@app.exception_handler(RequestValidationError)
async def invalid(request, exc):
    return JSONResponse({'error':'validation_failed','details':[{'field':'.'.join(map(str,e['loc'])), 'msg':e['msg']} for e in exc.errors()], 'request_id':request.state.rid},status_code=422)

from starlette.exceptions import HTTPException
@app.exception_handler(HTTPException)
async def http_error(request, exc):
    return JSONResponse({'error':str(exc.detail),'request_id':request.state.rid},status_code=exc.status_code)

@app.post('/v1/models/eta:predict')
def predict(batch: Batch, request: Request):
    frame = pd.DataFrame([r.model_dump() for r in batch.instances],columns=bundle['feature_columns'])
    return {'predictions':[round(float(x),1) for x in model.predict(frame)], 'model_version':bundle['version'], 'request_id':request.state.rid}

@app.get('/healthz')
def health(request: Request):
    return {'status':'ok','model_version':bundle['version'],'request_id':request.state.rid}

@app.get('/metrics')
def metrics():
    import json
    lines=['# TYPE eta_requests_total counter']
    lines += [f'eta_requests_total{{path={json.dumps(p)},status="{s}"}} {v}' for (p,s),v in sorted(counts.items())]
    lines += ['# TYPE eta_request_latency_seconds histogram']
    lines += [f'eta_request_latency_seconds_bucket{{le="{"+Inf" if b == float("inf") else b}"}} {latencies[b]}' for b in bounds]
    lines += [f'eta_request_latency_seconds_sum {total_time}',f'eta_request_latency_seconds_count {sum(counts.values())}']
    return PlainTextResponse('\n'.join(lines)+'\n',media_type='text/plain; version=0.0.4')
