import uuid
import pytest
from fastapi.testclient import TestClient
import partA.eta_app as module
client=TestClient(module.app)
ROW=dict(distance_km=10,n_stops=3,hour=12,weekday=2,traffic_index=.3,rain=0,weight_kg=5)
URL='/v1/models/eta:predict'
def post(rows,**kw): return client.post(URL,json={'instances':rows},**kw)
def test_valid():
    r=post([ROW]); assert r.status_code==200; assert len(r.json()['predictions'])==1; assert r.json()['model_version']=='v1'
def test_order():
    b={**ROW,'distance_km':80}; assert post([b,ROW]).json()['predictions']==[post([b]).json()['predictions'][0],post([ROW]).json()['predictions'][0]]
@pytest.mark.parametrize('field,value',[('distance_km',0),('n_stops',1.2),('rain',2),('hour',24),('weight_kg',0),('traffic_index',1.1)])
def test_invalid(field,value):
    r=post([{**ROW,field:value}]); assert r.status_code==422; assert r.json()['error']=='validation_failed'; assert r.json()['details']
def test_missing(): assert client.post(URL,json={'instances':[{}]}).status_code==422
def test_infeasible():
    r=post([{**ROW,'distance_km':151,'n_stops':21}]); assert r.status_code==422; assert 'infeasible' in r.text
@pytest.mark.parametrize('n',[0,501])
def test_batch_limits(n): assert post([ROW]*n).status_code==422
def test_500_allowed(): assert post([ROW]*500).status_code==200
def test_echo():
    r=post([ROW],headers={'X-Request-ID':'customer-id'}); assert r.headers['X-Request-ID']==r.json()['request_id']=='customer-id'
@pytest.mark.parametrize('rows',[[ROW],[]])
def test_generated(rows):
    r=post(rows); assert str(uuid.UUID(r.json()['request_id']))==r.headers['X-Request-ID']
def test_error_echo():
    r=post([],headers={'X-Request-ID':'err'}); assert r.json()['request_id']==r.headers['X-Request-ID']=='err'
def test_metrics():
    post([ROW]); a=client.get('/metrics'); b=client.get('/metrics'); assert a.text==b.text
    for s in ['eta_requests_total{','eta_request_latency_seconds_bucket{le="+Inf"}','eta_request_latency_seconds_sum','eta_request_latency_seconds_count']: assert s in a.text
def test_generic_500(monkeypatch):
    def fail(*args): raise RuntimeError('SECRET')
    monkeypatch.setattr(module.model,'predict',fail)
    r=post([ROW]); assert r.status_code==500; assert 'SECRET' not in r.text; assert r.headers['X-Request-ID']==r.json()['request_id']
