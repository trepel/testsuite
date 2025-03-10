"""Mockserver implementation as Backend"""

from testsuite.backend import Backend
from testsuite.kubernetes import Selector
from testsuite.kubernetes.deployment import Deployment, ContainerResources
from testsuite.kubernetes.service import Service, ServicePort


class MockserverBackend(Backend):
    """Mockserver deployed as backend in Kubernetes"""

    def commit(self):
        match_labels = {"app": self.label, "deployment": self.name}
        self.deployment = Deployment.create_instance(
            self.cluster,
            self.name,
            container_name="mockserver",
            image="quay.io/mganisin/mockserver:latest",
            ports={"api": 1080},
            selector=Selector(matchLabels=match_labels),
            labels={"app": self.label},
            resources=ContainerResources(limits_memory="2G"),
            lifecycle={"postStart": {"exec": {"command": ["/bin/sh", "init-mockserver"]}}},
        )
        self.deployment.commit()
        self.deployment.wait_for_ready()

        self.service = Service.create_instance(
            self.cluster,
            self.name,
            selector=match_labels,
            ports=[ServicePort(name="1080-tcp", port=8080, targetPort="api")],
            labels={"app": self.label},
            service_type="LoadBalancer",
        )
        self.service.commit()

    def wait_for_ready(self, timeout=300):
        """Waits until Deployment is marked as ready"""
        success = self.service.wait_until(
            lambda obj: "ip" in self.service.refresh().model.status.loadBalancer.ingress[0], timelimit=timeout
        )
        assert success, f"Service {self.name} did not get ready in time"
