ISSUE_HINT = (
    "Run:\n\n    arcvault inspect --sanitize > arc-structure.json\n\n"
    "and attach the sanitized file to a GitHub issue."
)


class ArcVaultError(Exception):
    pass


class ArcNotFoundError(ArcVaultError):
    pass


class ArcSchemaError(ArcVaultError):
    def __init__(self, msg: str) -> None:
        super().__init__(f"{msg}\n\n{ISSUE_HINT}")


class ArcDataReadError(ArcVaultError):
    pass


class ExportError(ArcVaultError):
    pass


class ConfigurationError(ArcVaultError):
    pass
