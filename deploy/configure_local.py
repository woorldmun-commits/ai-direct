"""Create local secrets once, without printing them. Does not provision or publish a server."""
import base64
import secrets
from pathlib import Path


def main():
    target=Path(__file__).with_name('.env')
    values={f'{role}_PASSWORD':secrets.token_urlsafe(32)
            for role in ('APP_MIGRATOR','APP_RW','APP_TOKEN','APP_SYSTEM','APP_DELETER')}
    password=secrets.token_urlsafe(32)
    values.update(POSTGRES_PASSWORD=password,
        BOOTSTRAP_DATABASE_URL=f'postgresql://postgres:{password}@db:5432/inrou',
        INROU_APP_ORIGIN='http://localhost:10000',API_HSTS='0',PORT='10000',
        YANDEX_LOGIN_ENABLED='0',YANDEX_API_ENABLED='0',WORKER_ENABLED='0',INROU_EMAIL_ENABLED='false',
        TOKEN_ENCRYPTION_KEY_VERSION='1',TOKEN_ENCRYPTION_KEY_1=base64.b64encode(secrets.token_bytes(32)).decode(),
        API_PROXY_HMAC_KEY=secrets.token_urlsafe(32),PILOT_WORKSPACE_IDS='',PILOT_ACCESS_UNTIL='')
    # Exclusive creation preserves existing credentials and the ability to decrypt stored tokens.
    with target.open('x',encoding='utf-8',newline='\n') as out:
        out.write('\n'.join(f'{key}={value}' for key,value in values.items())+'\n')
    print(f'Created {target}. Keep this file private and back it up securely.')


if __name__=='__main__':
    main()
