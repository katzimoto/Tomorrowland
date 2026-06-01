"""Real LDAP client implementing LdapAuthenticator plus live group search (#582).

Uses ``ldap3`` for actual LDAP operations.  Safety rules:
* Search results are ephemeral — never persisted by this module.
* Admin query input is escaped before injection into LDAP filters.
* A strict timeout and result limit are enforced on every search.
* No service-account credentials or raw LDAP errors with secrets are returned.
"""

from __future__ import annotations

import contextlib
import logging
import re
from typing import Any

from ldap3 import ALL, SIMPLE, Connection, Server

from services.auth.ldap import LdapAuthenticator, LdapProfile
from shared.config import Settings

logger = logging.getLogger(__name__)

# Characters that must be escaped in LDAP filter values per RFC 4515.
_LDAP_FILTER_ESCAPE_RE = re.compile(r"([*()\\\x00])")
# Map of non-printable or dangerous characters to escape sequences.
_LDAP_FILTER_ESCAPE_MAP = {
    "\\": "\\5c",
    "*": "\\2a",
    "(": "\\28",
    ")": "\\29",
    "\x00": "\\00",
}

# Fields returned by search_groups.  Base set of safe display / identifier
# fields.  The configured external_id_attr and display_name_attr are added
# dynamically in search_groups().
_SGROUP_ATTRS_BASE = [
    "cn",
    "name",
    "displayName",
    "distinguishedName",
    "description",
    "mail",
    "objectGUID",
    "objectSid",
    "sAMAccountName",
]


def _escape_ldap_filter_value(value: str) -> str:
    """Escape a user-supplied value for safe injection into an LDAP filter."""
    return _LDAP_FILTER_ESCAPE_RE.sub(
        lambda m: _LDAP_FILTER_ESCAPE_MAP.get(m.group(1), m.group(1)),
        value,
    )


def _octet_string_to_hex(value: object) -> str | None:
    """Convert an LDAP byte-array attribute (e.g. objectGUID) to a hex string."""
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, (list, tuple)):
        # Some LDAP servers return lists of byte-strings.
        candidates = [v for v in value if isinstance(v, bytes)]
        if candidates:
            return candidates[0].hex()
    return str(value) if value else None


