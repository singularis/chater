import kopf
import kubernetes
from kubernetes import client, config


# Handler for when the CR is created
@kopf.on.create("chater.example.com", "v1", "chatergpts")
def create_chater_gpt(spec, **kwargs):
    """
    This function is triggered when a new ChaterGpt custom resource is created.
    It will:
      1) Create (or verify) a Namespace.
      2) Create a Secret with openAIAPIKey and secretKey.
      3) Create a Deployment referencing the env variables.
    """
    namespace = spec.get("namespace")
    bootstrap_server = spec.get("bootstrapServer")
    model = spec.get("model")
    vision_model = spec.get("visionModel")
    openai_api_key_b64 = spec.get("openAIAPIKey")
    secret_key_b64 = spec.get("secretKey")
    replicas = spec.get("replicas", 1)
    affinity = spec.get("affinity")

    config.load_incluster_config()
    api_client = client.ApiClient()
    core_api = client.CoreV1Api(api_client)
    apps_api = client.AppsV1Api(api_client)

    # Ensure the namespace exists
    namespace_body = client.V1Namespace(metadata=client.V1ObjectMeta(name=namespace))
    try:
        core_api.create_namespace(namespace_body)
        kopf.info(
            objs=kwargs["body"],
            reason="Created",
            message=f"Created Namespace: {namespace}",
        )
    except kubernetes.client.exceptions.ApiException as e:
        if e.status == 409:
            # Already exists
            kopf.info(
                objs=kwargs["body"],
                reason="Exists",
                message=f"Namespace {namespace} already exists.",
            )
        else:
            raise

    # Create the secret
    secret_body = client.V1Secret(
        api_version="v1",
        kind="Secret",
        metadata=client.V1ObjectMeta(name="chater-gpt", namespace=namespace),
        data={"OPENAI_API_KEY": openai_api_key_b64, "SECRET_KEY": secret_key_b64},
    )
    try:
        core_api.create_namespaced_secret(namespace=namespace, body=secret_body)
        kopf.info(
            objs=kwargs["body"], reason="Created", message="Created Secret chater-gpt."
        )
    except kubernetes.client.exceptions.ApiException as e:
        if e.status == 409:
            core_api.patch_namespaced_secret(
                name="chater-gpt", namespace=namespace, body=secret_body
            )
            kopf.info(
                objs=kwargs["body"],
                reason="Patched",
                message="Patched existing Secret chater-gpt.",
            )
        else:
            raise

    # Define the container using env vars from the Secret and CR spec
    is_dev = str(spec.get("isDev", "false")).lower() == "true"
    image_name = "docker.io/singularis314/chater-gpt-dev:0.3" if is_dev else "docker.io/singularis314/chater-gpt:0.3"
    container = client.V1Container(
        name="chater-gpt",
        image=image_name,
        image_pull_policy="Always",
        env=[
            client.V1EnvVar(
                name="OPENAI_API_KEY",
                value_from=client.V1EnvVarSource(
                    secret_key_ref=client.V1SecretKeySelector(
                        name="chater-gpt", key="OPENAI_API_KEY"
                    )
                ),
            ),
            client.V1EnvVar(
                name="SECRET_KEY",
                value_from=client.V1EnvVarSource(
                    secret_key_ref=client.V1SecretKeySelector(
                        name="chater-gpt", key="SECRET_KEY"
                    )
                ),
            ),
            client.V1EnvVar(name="BOOTSTRAP_SERVER", value=bootstrap_server),
            client.V1EnvVar(name="MODEL", value=model),
            client.V1EnvVar(name="VISION_MODEL", value=vision_model),
            client.V1EnvVar(name="IS_DEV", value=str(spec.get("isDev", "false")).lower()),
        ],
    )

    pod_spec = client.V1PodSpec(containers=[container])
    if affinity is not None:
        pod_spec.affinity = affinity

    pod_template = client.V1PodTemplateSpec(
        metadata=client.V1ObjectMeta(
            labels={"app": "chater-gpt"},
            annotations={"co.elastic.logs/enabled": "true"},
        ),
        spec=pod_spec,
    )

    deployment_spec = client.V1DeploymentSpec(
        replicas=replicas,
        selector=client.V1LabelSelector(match_labels={"app": "chater-gpt"}),
        template=pod_template,
    )

    deployment_body = client.V1Deployment(
        api_version="apps/v1",
        kind="Deployment",
        metadata=client.V1ObjectMeta(name="chater-gpt", namespace=namespace),
        spec=deployment_spec,
    )

    try:
        apps_api.create_namespaced_deployment(namespace=namespace, body=deployment_body)
        kopf.info(
            objs=kwargs["body"],
            reason="Created",
            message="Created Deployment chater-gpt.",
        )
    except kubernetes.client.exceptions.ApiException as e:
        if e.status == 409:
            apps_api.patch_namespaced_deployment(
                name="chater-gpt", namespace=namespace, body=deployment_body
            )
            kopf.info(
                objs=kwargs["body"],
                reason="Patched",
                message="Patched existing Deployment chater-gpt.",
            )
        else:
            raise

    return {"message": "chater-gpt Operator handling complete"}


