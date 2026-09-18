"""Discrete-event validation of the same route/cycle used by the economic model."""
import random
import math
import simpy

def simulate(calculation, seed=42, hours=4):
    v=calculation['inputs'];fleet=calculation['fleet'];n=fleet['robots']
    if not 1<=n<=80: raise ValueError('Симуляция поддерживает 1–80 роботов. Уменьшите рабочую зону или нагрузку.')
    hours=float(hours)
    if not .25<=hours<=8: raise ValueError('Горизонт симуляции: от 0,25 до 8 часов')
    horizon=hours*3600
    peak=fleet['peak_demand']
    if peak*hours>20000: raise ValueError('Не более 20 000 операций за прогон: уменьшите горизонт или поток')
    rng=random.Random(int(seed));env=simpy.Environment();jobs=simpy.Store(env)
    bays=simpy.Resource(env,int(v['loading_bays']))
    corridor=simpy.Resource(env,int(v['corridor_capacity']))
    chargers=simpy.Resource(env,fleet['chargers'])
    events=[];arrivals=[];completions=[];waits=[]
    counts=[0]*n
    busy=[0.0]*n
    waits_resource=[0.0]*n
    charging=[0.0]*n
    states=['idle']*n
    active_jobs=set()
    def segment(robot,state,start,end,a='load',b='load'):
        if end>start:
            events.append(dict(robot=robot,state=state,start=round(start,3),end=round(min(end,horizon),3),a=a,b=b))
    def duration(robot,state,seconds,a='load',b='load'):
        start=env.now;states[robot]=state
        segment(robot,state,start,start+seconds,a,b)
        yield env.timeout(seconds)
    def source():
        while env.now<horizon:
            yield env.timeout(rng.expovariate(peak/3600))
            arrivals.append(round(env.now,3));yield jobs.put((len(arrivals),env.now))
    def travel(i,outbound):
        start=env.now
        with corridor.request() as req:
            yield req
            waits_resource[i]+=env.now-start
            segment(i,'waiting',start,env.now,'load' if outbound else 'drop','load' if outbound else 'drop')
            yield env.process(duration(i,'travel',v['distance']/v['speed'],'load' if outbound else 'drop','drop' if outbound else 'load'))
    def handling(i,place):
        start=env.now
        with bays.request() as req:
            yield req
            waits_resource[i]+=env.now-start;segment(i,'waiting',start,env.now,place,place)
            yield env.process(duration(i,'handling',v['handling_seconds']/2,place,place))
    def robot(i):
        # Stagger initial charge state deterministically to avoid an artificial simultaneous outage.
        battery_elapsed=i/max(n,1)*v['battery_hours']*3600*.8
        while env.now<horizon:
            if battery_elapsed>=v['battery_hours']*3600:
                start=env.now
                with chargers.request() as req:
                    yield req
                    segment(i,'waiting',start,env.now,'charge','charge');waits_resource[i]+=env.now-start
                    charging[i]+=min(v['charge_minutes']*60,horizon-env.now)
                    yield env.process(duration(i,'charging',v['charge_minutes']*60,'charge','charge'))
                battery_elapsed=0
            start=env.now;states[i]='idle'
            job,created=yield jobs.get()
            segment(i,'idle',start,env.now)
            waits.append(env.now-created);active_jobs.add(job)
            start=env.now
            yield env.process(handling(i,'load'))
            yield env.process(travel(i,True))
            yield env.process(handling(i,'drop'))
            # Completion at drop; robot still must return before taking the next job.
            completions.append(dict(time=round(env.now,3),robot=i,job=job));counts[i]+=1;active_jobs.discard(job)
            yield env.process(travel(i,False))
            battery_elapsed+=fleet['cycle_seconds']
            busy[i]+=env.now-start
    env.process(source())
    for i in range(n):env.process(robot(i))
    env.run(until=horizon)
    # Segments can extend past the horizon; aggregate the actually observed interval.
    totals={s:0.0 for s in ['travel','handling','waiting','charging','idle']}
    robot_active=[0.0]*n
    for e in events:
        d=max(0,min(e['end'],horizon)-e['start']);totals[e['state']]+=d
        if e['state'] in ['travel','handling']:robot_active[e['robot']]+=d
    # Pending idle/resource requests are not completed events: include final tails.
    for i in range(n):
        mine=[e for e in events if e['robot']==i]
        end=max((e['end'] for e in mine),default=0)
        if end<horizon:segment(i,'idle' if states[i]=='idle' else 'waiting',end,horizon)
    durations={s:sum(e['end']-e['start'] for e in events if e['state']==s) for s in totals}
    actual=len(completions)/hours
    backlog=len(jobs.items)
    sorted_waits=sorted(waits)
    p95=sorted_waits[min(len(sorted_waits)-1,int(len(sorted_waits)*.95))]/60 if waits else 0
    # The horizon includes warm-up; report backlog explicitly instead of claiming validation from animation.
    passed=actual>=peak*.95 and backlog<=max(3,peak*.05)
    bottlenecks=[]
    if durations['waiting']/(n*horizon)>.15:bottlenecks.append('Ожидание общего проезда или мест погрузки')
    if backlog>max(3,peak*.05):bottlenecks.append('Очередь необработанных задач растёт при пиковом потоке')
    if p95>5:bottlenecks.append('95% задач начинают выполняться с задержкой до '+str(round(p95,1))+' мин')
    return dict(seed=int(seed),hours=hours,duration=horizon,robots=n,chargers=fleet['chargers'],
        expected_throughput=peak,throughput=actual,arrived=len(arrivals),completed=len(completions),
        queued=backlog,in_progress=len(active_jobs),mean_wait_minutes=sum(waits)/max(1,len(waits))/60,
        p95_wait_minutes=p95,utilization=sum(robot_active)/(n*horizon)*100,
        state_shares={s:round(d/(n*horizon)*100,2) for s,d in durations.items()},
        passed=passed,bottlenecks=bottlenecks,events=sorted(events,key=lambda e:e['start']),
        arrivals=arrivals,completions=completions,per_robot=counts,
        model_version=calculation['model_version'],
        notes=['Моделируется постоянный пиковый поток, поступление задач случайное с фиксированным seed.',
               'Общий проезд и места погрузки имеют ограниченную ёмкость; показана типовая схема.',
               'Батарея расходуется на рабочие циклы; время зарядки и число станций взяты из расчёта.',
               'Критерий: выполнено не менее 95% ожидаемого потока, остаточная очередь не выше порога.',
               'Это проверка модельных предпосылок, а не подтверждение характеристик реального объекта.'])