class LdapClient(LdapAuthenticator):
    """Real LDAP client that authenticates users and searches groups live.

    Constructed from a ``Settings`` instance.  Satisfies the
    ``LdapAuthenticator`` protocol so it can be injected into ``AuthService``.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    # -- LdapAuthenticator protocol ------------------------------------------------

    def authenticate(self, email: str, password: str) -> LdapProfile | None:
        """Bind as *email* with *password* and return a normalized profile.

        Returns ``None`` when credentials are invalid or the server is
        unreachable.
        """
        try:
            conn = self._bind(email, password)
        except Exception:
            logger.warning("LDAP authentication bind failed for %s", email, exc_info=True)
            return None

        if conn is None:
            return None

        try:
            display_name: str | None = None
            group_names: list[str] = []

            # Look up the user entry for display name and group memberships.
            user_dn = self._resolve_user_dn(conn, email)
            if user_dn is not None:
                display_name = self._read_display_name(conn, user_dn) or email
                group_names = self._read_user_group_dns(conn, user_dn)

            return LdapProfile(
                email=email,
                display_name=display_name,
                group_names=group_names,
            )
        except Exception:
            logger.warning("LDAP profile resolution failed for %s", email, exc_info=True)
            # Still return a profile with just the email so the user can log in
            # even if group resolution is broken.
            return LdapProfile(email=email)
        finally:
            with contextlib.suppress(Exception):
                conn.unbind()  # type: ignore[no-untyped-call]

    # -- Group search (#582) -------------------------------------------------------

    def search_groups(self, query: str) -> list[dict[str, Any]]:
        """Search LDAP for groups matching *query*.

        Parameters
        ----------
        query:
            Free-text query from the admin (e.g. part of a group name).

        Returns
        -------
        list[dict]
            Each dict contains only safe display/identifier fields:
            ``display_name``, ``distinguished_name``, ``external_id``,
            ``external_id_attr``, and optionally ``description`` and ``mail``.
        """
        if not query or not query.strip():
            return []

        escaped = _escape_ldap_filter_value(query.strip())
        filter_template = (
            self._settings.ldap_group_search_filter or "(&(objectClass=group)(cn=*{query}*))"
        )
        search_filter = filter_template.replace("{query}", escaped)

        try:
            conn = self._bind_service_account()
        except Exception:
            logger.warning("LDAP group search bind failed", exc_info=True)
            return []

        if conn is None:
            return []

        try:
            results: list[dict[str, Any]] = []
            external_id_attr = self._settings.ldap_group_external_id_attr or "objectGUID"
            display_name_attr = self._settings.ldap_group_display_name_attr or "cn"
            # Dynamically include configured attrs in the search.
            search_attrs = list(
                dict.fromkeys(_SGROUP_ATTRS_BASE + [external_id_attr, display_name_attr])
            )

            for base_dn in self._settings.ldap_group_search_base_dn_list:
                if len(results) >= self._settings.ldap_group_search_limit:
                    break

                remaining = self._settings.ldap_group_search_limit - len(results)
                try:
                    conn.search(
                        search_base=base_dn,
                        search_filter=search_filter,
                        search_scope="SUBTREE",
                        attributes=search_attrs,
                        size_limit=remaining,
                        time_limit=int(self._settings.ldap_group_search_timeout),
                    )
                except Exception:
                    logger.warning("LDAP group search failed base_dn=%s", base_dn, exc_info=True)
                    continue

                for entry in conn.entries:
                    entry_dict: dict[str, Any] = entry.entry_attributes_as_dict
                    external_id_raw = entry_dict.get(external_id_attr)
                    display_name_raw = entry_dict.get(display_name_attr) or entry_dict.get("cn")

                    results.append(
                        {
                            "display_name": _safe_str(display_name_raw),
                            "dn": _safe_str(entry_dict.get("distinguishedName")),
                            "external_id": _octet_string_to_hex(external_id_raw),
                            "external_id_attr": external_id_attr,
                            "description": _safe_str(entry_dict.get("description")),
                            "mail": _safe_str(entry_dict.get("mail")),
                        }
                    )

                    if len(results) >= self._settings.ldap_group_search_limit:
                        break

            return results
        except Exception:
            logger.warning("LDAP group search failed", exc_info=True)
            return []
        finally:
            with contextlib.suppress(Exception):
                conn.unbind()  # type: ignore[no-untyped-call]

    # -- Internal helpers ----------------------------------------------------------

    def _bind(self, user_dn: str, password: str) -> Connection | None:
        """Attempt a simple bind with *user_dn* and *password*."""
        server = Server(self._settings.ldap_url, get_info=ALL)
        conn = Connection(
            server,
            user=user_dn,
            password=password,
            authentication=SIMPLE,
            read_only=True,
        )
        if not conn.bind():
            logger.debug("LDAP bind failed for %s: %s", user_dn, conn.result)
            return None
        return conn

    def _bind_service_account(self) -> Connection | None:
        """Bind using the configured LDAP service account."""
        return self._bind(
            self._settings.ldap_bind_user,
            self._settings.ldap_bind_password,
        )

    def _resolve_user_dn(self, conn: Connection, email: str) -> str | None:
        """Search for a user's DN by email (or sAMAccountName).

        Returns ``None`` when the user cannot be found.
        """
        escaped = _escape_ldap_filter_value(email)
        search_filter = (
            f"(&(objectClass=user)"
            f"(|(mail={escaped})(userPrincipalName={escaped})(sAMAccountName={escaped})))"
        )
        try:
            conn.search(
                search_base=self._settings.ldap_base_dn,
                search_filter=search_filter,
                search_scope="SUBTREE",
                attributes=["distinguishedName"],
                size_limit=1,
                time_limit=5,
            )
        except Exception:
            logger.warning("LDAP user DN search failed", exc_info=True)
            return None

        if not conn.entries:
            # Try binding as the email directly (some servers use email-format DNs).
            return email

        entry_dict = conn.entries[0].entry_attributes_as_dict
        return _safe_str(entry_dict.get("distinguishedName"))

    def _read_display_name(self, conn: Connection, user_dn: str) -> str | None:
        """Read the display name for *user_dn*."""
        try:
            conn.search(
                search_base=user_dn,
                search_filter="(objectClass=*)",
                search_scope="BASE",
                attributes=["displayName", "cn"],
                size_limit=1,
                time_limit=3,
            )
        except Exception:
            logger.debug("LDAP display name read failed for %s", user_dn, exc_info=True)
            return None

        if not conn.entries:
            return None

        attrs = conn.entries[0].entry_attributes_as_dict
        return _safe_str(attrs.get("displayName") or attrs.get("cn"))

    def _read_user_group_dns(self, conn: Connection, user_dn: str) -> list[str]:
        """Read the group distinguished names for *user_dn*.

        Returns group DNs extracted from the user's ``memberOf`` attribute.
        """
        try:
            conn.search(
                search_base=user_dn,
                search_filter="(objectClass=*)",
                search_scope="BASE",
                attributes=["memberOf"],
                size_limit=1,
                time_limit=3,
            )
        except Exception:
            logger.debug("LDAP group DNs read failed for %s", user_dn, exc_info=True)
            return []

        if not conn.entries:
            return []

        member_of = conn.entries[0].entry_attributes_as_dict.get("memberOf")
        if member_of is None:
            return []
        if isinstance(member_of, str):
            return [member_of]
        if isinstance(member_of, (list, tuple)):
            return [str(dn) for dn in member_of]
        return []


def _safe_str(value: object) -> str | None:
    """Convert *value* to a string when possible, returning ``None`` otherwise."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value.hex()
    if isinstance(value, (list, tuple)):
        candidates = [v for v in value if isinstance(v, str)]
        return candidates[0] if candidates else None
    return str(value)
