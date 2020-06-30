from datetime import datetime, timezone

import urllib3, tempfile, os, yaml
from flask import flash
from kubernetes import client, config
from kubernetes.client.rest import ApiException

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
config.load_kube_config()


def get_deployment_spec(context='', deployment='', namespace=''):
    workdir = tempfile.gettempdir() + '/' + str(namespace) + '/'
    api = client.AppsV1Api(
        api_client=config.new_client_from_config(context=context))
    ret = api.read_namespaced_deployment(name=deployment, namespace=namespace, async_req=True)
    try:
        if os.path.exists(workdir):
            pass
        else:
            os.mkdir(workdir)
        with open(workdir + str(deployment) + '.yml', 'w') as file:
            async_data = ret.get()
            documents = yaml.dump(async_data.to_dict(), file)
    except Exception as e:
        print(e)
    return async_data, workdir


def get_pod_info(context='', selector='', namespace='', deployment=''):
    pods = dict()
    api = client.CoreV1Api(
        api_client=config.new_client_from_config(context=context))
    ret = api.list_namespaced_pod(namespace=namespace, label_selector='app=' + str(selector))
    count = 0
    try:
        deployment_spec = get_deployment_spec(context=context, deployment=deployment, namespace=namespace)
        for pod in ret.items:
            count += 1
            start_time = pod.status.start_time
            now_time = datetime.now(timezone.utc)
            delta_time = now_time - start_time
            pods[count] = {'name': pod.metadata.name,
                           'node': [pod.spec.node_name, pod.status.host_ip],
                           'status': pod.status.phase,
                           'restarts': pod.status.container_statuses[0].restart_count,
                           'age': delta_time,
                           'spec': str(pod.spec.containers)}
            if pod.spec.volumes[0].config_map != None:
                name = pod.spec.volumes[0].config_map.name
                configmap = api.read_namespaced_config_map(name=name, namespace=namespace)
                # print(configmap)
            else:
                configmap = None
        return pods, deployment_spec, configmap
    except ApiException as apiEx:
        return flash(apiEx, "warning")


def get_deployment_info(namespace='', context='', selector=''):
    deployments = dict()
    try:
        api = client.AppsV1Api(api_client=config.load_kube_config(context=context))
        ret = api.list_namespaced_deployment(
            namespace=namespace, pretty='true', label_selector=selector, timeout_seconds='10')
        if len(ret.items) == 0:
            return deployments
        count = 0
        for deployment in ret.items:
            count += 1
            deployments[count] = (deployment.metadata.labels.get("app", ""),
                                  deployment.spec.replicas,
                                  deployment.status.ready_replicas,
                                  deployment.status.unavailable_replicas,
                                  "get_info",
                                  "restart",
                                  "start",
                                  "stop",
                                  deployment.metadata.name)
    except ApiException as ex:
        flash(ex, "warning")
    return deployments


def do_update_configmap(namespace='', name='', body_data={}):
    configuration = client.Configuration()
    configuration.debug = True
    configuration.verify_ssl = False
    body = client.V1ConfigMap(
        api_version="v1",
        data=body_data,
        kind="ConfigMap",
        metadata=client.V1ObjectMeta(
            name=name,
            namespace=namespace
        )
    )
    try:
        api = client.CoreV1Api(client.ApiClient(configuration))
        try:
            req = api.patch_namespaced_config_map(name=name, namespace=namespace, body=body, _request_timeout=30)
            return flash("Update configmap: {0} in namespace {1} is success.".format(str(name), str(namespace)), "info")
        except ApiException as ex:
            return flash("Configmap update wrong: \n {0}".format(ex), "info")
    except Exception as e:
        return flash("Exception when calling CoreV1Api->patch_namespaced_config_map: {0} \n".format(str(e)), "error")


def do_deployment_restart(context='', deployment='', namespace=''):
    try:
        api = client.CoreV1Api(
            api_client=config.new_client_from_config(context=context))
        api.delete_collection_namespaced_pod(
            namespace=namespace, label_selector=set_label_selector(selector=deployment))
    except ApiException as e:
        flash("Exception when calling CoreV1Api->delete_collection_namespaced_pod: {0} \n".format(str(e)), "error")
    pass


def do_deployment_start(context='', deployment='', namespace=''):
    api = client.CoreV1Api(
        api_client=config.new_client_from_config(context=context))
    replicas = api.read_namespaced_config_map(
        deployment + '-replicas', namespace)

    body = {'spec': {'replicas': int(replicas.data.get("replicas"))}}
    api = client.ExtensionsV1beta1Api(api_client=config.new_client_from_config(context=context))
    ret = api.patch_namespaced_deployment_scale(deployment, namespace, body)
    pass


def do_deployment_stop(context='', deployment='', namespace=''):
    body = {'spec': {'replicas': int(0)}}
    api = client.ExtensionsV1beta1Api(
        api_client=config.new_client_from_config(context=context))
    ret = api.patch_namespaced_deployment_scale(deployment, namespace, body)
    pass


def set_label_selector(selector=''):
    if selector == 'all':
        selector = "heritage=Tiller"
    elif selector.startswith('prod') or selector.startswith('uat'):
        selector = "release=" + selector
    else:
        selector = "app=" + selector
    return selector


def get_deployment_list(clusters='', selector=''):
    result = dict()
    for context in clusters:
        data = get_deployment_info(
            namespace=context, context=context, selector=selector)
        if data:
            result[context] = data
    return result


def get_clusters_scope():
    clusters_list = list()
    contexts, active_context = config.list_kube_config_contexts()
    if not contexts:
        flash("Cannot found any context in kube-config file.", "warning")
    for context in contexts:
        clusters_list.append(context['name'])
    return clusters_list


def main(action='', *args):
    try:
        config.load_kube_config()
        if action == 'get':
            return get_deployment_list(clusters=get_clusters_scope(), selector=set_label_selector(selector=args[0]))
        elif action == 'get_pod_info':
            return get_pod_info(context=args[0], selector=args[1], namespace=args[0], deployment=args[2])
        elif action == 'restart':
            flash("Restarting service: " + args[1])
            return do_deployment_restart(context=args[0], deployment=args[1], namespace=args[0])
        elif action == 'start':
            flash("Starting service: " + args[1])
            return do_deployment_start(context=args[0], deployment=args[1], namespace=args[0])
        elif action == 'stop':
            flash("Stoping service: " + args[1])
            return do_deployment_stop(context=args[0], deployment=args[1], namespace=args[0])
        else:
            return flash("Something goes wrong...", "warning")
    except Exception as ex:
        flash(ex, "warning")