# New update handler to react to changes in the CRD's spec
@kopf.on.update("chater.example.com", "v1", "chatergpts")
def update_chater_gpt(spec, **kwargs):
    """
    This handler is triggered whenever the CRD is updated.
    It patches the Secret and Deployment to update environment variables accordingly.
    """
    namespace = spec.get("namespace")
    bootstrap_server = spec.get("bootstrapServer")
    model = spec.get("model")
    vision_model = spec.get("visionModel")
    openai_api_key_b64 = spec.get("openAIAPIKey")
    secret_key_b64 = spec.get("secretKey")
    replicas = spec.get("replicas", 1)
    affinity = spec.get("affinity")
    is_dev = str(spec.get("isDev", "false")).lower() == "true"
    image_name = "docker.io/singularis314/chater-gpt-dev:0.3" if is_dev else "docker.io/singularis314/chater-gpt:0.3"

    config.load_incluster_config()
    api_client = client.ApiClient()
    core_api = client.CoreV1Api(api_client)
    apps_api = client.AppsV1Api(api_client)

    # Patch the secret with the new keys
    secret_patch = {
        "data": {"OPENAI_API_KEY": openai_api_key_b64, "SECRET_KEY": secret_key_b64}
    }
    try:
        core_api.patch_namespaced_secret(
            name="chater-gpt", namespace=namespace, body=secret_patch
        )
        kopf.info(
            objs=kwargs["body"],
            reason="Updated",
            message="Patched Secret chater-gpt with updated keys.",
        )
    except kubernetes.client.exceptions.ApiException as e:
        raise

    # Patch the deployment to update the environment variables
    # Here we patch the container within the Deployment template.
    deployment_patch = {
        "spec": {
            "replicas": replicas,
            "template": {
                "spec": {
                    "containers": [
                        {
                            "name": "chater-gpt",
                            "image": image_name,
                            "env": [
                                {
                                    "name": "OPENAI_API_KEY",
                                    "valueFrom": {
                                        "secretKeyRef": {
                                            "name": "chater-gpt",
                                            "key": "OPENAI_API_KEY",
                                        }
                                    },
                                },
                                {
                                    "name": "SECRET_KEY",
                                    "valueFrom": {
                                        "secretKeyRef": {
                                            "name": "chater-gpt",
                                            "key": "SECRET_KEY",
                                        }
                                    },
                                },
                                {"name": "BOOTSTRAP_SERVER", "value": bootstrap_server},
                                {"name": "MODEL", "value": model},
                                {"name": "VISION_MODEL", "value": vision_model},
                                {
                                    "name": "IS_DEV",
                                    "value": str(spec.get("isDev", "false")).lower(),
                                },
                            ],
                        }
                    ]
                }
            },
        }
    }
    if affinity is not None:
        deployment_patch["spec"]["template"]["spec"]["affinity"] = affinity
    try:
        apps_api.patch_namespaced_deployment(
            name="chater-gpt", namespace=namespace, body=deployment_patch
        )
        kopf.info(
            objs=kwargs["body"],
            reason="Updated",
            message="Patched Deployment chater-gpt with updated env variables.",
        )
    except kubernetes.client.exceptions.ApiException as e:
        raise

    return {"message": "Updated chater-gpt resources with new env variables."}


