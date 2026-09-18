import csv
import io
import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from django.db import transaction
from .models import Product

def import_catalog(content):
    if isinstance(content, bytes):
        try: content=content.decode('utf-8-sig')
        except UnicodeDecodeError: content=content.decode('cp1251')
    try: dialect=csv.Sniffer().sniff(content[:5000], delimiters=';,\t')
    except csv.Error: dialect=csv.excel
    reader=csv.DictReader(io.StringIO(content),dialect=dialect)
    required={'id','Название','компания','Цена изделия'}
    if not required.issubset(set(reader.fieldnames or [])):
        raise ValueError('Нужны колонки: id, Название, компания, Цена изделия')
    groups=defaultdict(list)
    for n,row in enumerate(reader,2):
        if n>10002: raise ValueError('Не более 10 000 строк каталога')
        if not row.get('id') or not row.get('Название'): raise ValueError(f'Строка {n}: нет ID или названия')
        groups[row['id'].strip()].append({k:(v or '').strip() for k,v in row.items() if k is not None})
    with transaction.atomic():
        for id,rows in groups.items():
            first=rows[0]; price_text=first['Цена изделия'].replace(' ','').replace('\xa0','').replace(',','.')
            try: price=Decimal(price_text) if price_text else None
            except InvalidOperation: raise ValueError('Некорректная цена: '+first['Название'])
            if price is not None and (not price.is_finite() or price<0): raise ValueError('Цена должна быть неотрицательной')
            specs={}
            match=re.search(r'грузоподъемность до\s*([\d\s]+)\s*кг',first['Название'],re.I)
            if match: specs['payload_kg']=int(match.group(1).replace(' ',''))
            subtype=first.get('Подтип','')
            if subtype=='AMR' and specs.get('payload_kg',0)>=600:
                specs['pallet_transport']=True
                specs['assumed']=['pallet_transport']
            if 'H1500' in first['Название']:
                specs.update(payload_kg=1500,pallet_transport=True,max_speed_mps=1.5,min_temp_c=5,max_temp_c=25,
                             width_m=.654,min_aisle_m=1.5,assumed=['min_aisle_m'])
            if 'H2000' in first['Название']:
                specs.update(payload_kg=2000,pallet_transport=True)
            sources=[dict(title='catalog_export_v4.csv',date='2026-09-16',status='Данные организатора')]
            if 'H1500' in first['Название']:
                sources.append(dict(title='Примеры_решений_типы_объектов.docx',date='2026-09-16',status='Типовой пример; ширина прохода — допущение'))
                sources.append(dict(title='Ronavi Robotics · H1500',url='https://ronavi-robotics.ru/catalogue/h1500',date='2026-09-17',status='Производитель подтверждает груз 1500 кг, скорость 1,5 м/с и размер 1044×654×380 мм. Заявлены автономность до 10 ч и проход 750 мм; в модели сохранены консервативные 6 ч и 1,5 м. Цена от 2,16 млн ₽ относится к закупке от 100 шт.; использована исходная цена организатора.'))
            obj,created=Product.objects.get_or_create(source_id=id,defaults=dict(name=first['Название']))
            obj.name=first['Название'];obj.company=first['компания'];obj.price=price
            obj.kind=first.get('Тип','');obj.subtype=subtype;obj.status=first.get('статус','operation')
            obj.description=first.get('описание','')
            obj.applications=[dict(industry=r.get('Отрасль',''),process=r.get('Сценарий',''),case=r.get('Кейсы','')) for r in rows]
            obj.observations=rows
            obj.specs={**specs,**obj.specs}
            known={s['title'] for s in sources}
            obj.sources=sources+[s for s in obj.sources if s.get('title') not in known]
            obj.save()
    return dict(rows=sum(map(len,groups.values())),products=len(groups))
