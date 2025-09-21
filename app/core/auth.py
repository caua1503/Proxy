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
