import argparse,sys,time
import numpy as np
import requests
ROW=dict(distance_km=10,n_stops=3,hour=12,weekday=2,traffic_index=.3,rain=0,weight_kg=5)
def main():
    p=argparse.ArgumentParser(); p.add_argument('--url',required=True); p.add_argument('--expect-version',required=True); p.add_argument('--max-p95-ms',type=float,default=80); a=p.parse_args()
    checks={}; times=[]
    def call(row):
        start=time.perf_counter(); r=requests.post(a.url,json={'instances':[row]},timeout=10); times.append((time.perf_counter()-start)*1000); r.raise_for_status(); return r.json()
    try:
        base=call(ROW); pred=base['predictions'][0]
        checks['version']=base['model_version']==a.expect_version
        checks['finite_positive']=bool(np.isfinite(pred) and pred>0)
        checks['distance_sanity']=call({**ROW,'distance_km':50})['predictions'][0]>=pred
        checks['traffic_sanity']=call({**ROW,'traffic_index':.9})['predictions'][0]>=pred
        checks['invalid_422']=requests.post(a.url,json={'instances':[{**ROW,'distance_km':-1}]},timeout=10).status_code==422
        for _ in range(50): call(ROW)
        checks['p95_latency']=float(np.percentile(times,95))<=a.max_p95_ms
        print('p95_ms:',float(np.percentile(times,95)))
    except Exception as e: checks['request_success']=False; print(type(e).__name__,str(e))
    for k,v in checks.items(): print(k, 'PASS' if v else 'FAIL')
    return 0 if len(checks)>=6 and all(checks.values()) else 1
if __name__=='__main__': sys.exit(main())
