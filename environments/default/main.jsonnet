local k = import 'github.com/grafana/jsonnet-libs/ksonnet-util/kausal.libsonnet';

{
  config:: {
    name: "provider",
    sts: {
      image: std.join(":", [std.extVar("IMAGE_NAME"), std.extVar("IMAGE_TAG")]),
    },
  },

  local sts = k.apps.v1.statefulSet,
  local container = k.core.v1.container,
  local secret = k.core.v1.secret,
  local envFromSource = k.core.v1.envFromSource,

  bot: {
    statefulset: sts.new(
      name=$.config.name,
      replicas=1,
      containers=[
        container.new(
          $.config.name,
          $.config.sts.image
        ) + container.withEnvFrom([
          envFromSource.secretRef.withName($.config.name),
        ]) + container.withResourcesRequests(
          cpu='50m',
          memory='50Mi'
        ) + container.withResourcesLimits(
          cpu='1',
          memory='300Mi'
        ) + container.withImagePullPolicy('IfNotPresent'),
      ],
    ),
    secret: secret.new(
      name=$.config.name,
      data={
        BOT_TOKEN: std.extVar('BOT_TOKEN'),
      }
    ),
  },
}
