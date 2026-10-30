"""One temporary host for Next.js, the API and optional workers. A failed child stops the deployment."""
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def child_environment(env, role):
    shared={key:value for key,value in env.items()
            if key!='BOOTSTRAP_DATABASE_URL' and not (key.startswith('APP_') and key.endswith('_PASSWORD'))}
    if role=='web':
        allowed={'PATH','HOME','SYSTEMROOT','TEMP','TMP','TMPDIR','LANG','LC_ALL','NODE_ENV','NODE_OPTIONS',
                 'HOSTNAME','PORT','NEXT_TELEMETRY_DISABLED','INROU_API_URL','INROU_APP_ORIGIN',
                 'INROU_SESSION_COOKIE','INROU_CLIENT_IP_HEADER','API_PROXY_HMAC_KEY','INROU_DEMO',
                 'INROU_LOCAL_PREVIEW','INROU_STAGING','INROU_PUBLIC_CONTACT_EMAIL'}
        return {key:value for key,value in shared.items() if key.upper() in allowed or key.startswith('NEXT_PUBLIC_')}
    if role=='api':
        return {key:value for key,value in shared.items() if key not in ('WORKER_DATABASE_URL','WORKER_QUEUE_DATABASE_URL','RETENTION_DATABASE_URL')}
    if role=='worker':
        allowed={'PATH','HOME','SYSTEMROOT','TEMP','TMP','TMPDIR','LANG','LC_ALL','PYTHONUNBUFFERED',
                 'SSL_CERT_FILE','SSL_CERT_DIR','WORKER_DATABASE_URL','WORKER_QUEUE_DATABASE_URL',
                 'RELEASE_COMMIT_SHA','RELEASE_BUILD_ID','YANDEX_API_CLIENT_ID','YANDEX_API_CLIENT_SECRET',
                 'YANDEX_API_REDIRECT_URI','TOKEN_ENCRYPTION_KEY_VERSION','PILOT_WORKSPACE_IDS',
                 'PILOT_OPEN_ACCESS','PILOT_ACCESS_UNTIL','DIRECT_PLACEMENTS_REPORT'}
        return {key:value for key,value in shared.items() if key in allowed
                or key.startswith('TOKEN_ENCRYPTION_KEY_') and key[len('TOKEN_ENCRYPTION_KEY_'):].isdigit()}
    if role in ('auth_mail','product_mail'):
        allowed={'PATH','HOME','SYSTEMROOT','TEMP','TMP','TMPDIR','LANG','LC_ALL','PYTHONUNBUFFERED',
                 'SSL_CERT_FILE','SSL_CERT_DIR','WORKER_QUEUE_DATABASE_URL','INROU_EMAIL_ENABLED',
                 'INROU_EMAIL_ORIGIN','INROU_AUTH_HMAC_KEY','INROU_MAIL_PROVIDER','INROU_MAIL_API_KEY',
                 'INROU_SMTP_HOST','INROU_SMTP_PORT','INROU_SMTP_FROM','INROU_SMTP_USER','INROU_SMTP_PASSWORD',
                 'INROU_PRODUCT_EMAIL_ENABLED','PILOT_WORKSPACE_IDS','PILOT_OPEN_ACCESS','PILOT_ACCESS_UNTIL'}
        return {key:value for key,value in shared.items() if key in allowed}
    if role=='retention':
        allowed={'PATH','HOME','SYSTEMROOT','TEMP','TMP','TMPDIR','LANG','LC_ALL','PYTHONUNBUFFERED',
                 'RETENTION_DATABASE_URL','SSL_CERT_FILE','SSL_CERT_DIR'}
        return {key:value for key,value in shared.items() if key in allowed}
    raise ValueError('Unknown process role')


def main():
    env=dict(os.environ)
    env['INROU_LOCAL_PREVIEW']='false'
    host=env.get('RENDER_EXTERNAL_URL') or env.get('INROU_APP_ORIGIN')
    if not host:
        raise SystemExit('Configure INROU_APP_ORIGIN or use the Render service URL')
    env['INROU_APP_ORIGIN']=host.rstrip('/')
    env['NEXT_PUBLIC_SITE_URL']=host.rstrip('/')
    env.setdefault('API_ALLOWED_ORIGINS',host.rstrip('/'))
    sys.path.insert(0,str(ROOT/'backend'))
    if env.get('BOOTSTRAP_DATABASE_URL'):
        from bootstrap import provision
        env.update(provision(env))
    env['INROU_API_URL']='http://127.0.0.1:8081'
    children=[]
    stopping=False
    def stop(*_):
        nonlocal stopping
        stopping=True
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    try:
        if env.get('API_DATABASE_URL'):
            children.append(subprocess.Popen([sys.executable,'-m','uvicorn','app.api:create_app','--factory',
                '--host','127.0.0.1','--port','8081','--no-access-log','--no-proxy-headers'],cwd=ROOT/'backend',env=child_environment(env,'api')))
        if env.get('INROU_EMAIL_ENABLED','').lower() in ('1','true','yes'):
            children.append(subprocess.Popen([sys.executable,'-m','app.worker.auth_mail_runner'],
                cwd=ROOT/'backend',env=child_environment(env,'auth_mail')))
        if env.get('WORKER_ENABLED')=='1':
            env.setdefault('RELEASE_COMMIT_SHA',env.get('RENDER_GIT_COMMIT',''))
            env.setdefault('RELEASE_BUILD_ID',env.get('RENDER_GIT_COMMIT',''))
            children.append(subprocess.Popen([sys.executable,'-m','app.worker.runner'],cwd=ROOT/'backend',env=child_environment(env,'worker')))
        if env.get('INROU_PRODUCT_EMAIL_ENABLED')=='1':
            children.append(subprocess.Popen([sys.executable,'-m','app.worker.product_mail_runner'],
                cwd=ROOT/'backend',env=child_environment(env,'product_mail')))
        if env.get('RETENTION_ENABLED')=='1':
            children.append(subprocess.Popen([sys.executable,'-m','app.worker.retention_runner'],cwd=ROOT/'backend',env=child_environment(env,'retention')))
        web_env={**child_environment(env,'web'),'HOSTNAME':'0.0.0.0','PORT':env.get('PORT','10000')}
        children.append(subprocess.Popen(['node','server.js'],cwd=ROOT/'web',env=web_env))
        while not stopping:
            if any(child.poll() is not None for child in children):
                raise SystemExit('A service exited; restart the deployment after checking its logs.')
            time.sleep(0.5)
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()


if __name__=='__main__':
    main()
