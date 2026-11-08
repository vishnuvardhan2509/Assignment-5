import os, secrets
os.environ.setdefault("RAY_AUTH_TOKEN", secrets.token_urlsafe(32))
import ray, requests
from ray import serve
from partC.eta_ray import build
ROW=dict(distance_km=10,n_stops=3,hour=12,weekday=2,traffic_index=.3,rain=0,weight_kg=5)
def main():
    ray.init(num_cpus=2,include_dashboard=False)
    def deploy(w): serve.run(build(weight=w),route_prefix='/')
    def arm(i,beta=False):
        r=requests.post('http://127.0.0.1:8000/v1/models/eta:predict',json={'customer_id':str(i),'instances':[ROW]},headers={'X-Beta':'1'} if beta else {},timeout=30); r.raise_for_status(); return r.json()['arm']
    try:
        deploy(.2)
        original=[arm(i) for i in range(1000)]
        share=original.count('v2')/1000
        assert abs(share-.2)<=.04; print('candidate share:',share,flush=True)
        assert all(arm(i)==original[i] for i in range(200)); print('200 repeat customers: PASS',flush=True)
        deploy(.2)
        assert all(arm(i)==original[i] for i in range(200)); print('200 after redeploy: PASS',flush=True)
        deploy(.5)
        assert all(arm(i)=='v2' for i in range(1000) if original[i]=='v2'); print('no candidate returns to prod: PASS',flush=True)
        assert all(arm(i,True)=='v2' for i in range(50)); print('50 overrides: PASS',flush=True)
    finally: serve.shutdown(); ray.shutdown()
if __name__=='__main__': main()
