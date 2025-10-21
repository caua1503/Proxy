import base64


class ProxyAuth:
    """
    Proxy authentication

    args:
        username (str),
        password (str)
    """

    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password

        if not username or not password:
            raise ValueError("Username and password are required")

    def authenticate(self, username: str, password: str) -> bool:
        """
        Authenticate the user and password

        returns:
            bool: True if authenticated, False otherwise
        """
        if not username or not password:
            return False

        if self.username == username and self.password == password:
            return True
        else:
            return False

    def is_authorized(self, headers: dict[str, str]) -> bool:
        auth_header = headers.get("Proxy-Authorization")
        if not auth_header:
            return False

        scheme, _, param = auth_header.partition(" ")
        if scheme.lower() != "basic" or not param:
            return False

        try:
            decoded = base64.b64decode(param).decode("utf-8")
            username, _, password = decoded.partition(":")
        except Exception:
            return False

        return self.authenticate(username, password)
