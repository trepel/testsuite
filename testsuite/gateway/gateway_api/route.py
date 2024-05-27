"""Module containing all route classes"""

import typing

from httpx import Client

from testsuite.httpx import KuadrantClient
from testsuite.gateway import Gateway, GatewayRoute, PathMatch, MatchType, RouteMatch
from testsuite.openshift.client import OpenShiftClient
from testsuite.openshift import OpenShiftObject, modify
from testsuite.policy import Policy
from testsuite.utils import asdict, check_condition

if typing.TYPE_CHECKING:
    from testsuite.backend import Backend


class HTTPRoute(OpenShiftObject, GatewayRoute):
    """HTTPRoute object, serves as replacement for Routes and Ingresses"""

    def client(self, **kwargs) -> Client:
        """Returns HTTPX client"""
        return KuadrantClient(base_url=f"http://{self.hostnames[0]}", **kwargs)

    @classmethod
    def create_instance(
        cls,
        openshift: "OpenShiftClient",
        name,
        gateway: Gateway,
        labels: dict[str, str] = None,
    ):
        """Creates new instance of HTTPRoute"""
        model = {
            "apiVersion": "gateway.networking.k8s.io/v1beta1",
            "kind": "HTTPRoute",
            "metadata": {"name": name, "namespace": openshift.project, "labels": labels},
            "spec": {
                "parentRefs": [gateway.reference],
                "hostnames": [],
                "rules": [],
            },
        }

        return cls(model, context=openshift.context)

    def is_affected_by(self, policy: Policy):
        """Returns True, if affected by status is found within the object for the specific policy"""
        for condition_set in self.model.status.parents:
            if condition_set.controllerName == "kuadrant.io/policy-controller":
                for condition in condition_set.conditions:
                    if check_condition(
                        condition,
                        f"kuadrant.io/{policy.kind(lowercase=False)}Affected",
                        "True",
                        "Accepted",
                        f"Object affected by {policy.kind(lowercase=False)} {policy.namespace()}/{policy.name()}",
                    ):
                        return True
        return False

    @property
    def reference(self):
        return {
            "group": "gateway.networking.k8s.io",
            "kind": "HTTPRoute",
            "name": self.name(),
            "namespace": self.namespace(),
        }

    @property
    def hostnames(self):
        """Return all hostnames for this HTTPRoute"""
        return self.model.spec.hostnames

    @modify
    def add_hostname(self, hostname: str):
        """Adds hostname to the Route"""
        if hostname not in self.model.spec.hostnames:
            self.model.spec.hostnames.append(hostname)

    @modify
    def remove_hostname(self, hostname: str):
        """Adds hostname to the Route"""
        self.model.spec.hostnames.remove(hostname)

    @modify
    def remove_all_hostnames(self):
        """Adds hostname to the Route"""
        self.model.spec.hostnames = []

    @modify
    def add_rule(self, backend: "Backend", *route_matches: RouteMatch):
        """Adds rule to the Route"""
        rules: dict[str, typing.Any] = {"backendRefs": [backend.reference]}
        matches = list(route_matches)
        if len(matches) == 0:
            matches.append(RouteMatch(path=PathMatch(type=MatchType.PATH_PREFIX, value="/")))

        rules["matches"] = [asdict(match) for match in matches]
        self.model.spec.rules.append(rules)

    @modify
    def remove_all_rules(self):
        """Remove all rules from the Route"""
        self.model.spec.rules = []

    @modify
    def add_backend(self, backend: "Backend", prefix="/"):
        self.model.spec.rules.append(
            {"backendRefs": [backend.reference], "matches": [{"path": {"value": prefix, "type": "PathPrefix"}}]}
        )

    @modify
    def remove_all_backend(self):
        self.model.spec.rules.clear()
