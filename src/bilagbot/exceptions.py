"""Exception-hierarki for BilagBot."""


class BilagBotError(Exception):
    """Base exception for alle BilagBot-feil."""


class ScannerError(BilagBotError):
    """Feil ved scanning/parsing av dokument."""


class ClassifierError(BilagBotError):
    """Feil ved klassifisering av leverandør."""


class DatabaseError(BilagBotError):
    """Feil ved databaseoperasjoner."""


class FikenError(BilagBotError):
    """Base exception for Fiken API-feil."""


class FikenAuthError(FikenError):
    """401/403 — ugyldig token eller manglende tilgang."""


class FikenValidationError(FikenError):
    """400 — valideringsfeil fra Fiken (manglende felt, ugyldig konto)."""


class FikenRateLimitError(FikenError):
    """429 — for mange forespørsler."""


class FikenNotFoundError(FikenError):
    """404 — ressurs ikke funnet."""
