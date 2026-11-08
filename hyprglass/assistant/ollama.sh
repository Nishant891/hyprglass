#!/usr/bin/env bash
set -euo pipefail
base=$(cd -- "$(dirname -- "$0")/../.." && pwd)
runtime=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
binary=$(command -v ollama || true)
if [[ -z "$binary" && -x "$base/tools/ollama/usr/bin/ollama" ]]; then
    binary="$base/tools/ollama/usr/bin/ollama"
    export LD_LIBRARY_PATH="$base/tools/ollama/usr/lib/ollama${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi
[[ -n "$binary" ]] || { echo 'Install Ollama to use local AI.' >&2; exit 1; }
export OLLAMA_HOST=127.0.0.1:11434
export OLLAMA_MODELS="$base/data/ollama/models"
export OLLAMA_NO_CLOUD=1
export OLLAMA_MAX_LOADED_MODELS=1
case ${1:-start} in
    start)
        curl --noproxy '*' -fsS --max-time 1 http://127.0.0.1:11434/api/tags >/dev/null 2>&1 && exit 0
        exec 9>"$runtime/hypr-ollama.lock"
        flock -n 9 || exit 0
        exec "$binary" serve ;;
    *) exec "$binary" "$@" ;;
esac
