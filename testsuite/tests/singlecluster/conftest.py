"""Configure all the components through Kuadrant,
 all methods are placeholders for now since we do not work with Kuadrant"""

import pytest
from openshift_client import selector

from testsuite.backend.httpbin import Httpbin
from testsuite.gateway import GatewayRoute, Gateway, Hostname
from testsuite.gateway.envoy import Envoy
from testsuite.gateway.envoy.route import EnvoyVirtualRoute
from testsuite.gateway.gateway_api.gateway import KuadrantGateway
from testsuite.gateway.gateway_api.route import HTTPRoute
from testsuite.kuadrant import KuadrantCR
from testsuite.kuadrant.policy.authorization.auth_policy import AuthPolicy
from testsuite.kuadrant.policy.rate_limit import RateLimitPolicy


@pytest.fixture(scope="session")
def cluster2(testconfig, skip_or_fail):
    """Kubernetes client for the secondary namespace located on the same cluster as primary cluster"""
    project = testconfig["service_protection"]["project2"]
    client = testconfig["cluster"].change_project(testconfig["service_protection"]["project2"])
    if client is None:
        skip_or_fail("Tests requires second_project but service_protection.project2 is not set")
    if not client.connected:
        pytest.fail(f"You are not logged into Kubernetes or the namespace for {project} doesn't exist")
    return client


@pytest.fixture(scope="module")
def authorization_name(blame):
    """Name of the Authorization resource, can be overriden to include more dependencies"""
    return blame("authz")


@pytest.fixture(scope="module")
def authorization(request, kuadrant, route, gateway, blame, cluster, label):  # pylint: disable=unused-argument
    """Authorization object (In case of Kuadrant AuthPolicy)"""
    target_ref = request.getfixturevalue(getattr(request, "param", "route"))

    if kuadrant:
        return AuthPolicy.create_instance(cluster, blame("authz"), target_ref, labels={"testRun": label})
    return None


@pytest.fixture(scope="module")
def rate_limit(kuadrant, cluster, blame, request, module_label, route, gateway):  # pylint: disable=unused-argument
    """
    Rate limit object.
    Request is used for indirect parametrization, with two possible parameters:
        1. `route` (default)
        2. `gateway`
    """
    target_ref = request.getfixturevalue(getattr(request, "param", "route"))

    if kuadrant:
        return RateLimitPolicy.create_instance(cluster, blame("limit"), target_ref, labels={"testRun": module_label})
    return None


@pytest.fixture(scope="module", autouse=True)
def commit(request, authorization, rate_limit):
    """Commits all important stuff before tests"""
    for component in [authorization, rate_limit]:
        if component is not None:
            request.addfinalizer(component.delete)
            component.commit()
            component.wait_for_ready()


@pytest.fixture(scope="session")
def kuadrant(request, testconfig):
    """Returns Kuadrant instance if exists, or None"""
    if request.config.getoption("--standalone"):
        return None

    ocp = testconfig["cluster"]
    project = testconfig["service_protection"]["system_project"]
    kuadrant_openshift = ocp.change_project(project)

    with kuadrant_openshift.context:
        kuadrant = selector("kuadrant").object(cls=KuadrantCR)

    return kuadrant


@pytest.fixture(scope="session")
def backend(request, cluster, blame, label, testconfig):
    """Deploys Httpbin backend"""
    image = testconfig["httpbin"]["image"]
    httpbin = Httpbin(cluster, blame("httpbin"), label, image)
    request.addfinalizer(httpbin.delete)
    httpbin.commit()
    return httpbin


@pytest.fixture(scope="session")
def gateway(request, kuadrant, cluster, blame, label, testconfig, wildcard_domain) -> Gateway:
    """Deploys Gateway that wires up the Backend behind the reverse-proxy and Authorino instance"""
    if kuadrant:
        gw = KuadrantGateway.create_instance(cluster, blame("gw"), wildcard_domain, {"app": label})
    else:
        authorino = request.getfixturevalue("authorino")
        gw = Envoy(
            cluster,
            blame("gw"),
            authorino,
            testconfig["service_protection"]["envoy"]["image"],
            labels={"app": label},
        )
    request.addfinalizer(gw.delete)
    gw.commit()
    gw.wait_for_ready()
    return gw


@pytest.fixture(scope="module")
def hostname(gateway, exposer, blame) -> Hostname:
    """Exposed Hostname object"""
    hostname = exposer.expose_hostname(blame("hostname"), gateway)
    return hostname


@pytest.fixture(scope="module")
def route(request, kuadrant, gateway, blame, hostname, backend, module_label) -> GatewayRoute:
    """Route object"""
    if kuadrant:
        route = HTTPRoute.create_instance(gateway.cluster, blame("route"), gateway, {"app": module_label})
    else:
        route = EnvoyVirtualRoute.create_instance(gateway.cluster, blame("route"), gateway)
    route.add_hostname(hostname.hostname)
    route.add_backend(backend)
    request.addfinalizer(route.delete)
    route.commit()
    return route


@pytest.fixture(scope="module")
def client(route, hostname):  # pylint: disable=unused-argument
    """Returns httpx client to be used for requests"""
    client = hostname.client()
    yield client
    client.close()
