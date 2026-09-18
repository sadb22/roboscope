import math
from datetime import datetime, timezone
from .schema import FIELDS, INTEGERS, MODEL_VERSION, DATA_VERSION, FORMULAS

class InputError(ValueError):
    def __init__(self, errors):
        self.errors = errors
        super().__init__('Проверьте параметры: ' + '; '.join(errors.values()))

def defaults():
    from .models import Normative
    values = {f['key']: f['default'] for f in FIELDS}
    for n in Normative.objects.all():
        if n.key in values: values[n.key] = n.value
    return values

def validate(raw, base=None):
    if not isinstance(raw, dict): raise InputError({'inputs': 'Ожидается объект с параметрами'})
    values = dict(base or {f['key']: f['default'] for f in FIELDS})
    errors = {}
    for f in FIELDS:
        key = f['key']
        v = raw.get(key, values[key])
        if f.get('type') == 'choice':
            if v not in f['choices']: errors[key] = f"{f['label']}: выберите значение из списка"
            else: values[key] = v
            continue
        try:
            if isinstance(v, bool): raise ValueError()
            v = float(str(v).replace(' ', '').replace('\u00a0', '').replace(',', '.'))
            if not math.isfinite(v) or not f['min'] <= v <= f['max']: raise ValueError()
            if key in INTEGERS and v != int(v): raise ValueError()
            values[key] = int(v) if key in INTEGERS else v
        except (ValueError, TypeError):
            errors[key] = f"{f['label']}: от {f['min']} до {f['max']} {f['unit']}" + ('; целое число' if key in INTEGERS else '')
    unknown = set(raw) - set(values)
    if unknown: errors['unknown'] = 'Неизвестные поля: ' + ', '.join(sorted(unknown))
    if values['active_area'] > values['area']: errors['active_area'] = 'Рабочая зона не может быть больше склада'
    if values['pallet_width']/1000 >= values['aisle_width']: errors['pallet_width'] = 'Ширина груза должна быть меньше ширины прохода'
    if errors: raise InputError(errors)
    return values

def product_dict(p):
    return dict(id=str(p.id), source_id=p.source_id, name=p.name, company=p.company,
                kind=p.kind, subtype=p.subtype, status=p.status, description=p.description,
                price=float(p.price) if p.price is not None else None, applications=p.applications,
                specs=p.specs, sources=p.sources, updated_at=p.updated_at.isoformat(),
                price_conflict=len({r.get('Цена изделия') for r in p.observations if r.get('Цена изделия')}) > 1)

