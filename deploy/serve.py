"""One temporary host for Next.js, the API and an optional worker. A failed child stops the deployment."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]


def main():
    env=dict(os.environ)
    env['REKVERO_LOCAL_PREVIEW']='false'
    host=env.get('RENDER_EXTERNAL_URL') or env.get('REKVERO_APP_ORIGIN')
    if not host:
        raise SystemExit('Configure REKVERO_APP_ORIGIN or use the Render service URL')
    env['REKVERO_APP_ORIGIN']=host.rstrip('/')
    env['NEXT_PUBLIC_SITE_URL']=host.rstrip('/')
    env.setdefault('API_ALLOWED_ORIGINS',host.rstrip('/'))
    sys.path.insert(0,str(ROOT/'backend'))
    if env.get('BOOTSTRAP_DATABASE_URL'):
        from bootstrap import provision
        env.update(provision(env))
    # Parent bootstrap credentials are never inherited by the web/API/worker children.
    for key in list(env):
        if key=='BOOTSTRAP_DATABASE_URL' or key.startswith('APP_') and key.endswith('_PASSWORD'):
            env.pop(key)
    env['REKVERO_API_URL']='http://127.0.0.1:8081'
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
                '--host','127.0.0.1','--port','8081','--no-access-log','--no-proxy-headers'],cwd=ROOT/'backend',env=env))
        if env.get('WORKER_ENABLED')=='1':
            env.setdefault('RELEASE_COMMIT_SHA',env.get('RENDER_GIT_COMMIT',''))
            children.append(subprocess.Popen([sys.executable,'-m','app.worker.runner'],cwd=ROOT/'backend',env=env))
        web_env={**env,'HOSTNAME':'0.0.0.0','PORT':env.get('PORT','10000')}
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
