"""Fiken API v2-klient for BilagBot."""

import logging
import time
import uuid
from pathlib import Path

import httpx

from bilagbot.config import FIKEN_API_TOKEN, FIKEN_BASE_URL, FIKEN_COMPANY_SLUG
from bilagbot.exceptions import (
    FikenAuthError,
    FikenError,
    FikenNotFoundError,
    FikenRateLimitError,
    FikenValidationError,
)

logger = logging.getLogger(__name__)

# Fiken MVA-koder til vatType-mapping
VAT_CODE_TO_TYPE: dict[str, str] = {
    "0": "NONE",
    "1": "HIGH",
    "3": "HIGH",
    "6": "OUTSIDE",
    "7": "NONE",
    "11": "MEDIUM",
    "12": "RAW_FISH",
    "13": "LOW",
    "14": "HIGH_DIRECT",
    "31": "MEDIUM",
    "33": "LOW",
}


def vat_code_to_type(code: str | None) -> str:
    """Konverter BilagBot MVA-kode til Fiken vatType."""
    if not code:
        return "HIGH"
    return VAT_CODE_TO_TYPE.get(code, "HIGH")


def amount_to_cents(amount: float | None) -> int:
    """Konverter beløp (float) til øre (int) for Fiken."""
    if amount is None:
        return 0
    return round(amount * 100)


