"""Private supervised HTTP process. Do not invoke as a benchmark entry point."""
import json
from pathlib import Path
import sys

from .common import write_json
from .execution import _http_request


def main():
    request = json.loads(Path(sys.argv[1]).read_text())
    try:
        result = _http_request(request['config'], Path(request['workspace']), request['task'],
                               request['timeout'], Path(request['logdir']))
    except (ValueError, RuntimeError, TypeError, KeyError) as exc:
        result = {"status": "infra_error", "reason": type(exc).__name__, "seconds": 0}
    write_json(sys.argv[2], result)


if __name__ == '__main__':main()