def applicability(p, v, object_type='warehouse'):
    spec = p.get('specs', {})
    hay = (' '.join(str(a) for a in p.get('applications', [])) + ' ' + p.get('description', '') + ' ' + p.get('subtype', '')).lower()
    allowed = {'warehouse': ['склад', 'сортиров', 'погруз', 'amr', 'паллет', 'уборк'],
               'airport': ['уборк', 'достав', 'багаж', 'тягач', 'аэропорт', 'грузовик', 'amr'],
               'hospital': ['уборк', 'достав', 'медицин', 'биоматериал', 'amr']}
    relevant = any(s in hay for s in allowed.get(object_type, []))
    issues, reasons, missing = [], [], []
    if not relevant: issues.append('Назначение продукта не соответствует выбранному объекту')
    elif object_type != 'warehouse':
        reasons.append('Есть потенциально применимый процесс; требуется проверка специфики объекта')
        missing.append('Допуски, маршруты и интеграции этого объекта не проверены')
    if object_type == 'warehouse':
        if v.get('floors',1)>1: issues.append('Эта модель маршрута поддерживает один этаж; выделите одноэтажную зону')
        if v.get('wms','Да')=='Нет': missing.append('Нет WMS: требуется проект управления заданиями и интеграции')
        if v.get('floor_type') in ['Асфальт','Другое']: missing.append('Покрытие пола требует подтверждения производителя')
        if v.get('floor_deviation',0)>3: missing.append('Неровность пола выше демонстрационного допуска 3 мм/2 м')
        if not spec.get('pallet_transport'):
            issues.append('Нет подтверждённой функции перевозки паллет между зонами')
        else: reasons.append('Перемещение паллет соответствует выбранному процессу')
        for key, value, cmp, message in [
            ('payload_kg', v['payload_kg'], lambda limit,x: x <= limit, 'Грузоподъёмность'),
            ('min_aisle_m', v['aisle_width'], lambda limit,x: x >= limit, 'Ширина прохода'),
            ('min_temp_c', v['temperature'], lambda limit,x: x >= limit, 'Минимальная температура'),
            ('max_temp_c', v['temperature'], lambda limit,x: x <= limit, 'Максимальная температура')]:
            if key not in spec: missing.append(message + ': характеристика не подтверждена')
            elif not cmp(float(spec[key]), value): issues.append(message + ': параметры объекта за пределами допустимого')
            else: reasons.append(message + ': соответствует исходной характеристике')
    if p['status'] != 'operation': missing.append('Статус продукта: пилотирование или разработка')
    if p.get('price') is None: missing.append('Нет цены оборудования')
    if p.get('price_conflict'): missing.append('В каталоге несколько цен; выбранная цена требует проверки')
    if spec.get('assumed'): missing.append('Часть технических ограничений принята как допущение')
    score_parts = dict(process=40 if relevant and (object_type!='warehouse' or spec.get('pallet_transport')) else 0,
                       payload=25 if 'payload_kg' in spec and spec['payload_kg'] >= v['payload_kg'] else 0,
                       data=20 if all(k in spec for k in ['min_aisle_m','min_temp_c','max_temp_c']) else 5,
                       maturity=15 if p['status']=='operation' else 5)
    return dict(state='excluded' if issues else ('review' if missing else 'suitable'), reasons=reasons,
                issues=issues, missing=missing, score=0 if issues else sum(score_parts.values()), factors=score_parts)

