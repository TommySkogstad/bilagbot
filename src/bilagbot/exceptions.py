"""Exception-hierarki for BilagBot."""


class BilagBotError(Exception):
    """Base exception for alle BilagBot-feil."""


class ScannerError(BilagBotError):
    """Feil ved scanning/parsing av dokument."""


class ClassifierError(BilagBotError):
    """Feil ved klassifisering av leverandør."""


class DatabaseError(BilagBotError):
    """Feil ved databaseoperasjoner."""
