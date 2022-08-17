"""Conftest for all tests requiring custom deployment of Authorino"""
import pytest
from weakget import weakget

from testsuite.openshift.objects.authorino import AuthorinoCR


@pytest.fixture(scope="module")
def authorino_parameters():
    """Optional parameters for Authorino creation, passed to the __init__"""
    return {}


@pytest.fixture(scope="module")
def cluster_wide():
    """True, if Authorino should be deployed in cluster-wide setup"""
    return False


@pytest.fixture(scope="module")
def authorino(openshift, blame, request, testconfig, cluster_wide, label, authorino_parameters) -> AuthorinoCR:
    """Custom deployed Authorino instance"""
    if not testconfig["authorino"]["deploy"]:
        return pytest.skip("Operator tests don't work with already deployed Authorino")

    parameters = {"label_selectors": [f"testRun={label}"],
                  **authorino_parameters}
    authorino = AuthorinoCR.create_instance(openshift,
                                            blame("authorino"),
                                            cluster_wide=cluster_wide,
                                            image=weakget(testconfig)["authorino"]["image"] % None,
                                            **parameters)
    request.addfinalizer(lambda: authorino.delete(ignore_not_found=True))
    authorino.commit()
    authorino.wait_for_ready()
    return authorino
