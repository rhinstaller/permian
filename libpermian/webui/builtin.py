import logging
import magic
import mimetypes
from flask import Blueprint, render_template, jsonify, request, redirect, Response

from ..exceptions import RemoteLogError
from .server import WebUI
from .request import currentWebUI, currentPipeline
from ..result import RESULTS, STATES

main = Blueprint('main', __name__)
WebUI.registerBlueprint(main)

LOGGER = logging.getLogger(__name__)

@main.app_template_filter()
def sort_crcs(crcs):
    return sorted(crcs, key=lambda crc: crc.testcase.name)

@main.route('/')
def index():
    pipeline=currentPipeline()
    filter_data = {'results': list(RESULTS.keys()),
                   'states': list(STATES.keys()),
                   'workflows': pipeline.testRuns.caseRunConfigurations.by_workflowType().keys()}
    return render_template('index.html', pipeline=pipeline, filter_data=filter_data)

@main.route('/pipeline_data')
def pipeline_data():
    """ Converts data from pipeline into json, that can be easily parsed in javascript

    :return: json data
    :rtype: flask.Response
    """
    pipeline = currentPipeline()
    caseRuns = list()

    if not pipeline.testRuns:
        return jsonify(caseRuns)

    for caserun in pipeline.testRuns.caseRunConfigurations:
        caserun_data = {'name': caserun.testcase.name,
                        'id': caserun.id,
                        'configuration': caserun.configuration,
                        'workflow': caserun.testcase.execution['type'],
                        'display_status': caserun.workflow.groupDisplayStatus(caserun.id),
                        'running_for': [ tp_id for tp_id, tp_bool in caserun.running_for.items() if tp_bool ],
                        'result': caserun.result.result,
                        'state' : caserun.result.state,
                        'logs' : list(caserun.logs.keys()),
                        'active' : not caserun.result.final,
                       }

        caseRuns.append(caserun_data)

    return jsonify(caseRuns)

@main.route('/logs/<crcid>/<path:name>')
def logs(crcid, name):
    pipeline = currentPipeline()
    try:
        with pipeline.testRuns.caseRunConfigurations[crcid].openLogfile(name, mode='rb') as logfile:
            data = logfile.read()
            mimetype = mimetypes.guess_type(logfile.name)[0] or magic.detect_from_content(data).mime_type
            return Response(data, mimetype=mimetype)
    except RemoteLogError as e:
        return redirect(e.log_path)

@main.route('/cancel')
def cancel():
    crc_id = request.args.get('crc_id')
    plan_name = request.args.get('plan_name')
    cancel_all = request.args.get('all')
    pipeline = currentPipeline()

    if crc_id:
        pipeline.testRuns.caseRunConfigurations[crc_id].cancel('WebUI cancel')
    elif plan_name:
        for crc in pipeline.testRuns.caseRunConfigurations.by_testplan()[plan_name]:
            crc.cancel('WebUI cancel')
    elif cancel_all:
        for crc in pipeline.testRuns.caseRunConfigurations:
            crc.cancel('WebUI cancel')

    return jsonify(True)

@main.route('/cancel_filtered')
def cancel_filtered():
    crc_ids = request.args.get('crc_ids').split(';')
    plan_name = request.args.get('plan_name')
    pipeline = currentPipeline()

    if plan_name:
        for crc in pipeline.testRuns.caseRunConfigurations.by_testplan()[plan_name]:
            if crc.id in crc_ids:
                crc.cancel('WebUI cancel')
    else:
        for crc_id in crc_ids:
            pipeline.testRuns.caseRunConfigurations[crc_id].cancel('WebUI cancel')

    return jsonify(True)

@main.route('/webUIuuid')
def webUIuuid():
    return currentWebUI().uuid
