"""Create a private deployment env without overwriting an existing configuration."""
import argparse
import os
import re
import secrets
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--domain',required=True);a=p.parse_args()
if not re.fullmatch(r'(?=.{1,253}$)[a-zA-Z0-9][a-zA-Z0-9.-]*[a-zA-Z0-9]',a.domain):p.error('Use a hostname without https:// or a path')
out=Path(__file__).resolve().parent.parent/'.env'
content='\n'.join([f'SITE_DOMAIN={a.domain}',f'ALLOWED_HOSTS={a.domain}',f'CSRF_TRUSTED_ORIGINS=https://{a.domain}',
 'SECRET_KEY='+secrets.token_urlsafe(48),'DB_PASSWORD='+secrets.token_hex(24),
 'ADMIN_USERNAME=admin','ADMIN_PASSWORD='+secrets.token_urlsafe(18),
 'DEMO_USERNAME=reviewer','DEMO_PASSWORD='+secrets.token_urlsafe(18)])+'\n'
fd=os.open(out,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as f:f.write(content)
print('Создан .env с правами 0600. Пароли находятся только в этом файле. Не публикуйте его.')
