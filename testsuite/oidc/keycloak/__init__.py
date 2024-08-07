"""Keycloak OIDCProvider"""

from functools import cached_property
from urllib.parse import urlparse

from keycloak import KeycloakOpenID, KeycloakAdmin, KeycloakPostError

from testsuite.oidc import OIDCProvider, Token
from testsuite.lifecycle import LifecycleObject
from .objects import Realm, Client, User


# pylint: disable=too-many-instance-attributes
class Keycloak(OIDCProvider, LifecycleObject):
    """
    OIDCProvider implementation using Keycloak. It creates Realm, Client and single User.
    """

    def __init__(
        self,
        server_url,
        username,
        password,
        realm_name,
        client_name,
        test_username="testUser",
        test_password="testPassword",
    ) -> None:
        self.test_username = test_username
        self.test_password = test_password
        self.username = username
        self.password = password
        self.realm_name = realm_name
        self.client_name = client_name
        self.realm = None
        self.user = None
        self.client = None

        try:
            self.master_realm = KeycloakAdmin(
                server_url=server_url,
                username=username,
                password=password,
                realm_name="master",
            )
            self.server_url = server_url
        except KeycloakPostError:
            # Older Keycloaks versions (and RHSSO) needs requires url to be pointed at auth/ endpoint
            # pylint: disable=protected-access
            self.server_url = urlparse(server_url)._replace(path="auth/").geturl()
            self.master_realm = KeycloakAdmin(
                server_url=self.server_url,
                username=username,
                password=password,
                realm_name="master",
            )

    def create_realm(self, name: str, **kwargs) -> Realm:
        """Creates new realm"""
        self.master_realm.create_realm(payload={"realm": name, "enabled": True, "sslRequired": "None", **kwargs})
        return Realm(self.master_realm, name)

    def commit(self):
        self.realm = self.create_realm(self.realm_name, accessTokenLifespan=24 * 60 * 60)

        self.client = self.realm.create_client(
            name=self.client_name,
            directAccessGrantsEnabled=True,
            publicClient=False,
            protocol="openid-connect",
            standardFlowEnabled=False,
            serviceAccountsEnabled=True,
            authorizationServicesEnabled=True,
        )
        self.user = self.realm.create_user(self.test_username, self.test_password)

    def delete(self):
        self.realm.delete()

    @property
    def oidc_client(self) -> KeycloakOpenID:
        """OIDCClient for the created client"""
        return self.client.oidc_client  # type: ignore

    @cached_property
    def well_known(self):
        return self.oidc_client.well_known()

    def refresh_token(self, refresh_token):
        """Refreshes token"""
        data = self.oidc_client.refresh_token(refresh_token)
        return Token(data["access_token"], self.refresh_token, data["refresh_token"])

    def get_token(self, username=None, password=None) -> Token:
        data = self.oidc_client.token(username or self.test_username, password or self.test_password)
        return Token(data["access_token"], self.refresh_token, data["refresh_token"])

    def get_public_key(self):
        """Return formatted public key"""
        return "-----BEGIN PUBLIC KEY-----\n" + self.oidc_client.public_key() + "\n-----END PUBLIC KEY-----"

    def token_params(self) -> str:
        """
        Returns token parameters that can be added to request url
        """
        return (
            f"grant_type=password&client_id={self.oidc_client.client_id}&"
            f"client_secret={self.oidc_client.client_secret_key}&username={self.test_username}&"
            f"password={self.test_password}"
        )

    def delete_signing_rs256_jwks_key(self):
        """Deletes signing RS256 key from JWKS"""

        jwks = self.realm.admin.get_keys()["keys"]
        assert jwks is not None

        provider_id = None
        for key in jwks:
            if key["use"] == "SIG" and key["algorithm"] == "RS256" and key["status"] == "ACTIVE":
                provider_id = key["providerId"]
                break
        assert provider_id is not None

        self.realm.admin.delete_component(provider_id)

    def create_signing_rs256_jwks_key(self):
        """Creates a new signing RS256 key in JWKS"""

        payload = {
            "name": "rsa-generated",
            "providerId": "rsa-generated",
            "providerType": "org.keycloak.keys.KeyProvider",
            "config": {
                "keySize": ["2048"],
                "active": ["true"],
                "priority": ["100"],
                "enabled": ["true"],
                "algorithm": ["RS256"],
            },
        }

        self.realm.admin.create_component(payload)
