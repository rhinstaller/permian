import os
import contextlib
import hashlib
import subprocess

import podman

@contextlib.contextmanager
def build_image(client, dockerfile, force=False, autoremove=False):
    images = client.images
    dockerdir = os.path.dirname(dockerfile)
    dockerfile_m = hashlib.sha256()
    with open(dockerfile, 'rb') as dockerfile_fo:
        #while (chunk := dockerfile_fo.read()):
        while True:
            chunk = dockerfile_fo.read()
            if not chunk:
                break
            dockerfile_m.update(chunk)
    dockerfile_checksum = dockerfile_m.hexdigest()
    
    if force or not images.exists(f'localhost/{dockerfile_checksum}'):
        image = images.build(
            path=dockerdir,
            dockerfile=dockerfile,
            tag=f'localhost/{dockerfile_checksum}',
            forcerm=True,
        )
    image = images.get(f'localhost/{dockerfile_checksum}')
    yield image
    if autoremove:
        image.remove()

@contextlib.contextmanager
def run_container(client, image, remove=True, **kwargs):
    cmd = ['cat']
    container = client.containers.create(image, ['cat'], tty=True, **kwargs)
    container.start()
    yield container
    container.kill()
    if remove:
        container.remove()

@contextlib.contextmanager
def dockerfile_container(
        dockerfile,
        use_container=True,
        autoremove=False,
        podman_url=None,
        **kwargs
):
    if not use_container:
        yield NullContainer()
        return
    with (
            podman.PodmanClient(base_url=podman_url)
            if podman_url
            else podman.PodmanClient()
    ) as client:
        with build_image(client, dockerfile, autoremove=autoremove) as image:
            with run_container(client, image, remove=True, **kwargs) as container:
                yield container

class NullContainer():
    def exec_run(self, args):
        proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return (proc.returncode, proc.stdout)
