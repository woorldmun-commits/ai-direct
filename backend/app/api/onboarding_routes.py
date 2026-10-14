"""Personal workspace and business context; site URLs are stored, never fetched."""

from decimal import Decimal
from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastapi import APIRouter
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.deps import Conn, CurrentActor, CurrentWorkspace, require_manager
from app.api.errors import ApiError
from app.tenancy import set_local_workspace

router = APIRouter()
Money = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)]
ShortText = Annotated[str, Field(min_length=1, max_length=300)]


class WorkspaceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=120)


class BusinessProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    industry: Literal["services", "retail", "ecommerce", "health", "education", "property", "b2b", "other"] = "other"
    custom_industry: str | None = Field(default=None, max_length=120)
    business_model: Literal["leads", "ecommerce", "b2b", "subscription"] = "leads"
    site_url: str | None = Field(default=None, max_length=2048)
    region: str | None = Field(default=None, max_length=120)
    goals: list[ShortText] = Field(default_factory=list, max_length=10)
    budget: Money | None = None
    target_cpa: Money | None = None
    currency: Literal["RUB"] = "RUB"
    constraints: list[ShortText] = Field(default_factory=list, max_length=20)

    @field_validator("budget", "target_cpa", mode="before")
    @classmethod
    def decimal_text(cls, value):
        if value is not None and not isinstance(value, str):
            raise ValueError("money must be decimal text")
        return value

    @field_validator("site_url")
    @classmethod
    def public_url(cls, value):
        if not value:
            return None
        parsed = urlsplit(value)
        if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("website URL required")
        return value

    def payload(self):
        result = self.model_dump(mode="json")
        for key in ("budget", "target_cpa"):
            value = getattr(self, key)
            result[key] = f"{value:.2f}" if value is not None else None
        return result


def _live_personal(conn: Conn, user_id: int) -> tuple[int, int] | None:
    """Личный workspace, кроме удаляемого: иначе пользователь получал бы 410 навсегда и не мог начать заново.
    Статус виден только внутри workspace (RLS) — поэтому вход в каждого кандидата по очереди."""
    rows = conn.execute(
        """SELECT a.workspace_id, a.organization_id FROM user_workspaces(%s) a
                         JOIN organizations o ON o.id=a.organization_id
                         WHERE o.kind='business' AND a.role='owner' ORDER BY a.workspace_id""",
        (user_id,),
    ).fetchall()
    for ws, org in rows:
        set_local_workspace(conn, ws)
        if conn.execute("SELECT status FROM workspaces WHERE id=%s", (ws,)).fetchone()[0] != "deletion_pending":
            return ws, org
    return None


@router.post("/workspaces", status_code=201)
def personal_workspace(conn: Conn, actor: CurrentActor, body: WorkspaceCreate):
    conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (f"personal:{actor.user_id}",))
    row = _live_personal(conn, actor.user_id)
    if row:
        ws, org = row
    else:
        org = conn.execute("SELECT create_organization(%s,%s,'business')", (actor.user_id, body.name)).fetchone()[0]
        ws = conn.execute("SELECT create_workspace(%s,%s,%s)", (actor.user_id, org, body.name)).fetchone()[0]
    set_local_workspace(conn, ws)
    name, status = conn.execute("SELECT name,status FROM workspaces WHERE id=%s", (ws,)).fetchone()
    if status == "deletion_pending":
        raise ApiError(410, "workspace_deleted")
    return {"id": f"ws_{ws}", "name": name, "organization_id": f"org_{org}"}


@router.get("/workspaces/{workspace_id}/business-profile")
def profile(conn: Conn, ws: CurrentWorkspace):
    row = conn.execute("SELECT profile FROM business_profiles WHERE workspace_id=%s", (ws.id,)).fetchone()
    return BusinessProfile.model_validate(row[0] if row else {}).payload()


@router.put("/workspaces/{workspace_id}/business-profile")
def save_profile(conn: Conn, ws: CurrentWorkspace, body: BusinessProfile):
    require_manager(ws)
    payload = body.payload()
    conn.execute(
        """INSERT INTO business_profiles(workspace_id,profile) VALUES(%s,%s)
                  ON CONFLICT(workspace_id) DO UPDATE SET profile=excluded.profile,updated_at=now()""",
        (ws.id, Jsonb(payload)),
    )
    if "target_cpa" in body.model_fields_set:  # не прислан — настройку аудита не трогаем
        conn.execute(
            """INSERT INTO workspace_settings(workspace_id,target_cpa) VALUES(%s,%s)
                      ON CONFLICT(workspace_id) DO UPDATE SET target_cpa=excluded.target_cpa,updated_at=now()""",
            (ws.id, body.target_cpa),
        )
    return payload
