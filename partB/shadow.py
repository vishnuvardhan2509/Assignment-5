import os,subprocess,time,sys,json
import requests,pandas as pd,numpy as np
from eta_data import FEATURES

def main():
    procs=[]
    try:
        for alias,port in [('prod',5101),('candidate',5102)]:
            env={**os.environ,'PATH':str(__import__('pathlib').Path(sys.executable).parent)+os.pathsep+os.environ['PATH'],'MLFLOW_TRACKING_URI':os.getenv('MLFLOW_TRACKING_URI','sqlite:///mlflow.db')}
            p=subprocess.Popen([sys.executable,'-m','mlflow','models','serve','-m',f'models:/eta-model@{alias}','-p',str(port),'--env-manager','local','--host','127.0.0.1'],env=env,stdout=open(f'mlflow_{alias}.log','w'),stderr=subprocess.STDOUT,start_new_session=True);procs.append(p)
        for port in [5101,5102]:
            for _ in range(120):
                if any(p.poll() is not None for p in procs): raise RuntimeError('MLflow server exited; see mlflow_prod.log and mlflow_candidate.log')
                try:
                    if requests.get(f'http://127.0.0.1:{port}/ping',timeout=1).status_code==200:break
                except requests.RequestException:pass
                time.sleep(.5)
            else:raise RuntimeError('MLflow startup timeout')
        rows=pd.read_csv('data/eta_fresh.csv')[FEATURES].head(200).to_dict('records')
        predictions=[[],[]];times=[[],[]]
        sessions=[requests.Session(),requests.Session()]
        for row in rows:
            for i,port in enumerate([5101,5102]):
                start=time.perf_counter();r=sessions[i].post(f'http://127.0.0.1:{port}/invocations',json={'dataframe_records':[row]},timeout=30);times[i].append((time.perf_counter()-start)*1000);r.raise_for_status();predictions[i].append(r.json()['predictions'][0]['eta_minutes'])
        diff=np.abs(np.array(predictions[0])-predictions[1])
        print(json.dumps({'requests_each':200,'mean_absolute_difference_minutes':float(diff.mean()),'percent_over_10_minutes':float((diff>10).mean()*100),'prod_p95_ms':float(np.percentile(times[0],95)),'candidate_p95_ms':float(np.percentile(times[1],95))},indent=2))
    finally:
        import signal
        for p in procs:
            if p.poll() is None:os.killpg(p.pid,signal.SIGTERM);p.wait(timeout=30)
if __name__=='__main__':main()
