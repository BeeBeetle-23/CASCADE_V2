class DomainError(Exception):
    def __init__(self, status: int, message: str, detail=None):
        self.status, self.message, self.detail = status, message, detail
        super().__init__(message)
