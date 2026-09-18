"""Reproducible model verification. Run after migrate and seed_data."""
import json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT));os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django
django.setup()
from core.engine import calculate,defaults,product_dict
from core.models import Product
from core.simulation import simulate
p=product_dict(Product.objects.filter(name__contains='H1500').get())
results={}
for name,changes in [('default',{}),('improved',{'loading_bays':6,'corridor_capacity':14})]:
    values=defaults();values.update(changes)
    start=time.perf_counter();r=calculate(values,p);calc_seconds=time.perf_counter()-start
    start=time.perf_counter();sim=simulate(r,42,4);sim_seconds=time.perf_counter()-start
    assert sim['arrived']==sim['completed']+sim['queued']+sim['in_progress']
    assert calc_seconds<10 and sim_seconds<60
    assert sim['passed']==(name=='improved')
    results[name]={'calculation_seconds':calc_seconds,'simulation_seconds':sim_seconds,
        'robots':r['fleet']['robots'],'buy_capex':r['scenarios'][1]['capex'],
        'buy_tco':r['scenarios'][1]['tco'],'simulation':{k:v for k,v in sim.items() if k not in ['events','arrivals','completions','per_robot']}}
path=ROOT/'test-results';path.mkdir(exist_ok=True)
(path/'model-verification.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
print(json.dumps({k:{'robots':v['robots'],'throughput':v['simulation']['throughput'],'passed':v['simulation']['passed'],'calculation_seconds':round(v['calculation_seconds'],4),'simulation_seconds':round(v['simulation_seconds'],4)} for k,v in results.items()},ensure_ascii=False,indent=2))
