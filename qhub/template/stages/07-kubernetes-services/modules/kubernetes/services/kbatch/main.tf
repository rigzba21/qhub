resource "helm_release" "kbatch" {
  name       = "kbatch"
  namespace  = var.namespace
  repository = "https://kbatch-dev.github.io/helm-chart"
  chart      = "kbatch-proxy"
  version    = "0.3.1"

  values = concat([
    file("${path.module}/values.yaml"),
    jsonencode({
      app = {
        jupyterhub_api_token = var.jupyterhub_api_token
        jupyterhub_api_url = "https://${var.external-url}/hub/api/"
        extra_env = {
          KBATCH_PREFIX = "/services/kbatch"
          # KBATCH_JOB_EXTRA_ENV = {
          #   "DASK_GATEWAY__AUTH__TYPE": "jupyterhub",
          #   "DASK_GATEWAY__CLUSTER__OPTIONS__IMAGE": "{JUPYTER_IMAGE_SPEC}",
          #   "DASK_GATEWAY__ADDRESS":  "https://<JUPYTERHUB_URL>/services/dask-gateway",
          #   "DASK_GATEWAY__PROXY_ADDRESS": "gateway://<DASK_GATEWAY_ADDRESS>:80"
          # }
        }
      }
      image = {
          tag = "0.3.1"
      }
    })
  ])

  set_sensitive {
    name  = "jupyterHubToken"
    value = var.jupyterhub_api_token
  }

  set {
    name  = "kbatchImage"
    value = var.image
  }

  set {
    name  = "namespace"
    value = var.namespace
  }

}

resource "kubernetes_cluster_role" "kbatch" {
  metadata {
    name = "${var.name}-kbatch"
  }

  rule {
    api_groups = ["", "batch"]
    resources  = ["*"]
    verbs      = ["get", "watch", "list", "patch", "create"]
  }

  rule {
    api_groups = ["gateway.dask.org"]
    resources  = ["daskclusters"]
    verbs      = ["*"]
  }
}


resource "kubernetes_cluster_role_binding" "kbatch" {
  metadata {
    name = "${var.name}-kbatch"
    namespace = var.namespace
  }

  role_ref {
    api_group = "rbac.authorization.k8s.io"
    kind      = "ClusterRole"
    name      = kubernetes_cluster_role.kbatch.metadata.0.name
  }
  subject {
    kind      = "ServiceAccount"
    name      = kubernetes_service_account.kbatch.metadata.0.name
    namespace = var.namespace
    api_group = ""
  }
}
