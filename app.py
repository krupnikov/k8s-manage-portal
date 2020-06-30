import secrets
import yaml

import kube
from flask import Flask, render_template, request, send_file
from  flask_bootstrap import Bootstrap
from flask_htmlmin import HTMLMIN

def cleanNullTerms(data):
   clean = {}
   for key, value in data.items():
       if isinstance(value, dict):
           nested = cleanNullTerms(value)
           if len(nested.keys()) > 0:
               clean[key] = nested
       elif value is not None:
           clean[key] = value
   return clean

def create_app(configfile=None):
    app = Flask(__name__)
    app.config['MINIFY_HTML'] = True
    app.secret_key = secrets.token_urlsafe(16)

    Bootstrap(app)

    HTMLMIN(app)

    @app.route('/', methods=['GET', 'POST'])
    def main():
        if request.method == 'GET':
            return render_template('base.html', title='ipevctl')
        if request.method == 'POST':
            label = request.form.get('service')
            if request.form.get('do_deployment_restart'):
                target = request.form.get('do_deployment_restart')
                kube.main('restart', label, target)
            if request.form.get('do_deployment_start'):
                target = request.form.get('do_deployment_start')
                kube.main('start', label, target)
            if request.form.get('do_deployment_stop'):
                target = request.form.get('do_deployment_stop')
                kube.main('stop', label, target)
            data = kube.main('get', label)
            namespace = [x for x in data.keys()]
            return render_template('get.html', title='ipevctl', namespace=namespace, data=data, label=label)

    @app.route('/downloadfile/<name>', methods=['GET', 'POST'])
    def get_deployment(name):
        tmpdir = request.form['create_file']
        filename = str(name) + '.yml'
        return send_file(tmpdir + filename,
                         as_attachment=True,
                         attachment_filename=filename,
                         mimetype='text/x-yaml')

    @app.route('/view', methods=['GET', 'POST'])
    def get_template_info():
        output_configmap = {}
        req = request.form['get_pods'].split(' ')
        try:
            data = kube.main('get_pod_info', req[0], req[1], req[2])
            pods_info, deployment, configmap = dict(data[0]), data[1][0], data[2]
            if configmap != None:
                configmap = configmap.to_dict()
                output_configmap['name'] = configmap['metadata']['name']
                output_configmap['namespace'] = configmap['metadata']['namespace']
                for k, v in configmap['data'].items():
                    output_configmap['data_key'] = k
                    output_configmap['data_value'] = v
            else:
                output_configmap = None
            deployment_spec = yaml.dump(cleanNullTerms(deployment.spec.template.spec.to_dict()))
            return render_template('view.html', data=pods_info, deployment=deployment_spec,
                                   deployment_name=deployment.metadata.name, tmpdir=data[1][1], configmap=output_configmap)
        except Exception as ex:
            return render_template('view.html')

    @app.route('/view/update-configmap', methods=['GET', 'POST'])
    def do_update_configmap():
        req = request.form['update_configmap']
        data_value = yaml.dump(yaml.load(req))
        if str('configmap_cred') in request.form:
            cred = request.form['configmap_cred'].split(' ')
            namespace, configmap_name, data_key = cred[0], cred[1], cred[2]
            body = {data_key: data_value}
            kube.do_update_configmap(context=namespace, namespace=namespace, name=configmap_name, body_data=body)
        else:
            cred = request.form['pod_restart'].split(' ')
            namespace, configmap_name, data_key = cred[0], cred[1], cred[2]
            deployment_name = cred[3]
            body = {data_key: req}
            kube.do_update_configmap(namespace=namespace, name=configmap_name, body_data=body)
            kube.do_deployment_restart(context=namespace, deployment=deployment_name, namespace=namespace)
        return render_template('view.html')

    return app


if __name__ == '__main__':
    create_app().run(host='0.0.0.0', debug=True)
