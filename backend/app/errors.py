class AppError(Exception):
    """An error that becomes the contract error shape: { error: { code, message } }."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message