def calculate(v, product, include_sensitivity=True):
    """Pure deterministic model; annual expenses include the residual manual process."""
    match = applicability(product, v)
    if match['issues']: raise InputError({'product': '; '.join(match['issues'])})
    limit = product.get('specs', {}).get('max_speed_mps')
    if limit is not None and v['speed'] > limit:
        raise InputError({'speed': f'Скорость выше указанного максимума модели: {limit} м/с'})
    price = v['robot_price'] or product.get('price')
    if not price or price <= 0: raise InputError({'robot_price': 'Укажите положительную цену робота'})
    cycle = 2*v['distance']/v['speed'] + v['handling_seconds']
    availability = v['battery_hours']/(v['battery_hours']+v['charge_minutes']/60)
    robot_capacity = 3600/cycle*availability
    demand = v['daily_moves']/v['hours_day']*v['peak_factor']
    recommended = math.ceil(demand/(robot_capacity*v['utilization']/100)*(1+v['reserve_pct']/100))
    count = int(v['robots_override']) or recommended
    chargers = math.ceil(count/v['robots_per_charger'])
    salary_year = v['salary']*12*v['payroll_factor']
    labor_before = v['staff']*salary_year
    released_fte = v['staff']*v['released_pct']/100
    saved_fte = released_fte*v['cash_realization_pct']/100
    labor_remaining = labor_before - saved_fte*salary_year
    support = v['support_staff']*salary_year
    electricity = count*v['power_kw']*v['hours_day']*v['days_year']*v['electricity_price']
    items = {'Роботы': count*price, 'Зарядные станции': chargers*v['charger_price'],
             'Инфраструктура': v['infrastructure'], 'ПО': v['software'], 'Интеграция и запуск': v['integration'],
             'Обучение': v['training']}
    items['Резерв внедрения'] = sum(items.values())*v['capex_reserve_pct']/100
    capex = sum(items.values())
    buy_opex = {'Оставшийся персонал процесса': labor_remaining, 'Операторы роботов': support,
                'Сервис': count*price*v['maintenance_pct']/100, 'Лицензии и связь': v['licenses_year'],
                'Электроэнергия': electricity}
    service_opex = {'Оставшийся персонал процесса': labor_remaining, 'Операторы роботов': support,
                    'Платёж за услугу': count*v['raas_month']*12, 'Электроэнергия': electricity}
    horizon = int(v['horizon'])
    scenarios = []
    for key, label, investment, opex, breakdown in [
        ('baseline','Текущий процесс',0,{'Персонал процесса':labor_before},{}),
        ('buy','Покупка',capex,buy_opex,items),
        ('service','Услуга',v['raas_setup'],service_opex,{'Запуск услуги':v['raas_setup']})]:
        annual = sum(opex.values())
        effect = labor_before-annual
        cumulative = -investment
        flow = []
        for year in range(1,horizon+1):
            replacement = count*v['battery_price'] if key=='buy' and year%int(v['battery_years'])==0 else 0
            year_effect = effect-replacement
            cumulative += year_effect
            flow.append(dict(year=year, opex=annual, replacement=replacement, effect=year_effect, cumulative=cumulative))
        accumulated = sum(y['effect'] for y in flow)
        scenarios.append(dict(key=key, label=label, capex=investment, opex=annual, annual_effect=effect,
             payback=investment/effect if investment>0 and effect>0 else None,
             roi=accumulated/investment*100 if investment>0 else None,
             net_roi=(accumulated-investment)/investment*100 if investment>0 else None,
             tco=investment+sum(y['opex']+y['replacement'] for y in flow),
             net_effect=cumulative, capex_items=breakdown, opex_items=opex, cashflow=flow))
    warnings = list(match['missing'])
    if product.get('specs',{}).get('payload_kg') is None: warnings.append('Грузоподъёмность продукта не подтверждена')
    if 'H1500' not in product['name']:
        warnings.append('Рабочая скорость, автономность и зарядка — параметры сценария; сверьте их с выбранной моделью')
    if count<recommended: warnings.append('Ручное количество роботов ниже расчётного: проверьте пиковую нагрузку симуляцией')
    if capex>v['budget']: warnings.append('Первоначальные вложения при покупке превышают бюджет')
    if count>80: warnings.append('Симуляция этой версии поддерживает до 80 роботов; выделите меньшую рабочую зону')
    warnings.append('Производительность зависит от очередей и планировки; расчётная оценка проверяется симуляцией')
    if saved_fte > 0: warnings.append(f'Денежная экономия предполагает сокращение расходов на {saved_fte:.2f} штатных единиц')
    result = dict(model_version=MODEL_VERSION, data_version=DATA_VERSION, calculated_at=datetime.now(timezone.utc).isoformat(),
                  inputs=v, product=product, scenarios=scenarios, formulas=FORMULAS, warnings=warnings,
                  fleet=dict(robots=count, recommended=recommended, chargers=chargers, peak_demand=demand,
                             cycle_seconds=cycle, per_robot_capacity=robot_capacity,
                             designed_capacity=count*robot_capacity*v['utilization']/100,
                             released_fte=released_fte, saved_fte=saved_fte), sensitivity=[])
    if include_sensitivity:
        for key,label in [('robot_price','Цена оборудования'),('daily_moves','Объём операций'),('salary','Стоимость труда')]:
            for delta in [-20,0,20]:
                changed=dict(v); changed[key]=(price if key=='robot_price' else v[key])*(1+delta/100)
                varied=calculate(changed,product,False)
                result['sensitivity'].append(dict(parameter=key,label=label,delta=delta, robots=varied['fleet']['robots'],
                    scenarios=[{k:s[k] for k in ['key','tco','annual_effect','payback','roi']} for s in varied['scenarios']]))
    return result
