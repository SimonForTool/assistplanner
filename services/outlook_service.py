"""Microsoft Graph API – správa událostí v Outlook kalendáři.

Používá client-credentials flow (App Registration + client secret) s aplikačním
oprávněním Calendars.ReadWrite. Bez vyplněných přihlašovacích údajů běží v mock
režimu: nic neodesílá a vrací fiktivní ID událostí, aby šlo aplikaci vyvíjet offline.
"""
import logging
import uuid
from datetime import datetime, timedelta

import requests

import config
from database.models import UserRole

log = logging.getLogger(__name__)

GRAPH_URL = "https://graph.microsoft.com/v1.0"
SCOPES = ["https://graph.microsoft.com/.default"]
MOCK_PREFIX = "mock-"


class OutlookError(RuntimeError):
    pass


class OutlookService:
    def __init__(self) -> None:
        self.mock = not config.graph_enabled()
        self._app = None
        if not self.mock:
            import msal
            self._app = msal.ConfidentialClientApplication(
                config.MS_CLIENT_ID,
                authority=f"https://login.microsoftonline.com/{config.MS_TENANT_ID}",
                client_credential=config.MS_CLIENT_SECRET,
            )

    # --- interní ---

    def _token(self) -> str:
        result = self._app.acquire_token_for_client(scopes=SCOPES)
        if "access_token" not in result:
            raise OutlookError(f"Nepodařilo se získat token: {result.get('error_description')}")
        return result["access_token"]

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        resp = requests.request(
            method,
            f"{GRAPH_URL}{path}",
            headers={"Authorization": f"Bearer {self._token()}",
                     "Content-Type": "application/json"},
            timeout=15,
            **kwargs,
        )
        if resp.status_code >= 400 and not (method == "DELETE" and resp.status_code == 404):
            raise OutlookError(f"Graph API {resp.status_code}: {resp.text[:300]}")
        return resp

    @staticmethod
    def mailbox_for(role: UserRole) -> str:
        mailbox = config.MS_DEPUTY_MAILBOX if role == UserRole.DEPUTY else config.MS_ASSISTANT_MAILBOX
        if not mailbox:
            raise OutlookError(f"Chybí adresa schránky pro roli {role.value}.")
        return mailbox

    @staticmethod
    def _event_body(title: str, start: datetime, description: str | None,
                    location: str | None) -> dict:
        end = start + timedelta(minutes=config.CALENDAR_EVENT_MINUTES)
        tz = str(config.TIMEZONE)
        body = {
            "subject": title,
            "start": {"dateTime": start.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": tz},
            "end": {"dateTime": end.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": tz},
            "body": {"contentType": "text", "content": description or ""},
        }
        if location:
            body["location"] = {"displayName": location}
        return body

    # --- veřejné API ---

    def create_event(self, role: UserRole, title: str, start: datetime,
                     description: str | None = None, location: str | None = None) -> str:
        if self.mock:
            event_id = f"{MOCK_PREFIX}{uuid.uuid4().hex[:12]}"
            log.info("[MOCK Outlook] Vytvořena událost %s v kalendáři %s", event_id, role.value)
            return event_id
        resp = self._request("POST", f"/users/{self.mailbox_for(role)}/events",
                             json=self._event_body(title, start, description, location))
        return resp.json()["id"]

    def update_event(self, role: UserRole, event_id: str, title: str, start: datetime,
                     description: str | None = None, location: str | None = None) -> None:
        if self.mock or event_id.startswith(MOCK_PREFIX):
            log.info("[MOCK Outlook] Aktualizována událost %s", event_id)
            return
        self._request("PATCH", f"/users/{self.mailbox_for(role)}/events/{event_id}",
                      json=self._event_body(title, start, description, location))

    def delete_event(self, role: UserRole, event_id: str) -> None:
        if self.mock or event_id.startswith(MOCK_PREFIX):
            log.info("[MOCK Outlook] Smazána událost %s", event_id)
            return
        self._request("DELETE", f"/users/{self.mailbox_for(role)}/events/{event_id}")

    def list_events_today(self, role: UserRole) -> list[dict]:
        """Dnešní události z kalendáře (pro ranní briefing). V mock režimu prázdný seznam."""
        if self.mock:
            return []
        now = datetime.now(config.TIMEZONE)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        resp = self._request(
            "GET",
            f"/users/{self.mailbox_for(role)}/calendarView",
            params={"startDateTime": start.isoformat(), "endDateTime": end.isoformat(),
                    "$select": "subject,start,end,location", "$orderby": "start/dateTime"},
        )
        return [
            {"subject": e.get("subject"),
             "start": e["start"]["dateTime"][:16].replace("T", " "),
             "location": (e.get("location") or {}).get("displayName")}
            for e in resp.json().get("value", [])
        ]


_service: OutlookService | None = None


def get_outlook() -> OutlookService:
    global _service
    if _service is None:
        _service = OutlookService()
    return _service
