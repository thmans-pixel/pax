"""Mini client pour tester l'application ASGI sans TestClient (httpx absent)."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from urllib.parse import urlencode, urlsplit


@dataclass
class Reponse:
    status: int
    headers: dict
    corps: bytes

    @property
    def texte(self) -> str:
        return self.corps.decode("utf-8", errors="replace")

    def json(self):
        import json
        return json.loads(self.corps)


class Client:
    def __init__(self, app, entetes: dict | None = None):
        self.app = app
        self.entetes = {k.lower(): v for k, v in (entetes or {}).items()}

    def requete(self, methode: str, url: str, donnees: dict | None = None, json_: object = None,
                entetes: dict | None = None) -> Reponse:
        return asyncio.run(self._requete(methode, url, donnees, json_, entetes))

    def get(self, url, **kw):
        return self.requete("GET", url, **kw)

    def post(self, url, **kw):
        return self.requete("POST", url, **kw)

    async def _requete(self, methode, url, donnees, json_, entetes):
        import json
        p = urlsplit(url)
        h = {"host": "testserver", **self.entetes, **{k.lower(): v for k, v in (entetes or {}).items()}}
        corps = b""
        if donnees is not None:
            corps = urlencode(donnees).encode()
            h.setdefault("content-type", "application/x-www-form-urlencoded")
        elif json_ is not None:
            corps = json.dumps(json_).encode()
            h.setdefault("content-type", "application/json")
        h["content-length"] = str(len(corps))
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": methode,
                 "scheme": "http", "path": p.path, "raw_path": p.path.encode(),
                 "query_string": p.query.encode(), "root_path": "", "server": ("testserver", 80),
                 "client": ("127.0.0.1", 1234), "headers": [(k.encode(), v.encode()) for k, v in h.items()]}
        envoye = False

        async def receive():
            nonlocal envoye
            if not envoye:
                envoye = True
                return {"type": "http.request", "body": corps, "more_body": False}
            return {"type": "http.disconnect"}

        statut, en, morceaux = 500, {}, []

        async def send(m):
            nonlocal statut, en
            if m["type"] == "http.response.start":
                statut = m["status"]
                en = {k.decode().lower(): v.decode() for k, v in m["headers"]}
            elif m["type"] == "http.response.body":
                morceaux.append(m.get("body", b""))

        await self.app(scope, receive, send)
        return Reponse(statut, en, b"".join(morceaux))
