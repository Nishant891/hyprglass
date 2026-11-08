#!/usr/bin/env bash
set -euo pipefail
base=$(cd -- "$(dirname -- "$0")/../../.." && pwd)
if [[ ${1:-} == --print-metadata ]]; then
    exec "$base/bin/hypr-glass" build-metadata
fi
for tool in git cc meson ninja valac blueprint-compiler sassc pkg-config glib-compile-schemas; do
    command -v "$tool" >/dev/null || { echo "Missing build tool: $tool" >&2; exit 1; }
done
mkdir -p "$base/tools"
exec 9>"$base/tools/.swaync-build.lock"
flock 9
build_root=$(mktemp -d "$base/tools/.swaync-build.XXXXXX")
destination="$base/tools/swaync"
cleanup() {
    if [[ -d "$build_root/previous" && ! -e "$destination" ]]; then
        mv -- "$build_root/previous" "$destination"
    fi
    rm -rf -- "$build_root"
}
trap cleanup EXIT
"$base/bin/hypr-glass" build-metadata >"$build_root/build-metadata.json"
git -c core.hooksPath=/dev/null clone --quiet --depth 1 --branch v0.12.6 \
    "${HYPR_GLASS_SWAYNC_SOURCE:-https://github.com/ErikReider/SwayNotificationCenter.git}" "$build_root/source"
source_dir="$build_root/source"
[[ $(git -C "$source_dir" rev-parse HEAD) == 1043ef98ec97a27e24192a726576fce807d2ee49 ]] || {
    echo 'SwayNC source does not match the pinned revision.' >&2; exit 1;
}
git -C "$source_dir" apply "$base/hyprglass/sidebar/native/swaync.patch"
cp "$base/hyprglass/sidebar/native/todo.vala" "$source_dir/src/controlCenter/widgets/todo.vala"
meson setup "$build_root/build" "$source_dir" --buildtype=release \
    -Dman-pages=false -Dsystemd-service=false -Dzsh-completions=false \
    -Dbash-completions=false -Dfish-completions=false
ninja -C "$build_root/build" -j 4
staging="$build_root/install"
mkdir -p "$staging/bin"
for binary in swaync swaync-client; do
    install -m 755 "$build_root/build/src/$binary" "$staging/bin/$binary"
done
install -m 644 "$build_root/build/data/style/style.css" "$staging/style.css"
install -m 644 "$source_dir/COPYING" "$staging/COPYING"
install -m 644 "$build_root/build-metadata.json" "$staging/build-metadata.json"
mkdir -p "$staging/schemas"
install -m 644 "$source_dir/data/org.erikreider.swaync.gschema.xml" "$staging/schemas/"
glib-compile-schemas "$staging/schemas"
if [[ -e "$destination" ]]; then mv -- "$destination" "$build_root/previous"; fi
mv -- "$staging" "$destination"
