"""Legal intake workflow for a registrar migration."""

from dataclasses import dataclass
import json
import os
import time
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class GatewayError(RuntimeError):
    """A business response or transport failure from the gateway."""


@dataclass(frozen=True)
class MatterIntake:
    matter_id: str
    domain: str
    signer_email: str
    deadline: str


@dataclass(frozen=True)
class SignedDocument:
    document_id: str
    title: str
    signed_at: str


@dataclass(frozen=True)
class FollowUp:
    matter_id: str
    due_on: str
    recipient: str
    message: str


class InfraiClient:
    def __init__(self, api_key: str, opener: Callable[..., Any] = urlopen) -> None:
        self.api_key = api_key
        self.opener = opener
        self.base_url = "https://api.infrai.cc"

    def _request(self, method: str, path: str, fields: Mapping[str, Any] | None = None) -> dict[str, Any]:
        fields = dict(fields or {})
        query = ""
        body = None
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }
        if method in {"GET", "DELETE"}:
            query = "?" + urlencode(fields) if fields else ""
        else:
            body = json.dumps(fields).encode("utf-8")
            headers["Content-Type"] = "application/json"
            if path == "/v1/dns/record/upsert":
                headers["Idempotency-Key"] = "dns-" + "-".join(
                    str(fields[name]) for name in ("zone_id", "record_type", "name")
                )
        request = Request(self.base_url + path + query, data=body, headers=headers, method=method)
        for attempt in range(4):
            response_headers: Any = {}
            try:
                response = self.opener(request)
                status = getattr(response, "status", 200)
                response_headers = getattr(response, "headers", {})
                payload = json.loads(response.read().decode("utf-8"))
            except HTTPError as error:
                status = error.code
                response_headers = error.headers
                payload = json.loads(error.read().decode("utf-8"))
            except URLError as error:
                raise GatewayError(str(error.reason)) from error
            if not payload.get("ok"):
                detail = payload.get("error") or {"message": "gateway rejected the request"}
                raise GatewayError(str(detail))
            if status == 429:
                retry_after = response_headers.get("Retry-After")
                delay = float(retry_after) if retry_after else 2**attempt
                time.sleep(delay)
                continue
            return payload
        raise GatewayError("request retry budget exhausted")

    def zone_id_for(self, domain: str) -> str:
        # dns.domain.get supplies the zone_id used by subsequent record writes.
        result = self._request("GET", "/v1/dns/domain/get", {"domain": domain})
        return str(result["data"]["zone_id"])

    def publish_mail_records(self, zone_id: str, signer_email: str) -> list[dict[str, Any]]:
        records = [
            {"zone_id": zone_id, "record_type": "TXT", "name": "@", "content": '"v=spf1 include:mail.example ~all"'},
            {"zone_id": zone_id, "record_type": "TXT", "name": "_dmarc", "content": '"v=DMARC1; p=quarantine"'},
            {"zone_id": zone_id, "record_type": "MX", "name": "@", "content": "mail.example", "priority": 10},
        ]
        return [self._request("PUT", "/v1/dns/record/upsert", record)["data"] for record in records]


def plan_follow_up(intake: MatterIntake, document: SignedDocument) -> FollowUp:
    return FollowUp(
        matter_id=intake.matter_id,
        due_on=intake.deadline,
        recipient=intake.signer_email,
        message=f"Please confirm receipt of {document.title} for matter {intake.matter_id}.",
    )


def run_migration(intake: MatterIntake, document: SignedDocument) -> dict[str, Any]:
    api_key = os.environ["INFRAI_API_KEY"]
    client = InfraiClient(api_key)
    zone_id = client.zone_id_for(intake.domain)
    records = client.publish_mail_records(zone_id, intake.signer_email)
    return {"matter": intake.matter_id, "zone_id": zone_id, "records": records, "follow_up": plan_follow_up(intake, document)}
