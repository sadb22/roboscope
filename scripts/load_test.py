"""HTTP test with separate browser sessions; use only against your own instance."""
import argparse,concurrent.futures,http.cookiejar,json,time,urllib.request,statistics
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://127.0.0.1:8765');parser.add_argument('--users',type=int,default=50)
a=parser.parse_args();base=a.url.rstrip('/')
def session():
    jar=http.cookiejar.CookieJar();op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar));op.open(base+'/',timeout=15).read()
    token=next(c.value for c in jar if c.name=='csrftoken');return op,token

def request(op,token,path,data=None):
    req=urllib.request.Request(base+path,headers={'X-CSRFToken':token,'Content-Type':'application/json','Referer':base+'/'},data=json.dumps(data).encode() if data is not None else None)
    with op.open(req,timeout=75) as r:return json.load(r)

op,token=session();boot=request(op,token,'/api/bootstrap/');catalog=request(op,token,'/api/catalog/')
product=next(p for p in catalog['products'] if 'H1500' in p['name'])
payload={'inputs':boot['defaults'],'product_id':product['id']}
sessions=[session() for _ in range(a.users)]
def calculate(s):
    start=time.perf_counter();result=request(*s,'/api/calculate/',payload);assert result['fleet']['robots']>0;return time.perf_counter()-start
with concurrent.futures.ThreadPoolExecutor(max_workers=a.users) as pool:times=list(pool.map(calculate,sessions))
def sim(s):
    start=time.perf_counter();run=request(*s,'/api/simulations/',{**payload,'hours':4,'seed':42})
    while time.perf_counter()-start<75:
        result=request(*s,'/api/simulations/'+run['id']+'/')
        if result['status']=='failed':raise RuntimeError(result['error'])
        if result['status']=='done':return time.perf_counter()-start
        time.sleep(.3)
    raise TimeoutError('Simulation queue took more than 75 seconds')
with concurrent.futures.ThreadPoolExecutor(max_workers=a.users) as pool:simtimes=list(pool.map(sim,sessions))
def stats(values):return {'count':len(values),'max_seconds':round(max(values),3),'median_seconds':round(statistics.median(values),3),'p95_seconds':round(sorted(values)[max(0,int(len(values)*.95)-1)],3)}
out={'timestamp':time.strftime('%Y-%m-%d %H:%M:%S'),'url':base,'concurrent_users':a.users,'calculation':stats(times),'simulation_including_queue':stats(simtimes),'environment_note':'Repeat on target production VPS with PostgreSQL; local results do not verify hosting SLA.'}
Path('test-results').mkdir(exist_ok=True);Path('test-results/http-load.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out,indent=2));assert max(times)<10 and max(simtimes)<60