class FikenClient:
    """Klient for Fiken API v2."""

    MAX_RETRIES = 3
    RETRY_BACKOFF = 2  # sekunder, dobles per forsøk

    def __init__(
        self,
        api_token: str | None = None,
        company_slug: str | None = None,
        base_url: str | None = None,
        http_client: httpx.Client | None = None,
    ):
        self.api_token = api_token or FIKEN_API_TOKEN
        self.company_slug = company_slug or FIKEN_COMPANY_SLUG
        self.base_url = base_url or FIKEN_BASE_URL

        if not self.api_token:
            raise FikenAuthError("FIKEN_API_TOKEN er ikke satt")
        if not self.company_slug:
            raise FikenError("FIKEN_COMPANY_SLUG er ikke satt")

        self._http = http_client or httpx.Client(
            headers={
                "Authorization": f"Bearer {self.api_token}",
                "Accept": "application/json",
            },
            timeout=30.0,
        )

    def close(self) -> None:
        """Lukk HTTP-klienten."""
        self._http.close()

    def _url(self, path: str) -> str:
        """Bygg full URL for et API-endepunkt."""
        return f"{self.base_url}/companies/{self.company_slug}{path}"

    def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        """Utfør HTTP-request med retry og feilhåndtering."""
        kwargs.setdefault("headers", {})
        kwargs["headers"]["X-Request-ID"] = str(uuid.uuid4())

        last_error = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                response = self._http.request(method, url, **kwargs)
            except httpx.HTTPError as e:
                last_error = FikenError(f"Nettverksfeil: {e}")
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_BACKOFF ** attempt)
                continue

            if response.status_code == 429:
                last_error = FikenRateLimitError("For mange forespørsler")
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_BACKOFF ** attempt)
                continue

            if response.status_code in (500, 502, 503, 504):
                last_error = FikenError(f"Serverfeil: {response.status_code}")
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_BACKOFF ** attempt)
                continue

            # Ikke-retrybare feil
            if response.status_code in (401, 403):
                raise FikenAuthError(f"Autentiseringsfeil: {response.status_code} — sjekk FIKEN_API_TOKEN")
            if response.status_code == 404:
                raise FikenNotFoundError(f"Ikke funnet: {url}")
            if response.status_code == 400:
                detail = response.text[:500]
                raise FikenValidationError(f"Valideringsfeil: {detail}")
            if response.status_code == 415:
                raise FikenValidationError("Feil mediatype — Fiken krever application/json")

            return response

        raise last_error or FikenError("Ukjent feil etter retry")

    # --- Validering ---

    def validate(self) -> dict:
        """Valider API-tilkobling. Returnerer firmadata."""
        url = f"{self.base_url}/companies/{self.company_slug}"
        response = self._request("GET", url)
        response.raise_for_status()
        return response.json()

    # --- Kontoplan ---

    def get_accounts(self) -> list[dict]:
        """Hent kontoplan fra Fiken."""
        response = self._request("GET", self._url("/accounts"))
        response.raise_for_status()
        return response.json()

    # --- Kontakter (leverandører) ---

    def find_contact_by_org_number(self, org_number: str) -> dict | None:
        """Søk etter kontakt basert på organisasjonsnummer."""
        response = self._request(
            "GET",
            self._url("/contacts"),
            params={"organizationNumber": org_number, "pageSize": 1},
        )
        response.raise_for_status()
        results = response.json()
        return results[0] if results else None

    def create_contact(self, name: str, org_number: str | None = None) -> int:
        """Opprett ny kontakt i Fiken. Returnerer contact ID."""
        payload: dict = {
            "name": name,
            "customer": False,
            "supplier": True,
        }
        if org_number:
            payload["organizationNumber"] = org_number

        response = self._request("POST", self._url("/contacts"), json=payload)

        # Fiken returnerer 201 med Location-header
        if response.status_code == 201:
            location = response.headers.get("Location", "")
            # Location: https://api.fiken.no/api/v2/companies/{slug}/contacts/{id}
            contact_id = int(location.rstrip("/").split("/")[-1])
            logger.info("Opprettet kontakt %s (ID: %d)", name, contact_id)
            return contact_id

        response.raise_for_status()
        raise FikenError(f"Uventet respons ved kontaktopprettelse: {response.status_code}")

    def get_or_create_contact(self, name: str, org_number: str | None = None) -> int:
        """Finn eksisterende kontakt eller opprett ny. Returnerer contact ID."""
        if org_number:
            existing = self.find_contact_by_org_number(org_number)
            if existing:
                contact_id = existing["contactId"]
                logger.info("Fant eksisterende kontakt %s (ID: %d)", name, contact_id)
                return contact_id

        return self.create_contact(name, org_number)

    # --- Kjøp ---

    def create_purchase(
        self,
        *,
        date: str,
        due_date: str | None = None,
        identifier: str | None = None,
        kid: str | None = None,
        contact_id: int | None = None,
        account_code: str,
        vat_code: str | None = None,
        gross_amount: int,
        description: str | None = None,
    ) -> int:
        """Opprett et kjøp i Fiken.

        Args:
            date: Fakturadato (yyyy-MM-dd)
            due_date: Forfallsdato (yyyy-MM-dd)
            identifier: Fakturanummer
            kid: KID/betalingsreferanse
            contact_id: Fiken kontakt-ID for leverandøren
            account_code: Kontokode (f.eks. "6900")
            vat_code: BilagBot MVA-kode ("1", "11", "6" osv.)
            gross_amount: Bruttobeløp i øre (inkl. MVA)
            description: Beskrivelse

        Returns:
            Purchase ID fra Fiken
        """
        line = {
            "description": description or "Kjøp",
            "account": account_code,
            "vatType": vat_code_to_type(vat_code),
            "grossAmount": gross_amount,
        }

        payload: dict = {
            "date": date,
            "kind": "cash_purchase",
            "lines": [line],
        }

        if due_date:
            payload["dueDate"] = due_date
        if identifier:
            payload["identifier"] = identifier
        if kid:
            payload["kid"] = kid
        if contact_id:
            payload["supplier"] = {"contactId": contact_id}

        response = self._request("POST", self._url("/purchases"), json=payload)

        if response.status_code == 201:
            location = response.headers.get("Location", "")
            purchase_id = int(location.rstrip("/").split("/")[-1])
            logger.info("Opprettet kjøp #%d (beløp: %d øre)", purchase_id, gross_amount)
            return purchase_id

        response.raise_for_status()
        raise FikenError(f"Uventet respons ved kjøpsopprettelse: {response.status_code}")

    # --- Vedlegg ---

    def upload_attachment(self, purchase_id: int, file_path: Path) -> None:
        """Last opp vedlegg til et kjøp."""
        if not file_path.exists():
            raise FikenError(f"Fil ikke funnet: {file_path}")

        mime_types = {
            ".pdf": "application/pdf",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
        }
        content_type = mime_types.get(file_path.suffix.lower(), "application/octet-stream")

        with open(file_path, "rb") as f:
            response = self._request(
                "POST",
                self._url(f"/purchases/{purchase_id}/attachments"),
                files={"file": (file_path.name, f, content_type)},
            )

        if response.status_code in (200, 201):
            logger.info("Lastet opp vedlegg %s til kjøp #%d", file_path.name, purchase_id)
            return

        response.raise_for_status()

    # --- Komplett bokføringsflyt ---

    def post_invoice(
        self,
        *,
        vendor_name: str,
        vendor_org_number: str | None,
        invoice_date: str,
        due_date: str | None,
        invoice_number: str | None,
        payment_reference: str | None,
        total_amount: float,
        account_code: str,
        vat_code: str | None,
        description: str | None,
        file_path: Path | None = None,
    ) -> int:
        """Komplett bokføringsflyt: kontakt → kjøp → vedlegg.

        Returns:
            Purchase ID fra Fiken
        """
        # 1. Finn eller opprett kontakt
        contact_id = None
        if vendor_name:
            contact_id = self.get_or_create_contact(vendor_name, vendor_org_number)

        # 2. Opprett kjøp
        purchase_id = self.create_purchase(
            date=invoice_date or "1970-01-01",
            due_date=due_date,
            identifier=invoice_number,
            kid=payment_reference,
            contact_id=contact_id,
            account_code=account_code,
            vat_code=vat_code,
            gross_amount=amount_to_cents(total_amount),
            description=description,
        )

        # 3. Last opp vedlegg (feil her blokkerer ikke bokføringen)
        if file_path and file_path.exists():
            try:
                self.upload_attachment(purchase_id, file_path)
            except FikenError as e:
                logger.warning("Vedlegg feilet for kjøp #%d: %s", purchase_id, e)

        return purchase_id
