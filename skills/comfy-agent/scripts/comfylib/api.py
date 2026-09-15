class ApiError(Exception):
    def __init__(self, message, status=None, body=None, url=None):
        super().__init__(message)
        self.status, self.body, self.url = status, body, url


class ConnectError(ApiError):
    pass


class Client:
    def __init__(self, base_url, auth=None, timeout=30.0, retries=3):
        self.base_url = base_url
