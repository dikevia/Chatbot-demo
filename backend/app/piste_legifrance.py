"""Minimal, defensive client for the stable Légifrance API exposed through PISTE.

Credentials are read only from the process environment. This module never logs
credentials, OAuth tokens, response bodies, or personal data.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date
from typing import Any


class LegifranceError(RuntimeError):
    """Sanitized API/authentication error safe to display in application logs."""


@dataclass(frozen=True)
class _Token:
    value: str
    expires_at: float


class LegifranceClient:
    def __init__(self, *, opener=None, clock=time.monotonic) -> None:
        self.environment = os.getenv("LEGIFRANCE_ENVIRONMENT", "sandbox").strip().lower()
        if self.environment not in {"sandbox", "production"}:
            raise LegifranceError("LEGIFRANCE_ENVIRONMENT doit être sandbox ou production.")
        prefix = "sandbox-" if self.environment == "sandbox" else ""
        self.oauth_url = f"https://{prefix}oauth.piste.gouv.fr/api/oauth/token"
        self.api_base = f"https://{prefix}api.piste.gouv.fr/dila/legifrance/lf-engine-app"
        self.client_id = os.getenv("LEGIFRANCE_CLIENT_ID", "").strip()
        self.client_secret = os.getenv("LEGIFRANCE_CLIENT_SECRET", "")
        if not self.client_id or not self.client_secret:
            raise LegifranceError("Identifiants PISTE Légifrance non configurés.")
        self._opener = opener or urllib.request.urlopen
        self._clock = clock
        self._token: _Token | None = None
        self._lock = threading.Lock()

    def _request(self, url: str, *, data: bytes | None = None,
                 headers: dict[str, str] | None = None) -> Any:
        request = urllib.request.Request(url, data=data, headers=headers or {},
                                         method="POST" if data is not None else "GET")
        try:
            response = self._opener(request, timeout=15)
            with response:
                raw = response.read()
                status = getattr(response, "status", 200)
        except urllib.error.HTTPError as exc:
            status = exc.code
            # Never include provider response bodies: they can echo sensitive data.
            if status == 401:
                raise LegifranceError("Authentification PISTE refusée (401). Vérifier les identifiants et l'environnement.") from None
            if status == 403:
                raise LegifranceError("Accès Légifrance refusé (403). Vérifier les CGU et l'abonnement de l'application PISTE.") from None
            if status == 429:
                raise LegifranceError("Quota PISTE atteint (429). Réessayer ultérieurement.") from None
            if status >= 500:
                raise LegifranceError(f"Service Légifrance temporairement indisponible ({status}).") from None
            raise LegifranceError(f"Requête Légifrance refusée ({status}).") from None
        except (TimeoutError, urllib.error.URLError, OSError):
            raise LegifranceError("Connexion au service Légifrance impossible ou expirée.") from None
        if status >= 400:
            raise LegifranceError(f"Service Légifrance en erreur ({status}).")
        try:
            return json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise LegifranceError("Réponse Légifrance illisible.") from None

    def _access_token(self, *, force: bool = False) -> str:
        with self._lock:
            if not force and self._token and self._token.expires_at > self._clock() + 60:
                return self._token.value
            form = urllib.parse.urlencode({
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "openid",
            }).encode("ascii")
            payload = self._request(
                self.oauth_url, data=form,
                headers={"Accept": "application/json",
                         "Content-Type": "application/x-www-form-urlencoded"},
            )
            token = payload.get("access_token") if isinstance(payload, dict) else None
            expires = payload.get("expires_in", 3600) if isinstance(payload, dict) else 0
            if not isinstance(token, str) or not token or not isinstance(expires, (int, float)):
                raise LegifranceError("PISTE n'a pas fourni de jeton OAuth valide.")
            self._token = _Token(token, self._clock() + max(60, int(expires)))
            return token

    def _api(self, path: str, payload: dict[str, Any] | None = None) -> Any:
        token = self._access_token()
        url = self.api_base + "/" + path.lstrip("/")
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        try:
            return self._request(url, data=body, headers=headers)
        except LegifranceError as exc:
            if "Authentification PISTE refusée (401)" not in str(exc):
                raise
            token = self._access_token(force=True)
            headers["Authorization"] = f"Bearer {token}"
            return self._request(url, data=body, headers=headers)

    def ping(self) -> bool:
        result = self._api("list/ping")
        return bool(result is not None)

    @staticmethod
    def _search_payload(term: str, fond: str, *, start: str | None = None,
                        end: str | None = None, page_size: int = 10) -> dict[str, Any]:
        term = " ".join(term.split())[:180]
        if not term:
            raise LegifranceError("Le terme de recherche est vide.")
        if start and end:
            try:
                if date.fromisoformat(start) > date.fromisoformat(end):
                    raise ValueError
            except ValueError:
                raise LegifranceError("Période de recherche invalide.") from None
        filtres = []
        if start and end:
            filtres.append({"facette": "DATE_DECISION" if fond == "CETAT" else "DATE_VERSION",
                            "dates": {"start": start, "end": end}})
        return {
            "fond": fond,
            "recherche": {
                "champs": [{
                    "typeChamp": "ALL",
                    "criteres": [{"typeRecherche": "UN_DES_MOTS", "valeur": term,
                                  "proximite": 2, "operateur": "ET"}],
                    "operateur": "ET",
                }],
                "filtres": filtres,
                "fromAdvancedRecherche": False,
                "pageNumber": 1,
                "pageSize": max(1, min(int(page_size), 25)),
                "operateur": "ET",
                "sort": "PERTINENCE",
                "secondSort": "DATE_DESC",
                "typePagination": "DEFAUT",
            },
        }

    def search_texts(self, term: str, *, start: str | None = None,
                     end: str | None = None, page_size: int = 10) -> Any:
        """Search current consolidated legislation and regulations (LODA_DATE)."""
        return self._api("search", self._search_payload(
            term, "LODA_DATE", start=start, end=end, page_size=page_size))

    def search_codes(self, term: str, *, page_size: int = 10) -> Any:
        """Search code content; caller must constrain results to relevant codes."""
        return self._api("search", self._search_payload(term, "CODE_ETAT", page_size=page_size))

    def search_administrative_case_law(self, term: str, *, start: str | None = None,
                                       end: str | None = None, page_size: int = 10) -> Any:
        """Search administrative case law (CETAT), not judicial case law (JURI)."""
        return self._api("search", self._search_payload(
            term, "CETAT", start=start, end=end, page_size=page_size))

    def get_article(self, article_id: str) -> Any:
        if not article_id.startswith("LEGIARTI"):
            raise LegifranceError("Identifiant d'article Légifrance invalide.")
        return self._api("consult/getArticle", {"id": article_id})

    def get_legi_part(self, text_id: str, at: date | None = None) -> Any:
        if not text_id.startswith("LEGITEXT"):
            raise LegifranceError("Identifiant de texte Légifrance invalide.")
        at = at or date.today()
        timestamp_ms = int(time.mktime(at.timetuple()) * 1000)
        return self._api("consult/legiPart", {"date": timestamp_ms, "textId": text_id})