# Ensure desired state after operator restarts
@kopf.on.resume("chater.example.com", "v1", "chatergpts")
def resume_chater_gpt(spec, **kwargs):
    namespace = spec.get("namespace")
    bootstrap_server = spec.get("bootstrapServer")
    model = spec.get("model")
    vision_model = spec.get("visionModel")
    openai_api_key_b64 = spec.get("openAIAPIKey")
    secret_key_b64 = spec.get("secretKey")
    replicas = spec.get("replicas", 1)
    affinity = spec.get("affinity")
    is_dev = str(spec.get("isDev", "false")).lower() == "true"
    image_name = "docker.io/singularis314/chater-gpt-dev:0.3" if is_dev else "docker.io/singularis314/chater-gpt:0.3"

    config.load_incluster_config()
    api_client = client.ApiClient()
    core_api = client.CoreV1Api(api_client)
    apps_api = client.AppsV1Api(api_client)

    # Ensure Secret exists and matches desired state
    secret_patch = {
        "data": {"OPENAI_API_KEY": openai_api_key_b64, "SECRET_KEY": secret_key_b64}
    }
    try:
        core_api.patch_namespaced_secret(
            name="chater-gpt", namespace=namespace, body=secret_patch
        )
    except kubernetes.client.exceptions.ApiException as e:
        if e.status == 404:
            secret_body = client.V1Secret(
                api_version="v1",
                kind="Secret",
                metadata=client.V1ObjectMeta(name="chater-gpt", namespace=namespace),
                data={
                    "OPENAI_API_KEY": openai_api_key_b64,
                    "SECRET_KEY": secret_key_b64,
                },
            )
            core_api.create_namespaced_secret(namespace=namespace, body=secret_body)
        else:
            raise

    # Reconcile Deployment
    deployment_patch = {
        "spec": {
            "replicas": replicas,
            "template": {
                "spec": {
                    "containers": [
                        {
                            "name": "chater-gpt",
                            "image": image_name,
                            "env": [
                                {
                                    "name": "OPENAI_API_KEY",
                                    "valueFrom": {
                                        "secretKeyRef": {
                                            "name": "chater-gpt",
                                            "key": "OPENAI_API_KEY",
                                        }
                                    },
                                },
                                {
                                    "name": "SECRET_KEY",
                                    "valueFrom": {
                                        "secretKeyRef": {
                                            "name": "chater-gpt",
                                            "key": "SECRET_KEY",
                                        }
                                    },
                                },
                                {"name": "BOOTSTRAP_SERVER", "value": bootstrap_server},
                                {"name": "MODEL", "value": model},
                                {"name": "VISION_MODEL", "value": vision_model},
                                {
                                    "name": "IS_DEV",
                                    "value": str(spec.get("isDev", "false")).lower(),
                                },
                            ],
                        }
                    ]
                }
            },
        }
    }
    if affinity is not None:
        deployment_patch["spec"]["template"]["spec"]["affinity"] = affinity

    try:
        apps_api.patch_namespaced_deployment(
            name="chater-gpt", namespace=namespace, body=deployment_patch
        )
    except kubernetes.client.exceptions.ApiException as e:
        if e.status == 404:
            # Create Deployment from scratch if missing
            container = client.V1Container(
                name="chater-gpt",
                image=image_name,
                image_pull_policy="Always",
                env=[
                    client.V1EnvVar(
                        name="OPENAI_API_KEY",
                        value_from=client.V1EnvVarSource(
                            secret_key_ref=client.V1SecretKeySelector(
                                name="chater-gpt", key="OPENAI_API_KEY"
                            )
                        ),
                    ),
                    client.V1EnvVar(
                        name="SECRET_KEY",
                        value_from=client.V1EnvVarSource(
                            secret_key_ref=client.V1SecretKeySelector(
                                name="chater-gpt", key="SECRET_KEY"
                            )
                        ),
                    ),
                    client.V1EnvVar(name="BOOTSTRAP_SERVER", value=bootstrap_server),
                    client.V1EnvVar(name="MODEL", value=model),
                    client.V1EnvVar(name="VISION_MODEL", value=vision_model),
                    client.V1EnvVar(
                        name="IS_DEV", value=str(spec.get("isDev", "false")).lower()
                    ),
                ],
            )
            pod_spec = client.V1PodSpec(containers=[container])
            if affinity is not None:
                pod_spec.affinity = affinity
            pod_template = client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(
                    labels={"app": "chater-gpt"},
                    annotations={"co.elastic.logs/enabled": "true"},
                ),
                spec=pod_spec,
            )
            deployment_spec = client.V1DeploymentSpec(
                replicas=replicas,
                selector=client.V1LabelSelector(match_labels={"app": "chater-gpt"}),
                template=pod_template,
            )
            deployment_body = client.V1Deployment(
                api_version="apps/v1",
                kind="Deployment",
                metadata=client.V1ObjectMeta(name="chater-gpt", namespace=namespace),
                spec=deployment_spec,
            )
            apps_api.create_namespaced_deployment(
                namespace=namespace, body=deployment_body
            )
        else:
            raise


# Periodic reconciliation to constantly check and apply CR changes
@kopf.timer("chater.example.com", "v1", "chatergpts", interval=60.0)
def reconcile_timer(spec, **kwargs):
    return resume_chater_gpt(spec, **kwargs)
