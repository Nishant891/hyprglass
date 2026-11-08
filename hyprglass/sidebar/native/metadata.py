"""Fingerprint the pinned sidebar source, local inputs, and linked libraries."""
import hashlib
import json
from pathlib import Path
import subprocess

from hyprglass.install.dependencies import LIBRARIES, version

SOURCE = '1043ef98ec97a27e24192a726576fce807d2ee49'


def metadata():
    directory = Path(__file__).resolve().parent
    inputs = {}
    for name in ('build.sh', 'metadata.py', 'swaync.patch', 'todo.vala'):
        inputs[name] = hashlib.sha256((directory / name).read_bytes()).hexdigest()
    libraries = {}
    for library, (minimum, _) in LIBRARIES.items():
        result = subprocess.run(['pkg-config', '--modversion', library],
                                capture_output=True, text=True, check=True)
        detected = result.stdout.strip()
        if minimum and version(detected) < version(minimum):
            raise ValueError(f'{library} >= {minimum} required; found {detected}')
        libraries[library] = detected
    return {'source': SOURCE, 'inputs': inputs, 'libraries': libraries}


if __name__ == '__main__':
    print(json.dumps(metadata(), sort_keys=True))
