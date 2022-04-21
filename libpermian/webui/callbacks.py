import logging
import requests
import time
import json
import requests
import libxml2
from os import path, mkdir, makedirs

from ..hooks.builtin import pipeline_ended
from ..hooks.register import run_on, run_threaded_on
from . import hooks

LOGGER = logging.getLogger(__name__)
# following lines should be controllable by settings
WERKZEUG_LOGGER = logging.getLogger("werkzeug")
WERKZEUG_LOGGER.setLevel(logging.ERROR)

@run_threaded_on(hooks.WebUI_starting)
def signalWhenStarted(webUI):
    """
    This is hook callback reacting on :py:func:`hooks.WebUI_starting`.

    When the webUI begins starting process, start checking for its availability.
    Once the webUI starts (checking the desired instance is running on the
    expected port), unlock the webUI effectively signalling to others that the
    webUI is fully initialized and ready to accept requests.
    """
    while True:
        try:
            response = requests.get(f'{webUI.baseurl}webUIuuid') # TODO: Fix the URL creation
        except requests.exceptions.ConnectionError:
            # The WebUI is not listening on the port
            if not webUI.is_alive():
                raise Exception(f"WebUI {webUI!r} signaled it's starting but the thread is not alive anymore, maybe it crashed.")
            # the WebUI thread is still running but is not yet binded on the socket
            time.sleep(0.1)
            continue
        if response.status_code == 200:
            # TODO: check uuid of the WebUI instance to detect possible port collision with other pipeline running on the same host
            if response.text != webUI.uuid:
                raise Exception("UUID of the webUI doesn't match. There's some other application/webUI running on the expected port!")
            break
        continue
    webUI.unlock()

@run_on(hooks.WebUI_started)
def webUIStartedMsg(webUI):
    """
    This is hook callback reacting on hooks.WebUI_started.

    Log URL of available webUI.
    """
    LOGGER.info(f'WebUI started at: {webUI.baseurl}')

@run_on(pipeline_ended)
def render_static(pipeline):
    """
    This is hook callback reacting on hooks.builtin.pipeline_ended.

    Creates static version of WebUI that can be accessed after pipeline ends.
    """
    if not pipeline.settings.get('WebUI', 'create_static_webui'):
        return

    LOGGER.info('Generating static WebUI')

    webui_url = pipeline.webUI.baseurl
    webui_path = pipeline.settings.get('WebUI', 'static_webui_dir')
    static_dir = path.join(webui_path, 'static')
    index_path = path.join(webui_path, 'index.html')

    # Create static WebUI directory
    if not path.exists(webui_path):
        makedirs(webui_path)

    # Modify pipeline data
    response = requests.get(webui_url + 'pipeline_data')
    pipline_data = json.loads(response.text)
    for crc in pipline_data:
        # Handle local and external logs
        new_logs = dict()
        for log in crc['logs']:
            url = f'./logs/{crc["id"]}/{log}'
            r = requests.get(webui_url + url.lstrip('./'), allow_redirects=False)
            if r.status_code == 302:
                url = r.next.url
            else:
                url = url + '.txt'
            new_logs[log] = url
        crc['logs'] = new_logs

    with open(path.join(webui_path, 'pipeline_data'), 'w') as fo:
        fo.write(json.dumps(pipline_data))

    # Create dir for static files
    if not path.exists(static_dir):
        mkdir(static_dir)

    def download_static(static_path):
        # Download static files
        r = requests.get(webui_url + static_path.lstrip('/'))
        with open(path.join(static_dir, r.url.split('/')[-1]), 'w') as fo:
            fo.write(r.text)

    # Modify WebUI page
    response = requests.get(webui_url)
    doc = libxml2.parseDoc(response.text)
    for elem in doc.xpathEval('/html/head/*[@href or @src]'):
        href = elem.prop('href')
        if href is not None and href.startswith('/'):
            elem.setProp('href', '.'+href)
            download_static(href)
        src = elem.prop('src')
        if src is not None and src.startswith('/'):
            elem.setProp('src', '.'+src)
            download_static(src)

    head = doc.xpathEval('/html/head')
    script_content = """
        var pipeline_data_url = "./pipeline_data";
        var static_webui = true;
        """
    newElement = head[0].newChild(None, 'script', script_content)
    newElement.newProp('type', 'text/javascript')

    doc.htmlSaveFile(index_path)
    doc.free()
    LOGGER.info('Static WebUI generation is complete')
    hooks.static_WebUI_rendered(pipeline, index_path)
