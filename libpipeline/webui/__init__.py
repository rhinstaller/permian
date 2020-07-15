import threading
import logging
import requests
import time
import socket
import uuid
import flask
from flask import Flask, Blueprint

from ..hooks.register import run_on, run_threaded_on
from . import hooks

LOGGER = logging.getLogger(__name__)
WERKZEUG_LOGGER = logging.getLogger("werkzeug")
WERKZEUG_LOGGER.setLevel(logging.ERROR)

def get_port(port):
    if isinstance(port, int):
        return port
    if port == 'random':
        return get_random_free_port()
    raise ValueError(f'Unrecognized port value: {port!r}')

def get_random_free_port():
    return 1234

def get_ip():
    return socket.gethostbyname(socket.gethostname())

@run_threaded_on(hooks.WebUI_starting)
def signalWhenStarted(webUI):
    while True:
        try:
            response = requests.get(f'{webUI.address}webUIuuid') # TODO: Fix the URL creation
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
    LOGGER.info(f'WebUI started at: {webUI.address}')

@run_on(hooks.WebUI_started)
def waitAWhile(webUI):
    time.sleep(30)

class WebUI(threading.Thread):
    def __init__(self, pipeline):
        super().__init__(daemon=True)
        self.app = Flask(__name__)
        self.app.register_blueprint(main)
        self.pipeline = pipeline
        self.listen_ip = self.config('listen_ip')
        self.port = None # delay obtaining the port until the very moment before the flask app is started to limit potential random port collision
        self._operationalLock = threading.Lock()
        self._operationalLock.acquire() # immediately acquire the lock as the webUI is not running yet
        self.uuid = uuid.uuid4().hex
        self.app.config.update(
            ENV='embedded',
            pipeline=self.pipeline,
            webUI=self,
        )

    def run(self):
        self.port = get_port(self.config('port'))
        hooks.WebUI_starting(self)
        self.app.run(self.listen_ip, self.port)

    def config(self, option):
        if option == 'listen_ip': # TODO: Remove me
            return '0.0.0.0'
        if option == 'port': # TODO: Remove me
            return 'random'
        return self.pipeline.config.get('WebUI', option)

    @property
    def address(self):
        return f'http://{get_ip()}:{self.port}/'

    def waitUntilStarted(self):
        # just wait for operational lock to be released
        with self._operationalLock:
            pass

    def unlock(self):
        LOGGER.debug(f'Unlocking webUI {self}')
        hooks.WebUI_started(self)
        self._operationalLock.release()

def currentWebUI():
    return flask.current_app.config['webUI']

def currentPipeline():
    return flask.current_app.config['pipeline']

main = Blueprint('main', __name__)

@main.route('/')
def index():
    return 'Hello!'

@main.route('/webUIuuid')
def webUIuuid():
    return currentWebUI().uuid
