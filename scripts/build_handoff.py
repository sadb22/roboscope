"""Generate documentation and reproducible sample reports from the release model."""
import json,os,re,sys
from pathlib import Path
from xml.sax.saxutils import escape
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT));os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django;django.setup()
from django.test import Client
from core.models import Product
from core.simulation import simulate
from core.reports import pdf_report,excel_report
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,PageBreak,Preformatted,Table,TableStyle,KeepTogether
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
out=ROOT/'output';out.mkdir(exist_ok=True)
c=Client();p=Product.objects.filter(name__contains='H1500').get()
result=c.post('/api/calculate/',json.dumps({'product_id':str(p.id),'inputs':{}}),content_type='application/json').json()
s=simulate(result,42,4);result['simulation_summary']={k:v for k,v in s.items() if k not in ['events','arrivals','completions','per_robot']}
(out/'sample-report.pdf').write_bytes(pdf_report(result))
(out/'sample-report.xlsx').write_bytes(excel_report(result))
(out/'sample-report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
result2=c.post('/api/calculate/',json.dumps({'product_id':str(p.id),'inputs':{'loading_bays':6,'corridor_capacity':14}}),content_type='application/json').json()
s2=simulate(result2,42,4);result2['simulation_summary']={k:v for k,v in s2.items() if k not in ['events','arrivals','completions','per_robot']}
(out/'improved-scenario.json').write_text(json.dumps(result2,ensure_ascii=False,indent=2))
fontdir=ROOT/'static/fonts'
for n,f in [('Doc','DejaVuSans.ttf'),('DocBold','DejaVuSans-Bold.ttf')]:pdfmetrics.registerFont(TTFont(n,str(fontdir/f)))
styles={
 'body':ParagraphStyle('body',fontName='Doc',fontSize=9.2,leading=14,spaceAfter=7,textColor=colors.HexColor('#23364b')),
 'h1':ParagraphStyle('h1',fontName='DocBold',fontSize=23,leading=29,spaceAfter=19,keepWithNext=True),
 'h2':ParagraphStyle('h2',fontName='DocBold',fontSize=13,leading=18,spaceBefore=15,spaceAfter=9,keepWithNext=True),
 'code':ParagraphStyle('code',fontName='Doc',fontSize=7.2,leading=11,backColor=colors.HexColor('#eef2f7'),spaceAfter=8,borderPadding=7),
}
def clean(x):
 x=x.replace('**','').replace('`','')
 return re.sub(r'\[([^\]]+)\]\(([^)]+)\)',r'\1 (\2)',x)
def para(s,style='body'):return Paragraph(escape(clean(s)),styles[style])
story=[para('Робоскоп','h1'),para('Документация релиза 1.0','h2'),para('Предварительная оценка роботизации склада. Хакатон ФЦ БАС, сентябрь 2026.'),
 para('Комплект описывает расчёт, данные, пользовательские действия, API и развёртывание. Полная модель относится к перемещению паллет в одноэтажной зоне склада.'),
 para('Статус размещения','h2'),para('Локальное приложение и комплект развёртывания готовы. Публичный сервер и домен на момент формирования документа не предоставлены. HTTPS и работа серверного Docker-стека требуют проверки на целевом VPS.'),
 para('Содержание','h2')]
files=['README.md','docs/USER_GUIDE.md','docs/MODEL.md','docs/ARCHITECTURE.md','docs/DEPLOYMENT.md','docs/SOURCES.md','docs/RELEASE_CHECKLIST.md']
for i,name in enumerate(files):
 title=(ROOT/name).read_text().splitlines()[0].lstrip('# ');story.append(para(f'{i+1}. {title}'))
story.append(para('Демонстрационный расчёт','h2'))
story.append(para('Исходный склад: 20 000 м², 2 000 перемещений/сутки, 22 ч/сутки, пик 1,5. Цена H1500 2,7 млн ₽. Расчёт: 17 роботов и 4 зарядные станции. Покупка: CAPEX 56,815 млн ₽, TCO 228,2606 млн ₽ за 5 лет. Исходная схема не проходит симуляцию.'))
story.append(para('Проверка исправленной схемы','h2'))
story.append(para('При 6 параллельных местах погрузки и ёмкости общего проезда 14 роботов прогон seed=42, 4 часа даёт 524 выполненные задачи из 532 поступивших, 8 в работе и 0 в очереди. Пропускная способность 131 операций/ч при целевом потоке 136,36. Выполнен принятый критерий 95%. Изменение планировки является допущением, его стоимость требует обследования.'))
for name in files:
 story.append(PageBreak());incode=False;code=[]
 for line in (ROOT/name).read_text().splitlines():
  if line.startswith('```'):
   if incode:
    for ln in code:story.append(para(ln,'code'))
    code=[]
   incode=not incode;continue
  if incode:code.append(line);continue
  if not line.strip():continue
  if line.startswith('# '):story.append(para(line[2:],'h1'))
  elif line.startswith('## '):story.append(para(line[3:],'h2'))
  elif line.startswith('### '):story.append(para(line[4:],'h2'))
  else:story.append(para(line))

def footer(can,doc):
 can.setFont('Doc',8);can.setFillColor(colors.HexColor('#78879a'));can.drawString(42,25,'Робоскоп 1.0 / документация / 17.09.2026');can.drawRightString(553,25,str(doc.page))
SimpleDocTemplate(str(out/'documentation.pdf'),pagesize=(595.28,841.89),leftMargin=42,rightMargin=42,topMargin=42,bottomMargin=45,title='Робоскоп: документация').build(story,onFirstPage=footer,onLaterPages=footer)
print('Created documentation.pdf, sample-report.pdf/.xlsx/.json, improved-scenario.json')
