"""Read-only provider discovery after OAuth, bounded to 20 Metrika counters."""

from dataclasses import asdict, dataclass, replace
import os
import re
from urllib.parse import urlsplit

from app.auth.tokens import EnvKeys
from app.auth.yandex_oauth import OAuthApp, OAuthError
from app.sources.direct import json_body
from app.sources.http import api_client
from app.sources.metrika import MetrikaApi
from app.sources.metrika_discovery import parse_counters, parse_goal_list, score_goal

SCOPES = ("direct:api", "metrika:read")


@dataclass
class IntegrationServices:
    app: OAuthApp
    keys: object
    http: object
    redirect_uris: dict | None = None

    @classmethod
    def from_env(cls):
        app = OAuthApp.from_env("YANDEX_API", SCOPES)
        uris = {
            "yandex_direct": os.environ.get("YANDEX_API_DIRECT_REDIRECT_URI", app.redirect_uri),
            "yandex_metrika": os.environ.get("YANDEX_API_METRIKA_REDIRECT_URI", ""),
        }
        return cls(app, EnvKeys(), api_client("yandex_oauth"), uris)

    def app_for(self, provider: str):
        uri = (self.redirect_uris or {}).get(provider, "")
        parsed = urlsplit(uri)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise RuntimeError("provider callback URI not configured")
        if not parsed.path.endswith(f"/integrations/{provider}/callback") or parsed.query or parsed.fragment:
            raise RuntimeError("callback URI does not match provider")
        scopes = ("direct:api",) if provider == "yandex_direct" else ("metrika:read",)
        return replace(self.app, redirect_uri=uri, scopes=scopes)

    def discover(self, provider: str, token: str) -> dict:
        if provider == "yandex_metrika":
            return self.metrika_catalog(token)
        response = self.http.post(
            "https://api.direct.yandex.com/json/v5/clients",
            timeout=10,
            headers={"Authorization": f"Bearer {token}"},
            json={"method": "get", "params": {"FieldNames": ["Login"]}},
        )
        result = json_body(response).get("result")
        clients = result.get("Clients") if isinstance(result, dict) else None
        if response.status_code != 200 or not isinstance(clients, list) or len(clients) != 1:
            raise OAuthError("provider_discovery_failed")
        login = clients[0].get("Login") if isinstance(clients[0], dict) else None
        if not isinstance(login, str) or not re.fullmatch(r"[A-Za-z0-9_.@-]{1,128}", login):
            raise OAuthError("provider_discovery_failed")
        return {"login": login, "accounts": [{"client_login": None, "login": login}]}

    def metrika_catalog(self, token: str) -> dict:
        source = MetrikaApi(self.http, token)
        counters = parse_counters(source.fetch_counters())
        result = []
        for counter in counters[:20]:
            goals = parse_goal_list(source.fetch_goals(counter.id))
            result.append(
                {
                    **asdict(counter),
                    "goals": [
                        {**asdict(g), "level": score_goal(g).level, "reason": score_goal(g).reason} for g in goals
                    ],
                }
            )
        return {"login": None, "counters": result, "catalog_truncated": len(counters) > 20}
