class AppError(Exception):
    def __init__(self, status_code: int, title: str, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.title = title
        self.detail = detail
