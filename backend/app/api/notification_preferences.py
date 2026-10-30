from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, StrictBool

from app.api.deps import Conn, CurrentWorkspace
from app.api.errors import ApiError

router = APIRouter()


class Preference(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: StrictBool


@router.get('/workspaces/{workspace_id}/email-preference')
def read_preference(request: Request, conn: Conn, ws: CurrentWorkspace):
    available = conn.execute('SELECT product_email_available(%s,%s)', (ws.actor.user_id, ws.id)).fetchone()[0]
    row = conn.execute('SELECT enabled FROM workspace_email_preferences WHERE workspace_id=%s AND user_id=%s',
                       (ws.id, ws.actor.user_id)).fetchone()
    return {'enabled': bool(row and row[0]), 'email_verified': available,
            'delivery_configured': bool(request.app.state.settings.email_auth)
                and request.app.state.settings.product_email_enabled}


@router.post('/workspaces/{workspace_id}/email-preference')
def save_preference(body: Preference, request: Request, conn: Conn, ws: CurrentWorkspace):
    current = read_preference(request, conn, ws)
    if body.enabled and not current['email_verified']:
        raise ApiError(409, 'verified_email_required', message='Для сервисных писем нужен подтверждённый email.')
    conn.execute('''INSERT INTO workspace_email_preferences(workspace_id,user_id,enabled) VALUES(%s,%s,%s)
        ON CONFLICT(workspace_id,user_id) DO UPDATE SET enabled=EXCLUDED.enabled,updated_at=now()''',
        (ws.id, ws.actor.user_id, body.enabled))
    return {**current, 'enabled': body.enabled}
