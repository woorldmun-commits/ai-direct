"""One temporary host for Next.js, the API and an optional worker. A failed child stops the deployment."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]


def child_environment(env, role):
    shared={key:value for key,value in env.items()
            if key!='BOOTSTRAP_DATABASE_URL' and not (key.startswith('APP_') and key.endswith('_PASSWORD'))}
    if role=='web':
        allowed={'PATH','HOME','SYSTEMROOT','TEMP','TMP','TMPDIR','LANG','LC_ALL','NODE_ENV','NODE_OPTIONS',
                 'HOSTNAME','PORT','NEXT_TELEMETRY_DISABLED','INROU_API_URL','INROU_APP_ORIGIN',
                 'INROU_SESSION_COOKIE','INROU_CLIENT_IP_HEADER','API_PROXY_HMAC_KEY','INROU_DEMO',
                 'INROU_LOCAL_PREVIEW','INROU_STAGING'}
        return {key:value for key,value in shared.items() if key.upper() in allowed or key.startswith('NEXT_PUBLIC_')}
    if role=='api':
        return {key:value for key,value in shared.items() if key not in ('WORKER_DATABASE_URL','WORKER_QUEUE_DATABASE_URL')}
    if role=='worker':
        return {key:value for key,value in shared.items() if key!='API_DATABASE_URL'}
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
        if env.get('WORKER_ENABLED')=='1':
            env.setdefault('RELEASE_COMMIT_SHA',env.get('RENDER_GIT_COMMIT',''))
            env.setdefault('RELEASE_BUILD_ID',env.get('RENDER_GIT_COMMIT',''))
            children.append(subprocess.Popen([sys.executable,'-m','app.worker.runner'],cwd=ROOT/'backend',env=child_environment(env,'worker')))
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
