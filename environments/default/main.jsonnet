local k = import 'github.com/grafana/jsonnet-libs/ksonnet-util/kausal.libsonnet';

{
  config:: {
    sts: {
      name: 'provider',
      image: std.extVar("IMAGE_NAME"),
    },
    secret: {
      name: 'provider',
    },
  },

  local sts = k.apps.v1.statefulSet,
  local container = k.core.v1.container,
  local secret = k.core.v1.secret,
  local envFromSource = k.core.v1.envFromSource,

  bot: {
    deployment: sts.new(
      name=$.config.sts.name,
      replicas=1,
      containers=[
        container.new(
          $.config.sts.name,
          $.config.sts.image
        ) + container.withEnvFrom([
          envFromSource.secretRef.withName($.config.secret.name),
        ]) + container.withResourcesRequests(
          cpu='50m',
          memory='50Mi'
        ) + container.withResourcesLimits(
          cpu='300m',
          memory='300Mi'
        ) + container.withImagePullPolicy('IfNotPresent'),
      ],
    ),
    secret: secret.new(
      name=$.config.secret.name,
      data={
        BOT_TOKEN: std.extVar('BOT_TOKEN'),
      }
    ),
  },
}
