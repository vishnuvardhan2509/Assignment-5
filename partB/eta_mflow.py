import os, time
import numpy as np
import pandas as pd
import mlflow
from mlflow import MlflowClient
from mlflow.models import infer_signature
from eta_data import make_data, FEATURES

mlflow.set_tracking_uri(os.getenv('MLFLOW_TRACKING_URI','sqlite:///mlflow.db'))
class ETAWrapper(mlflow.pyfunc.PythonModel):
    def load_context(self, context):
        import joblib
        self.bundle = joblib.load(context.artifacts['bundle'])
    def predict(self, context, model_input, params=None):
        b=self.bundle
        return pd.DataFrame({'eta_minutes':np.round(b['model'].predict(model_input[b['feature_columns']]),1),'model_version':b['version']})

def register():
    import importlib.metadata as meta
    client=MlflowClient()
    sample=make_data(5)[FEATURES]
    result=[]
    for alias,version in [('prod','v1'),('candidate','v2')]:
        import joblib
        b=joblib.load(f'data/eta_{version}.joblib')
        output=pd.DataFrame({'eta_minutes':np.round(b['model'].predict(sample),1),'model_version':version})
        with mlflow.start_run():
            info=mlflow.pyfunc.log_model(name=f'eta_{version}',python_model=ETAWrapper(),artifacts={'bundle':os.path.abspath(f'data/eta_{version}.joblib')},signature=infer_signature(sample,output),input_example=sample,pip_requirements=[f'{p}=={meta.version(p)}' for p in ['mlflow','scikit-learn','pandas','numpy','joblib','cloudpickle']],code_paths=['eta_data.py'])
            mv=mlflow.register_model(info.model_uri,'eta-model')
            client.set_registered_model_alias('eta-model',alias,mv.version)
            result.append({'version':mv.version,'alias':alias,'bundle':version})
    return result

def decide(prod,cand,min_rel_gain=.03,max_p95_ms=10.,max_slice_regression=.05):
    criteria={'overall_gain':cand['mae'] <= prod['mae']*(1-min_rel_gain),'latency':cand['p95_ms'] <= max_p95_ms,'rush_slice':cand['mae_rush'] <= prod['mae_rush']*(1+max_slice_regression),'rain_slice':cand['mae_rain'] <= prod['mae_rain']*(1+max_slice_regression)}
    return {'criteria':criteria,'promote':all(criteria.values())}

def promotion_gate(**thresholds):
    df=make_data(2000,seed=99)
    metrics=[]
    for alias in ['prod','candidate']:
        m=mlflow.pyfunc.load_model(f'models:/eta-model@{alias}')
        pred=m.predict(df[FEATURES]).eta_minutes.to_numpy()
        err=np.abs(df.eta_minutes.to_numpy()-pred)
        times=[]
        for i in range(200):
            start=time.perf_counter(); m.predict(df[FEATURES].iloc[[i]]); times.append((time.perf_counter()-start)*1000)
        metrics.append({'mae':float(err.mean()),'mae_rush':float(err[df.hour.isin([7,8,9,16,17,18,19])].mean()),'mae_rain':float(err[df.rain==1].mean()),'p95_ms':float(np.percentile(times,95))})
    return {'prod':metrics[0],'candidate':metrics[1],**decide(*metrics,**thresholds)}

if __name__=='__main__':
    import json
    print(json.dumps({'registry':register(),'default':promotion_gate(),'gain_60_percent':promotion_gate(min_rel_gain=.60)},indent=2))
