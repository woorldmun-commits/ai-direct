from types import SimpleNamespace

from starlette.testclient import TestClient

from app.api import middleware


def test_callback_limit_is_retryable_bounded_and_does_not_block_other_routes(monkeypatch):
    now = [100.0]
    calls = []
    monkeypatch.setattr(middleware, 'CALLBACKS_PER_MINUTE', 2)
    monkeypatch.setattr(middleware, 'monotonic', lambda: now[0])

    async def downstream(scope, receive, send):
        if scope['type'] == 'lifespan':
            while True:
                message = await receive()
                await send({'type': message['type'] + '.complete'})
                if message['type'] == 'lifespan.shutdown':
                    return
        calls.append(scope['path'])
        await send({'type': 'http.response.start', 'status': 200, 'headers': []})
        await send({'type': 'http.response.body', 'body': b'{}'})

    settings = SimpleNamespace(hsts=False, proxy_hmac_key=None, max_body_bytes=1024, allowed_origins=())
    app = middleware.BoundaryMiddleware(downstream, settings)
    callback = '/api/v1/billing/yookassa/webhook'
    with TestClient(app) as client:
        assert client.post(callback, json={}).status_code == 200
        assert client.post(callback, json={}).status_code == 200
        limited = client.post(callback, json={})
        assert limited.status_code == 503
        assert limited.json()['error']['code'] == 'billing_busy'
        assert calls.count(callback) == 2
        assert client.get('/health').status_code == 200
        now[0] += 60
        assert client.post(callback, json={}).status_code == 200
        assert len(app.callback_times) <= 2
