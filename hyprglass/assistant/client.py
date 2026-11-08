"""JSON requests to the local Ollama server."""
import json
from urllib.request import Request, ProxyHandler, build_opener

LOCAL = build_opener(ProxyHandler({}))


def local_request(base, path, body=None, method=None, timeout=12):
    request = Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                      headers={'Content-Type': 'application/json'}, method=method)
    with LOCAL.open(request, timeout=timeout) as response:
        return json.load(response)
