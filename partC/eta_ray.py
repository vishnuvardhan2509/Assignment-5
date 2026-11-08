import hashlib, time
import joblib
import pandas as pd
from fastapi import FastAPI, Request
from ray import serve
from eta_schema import Batch

def bucket(customer_id):
    return int.from_bytes(hashlib.sha256(customer_id.encode()).digest()[:8],'big') / 2**64

@serve.deployment(ray_actor_options={'num_cpus':.25})
class EtaModel:
    def __init__(self,path,extra_work_ms=0):
        self.bundle=joblib.load(path)
        self.extra=extra_work_ms
    def predict(self,rows):
        if self.extra: time.sleep(self.extra/1000)
        b=self.bundle
        return {'predictions':[round(float(x),1) for x in b['model'].predict(pd.DataFrame(rows,columns=b['feature_columns']))],'model_version':b['version']}

api=FastAPI()
class CanaryBatch(Batch):
    customer_id: str

@serve.deployment(ray_actor_options={'num_cpus':.25})
@serve.ingress(api)
class Router:
    def __init__(self,prod,cand,weight): self.prod,self.cand,self.weight=prod,cand,weight
    @api.post('/v1/models/eta:predict')
    async def predict(self,body:CanaryBatch,request:Request):
        beta=request.headers.get('X-Beta')=='1' or bucket(body.customer_id)<self.weight
        handle=self.cand if beta else self.prod
        out=await handle.predict.remote([r.model_dump() for r in body.instances])
        return {**out,'arm':'v2' if beta else 'v1'}

def build(weight=.1,extra_work_ms=0.):
    if not 0 <= weight <= 1: raise ValueError('weight must be in [0,1]')
    prod=EtaModel.options(name='prod',num_replicas=2).bind('data/eta_v1.joblib',extra_work_ms)
    cand=EtaModel.options(name='candidate',autoscaling_config={'min_replicas':1,'max_replicas':3,'target_ongoing_requests':2,'upscale_delay_s':5,'downscale_delay_s':30}).bind('data/eta_v2.joblib',extra_work_ms)
    return Router.bind(prod,cand,weight)
