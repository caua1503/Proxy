from .logger import ProxyLogger

logger = ProxyLogger()


class ProxyFirewall:
    def __init__(
        self,
        allowlist: list[str] = [],
        blocklist: list[str] = [],
        no_auth_required: list[str] = [],
    ):
        """
        Proxy firewall

        args:
            allowlist (list[str]): list of allowed hosts
            blocklist (list[str]): list of blocked hosts
            no_auth_required (list[str]): list of hosts that do not require authentication
        """
        self.allowlist = set(allowlist)
        self.blocklist = set(blocklist)
        self.no_auth_required = set(no_auth_required)

        if not self.allowlist and not self.blocklist and not self.no_auth_required:
            raise ValueError(
                "At least one of allowlist, blocklist or no_auth_required is required, or disable the firewall"  # noqa: E501
            )

        for host in self.allowlist:
            if host in self.blocklist:
                raise ValueError(f"Host {host} is in both allowlist and blocklist")
        for host in self.blocklist:
            if host in self.allowlist or host in self.no_auth_required:
                raise ValueError(f"Host {host} is in both allowlist and blocklist")
        for host in self.no_auth_required:
            if host in self.blocklist:
                raise ValueError(f"Host {host} is in both allowlist and blocklist")

    def verify(self, host: str) -> bool:
        logger.debug(f"Verifying {host}")
        if self.is_blocked(host):
            return False

        if self.allowlist:
            return self.is_allowed(host)

        return True

    def is_allowed(self, host: str) -> bool:
        logger.debug(f"Checking if {host} is allowed")
        return host in self.allowlist

    def is_blocked(self, host: str) -> bool:
        logger.debug(f"Checking if {host} is blocked")
        return host in self.blocklist

    def is_no_auth_required(self, host: str) -> bool:
        logger.debug(f"Checking if {host} is no auth required")
        return host in self.no_auth_required
