#!/bin/sh
# Build MTPro2 Math into out/; see ./build.sh -h.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROG=build.sh

usage() {
    cat <<EOF
usage: $PROG [-h] [-l] [-d FILE] [-V]

Build MTPro2 Math (OpenType and TrueType) from the MathTime Professional 2
fonts in mtpro2/.

options:
  -h, --help        show this help message and exit
  -l, --lite        build MTPro2 Math Lite instead of the full font
  -d, --donor FILE  Roman font for upright Latin letters (default:
                    donor/NimbusRoman-Regular.otf)
  -V, --version     show the version number and exit
EOF
}

usage_error() {
    echo "usage: $PROG [-h] [-l] [-d FILE] [-V]" >&2
    echo "$PROG: error: $1" >&2
    exit 2
}

edition=full
donor=$ROOT/donor/NimbusRoman-Regular.otf
while [ $# -gt 0 ]; do
    case $1 in
    -h | --help)
        usage
        exit 0
        ;;
    -V | --version)
        [ -r "$ROOT/VERSION" ] || {
            echo "$PROG: VERSION not found" >&2
            exit 1
        }
        echo "$PROG $(cat "$ROOT/VERSION")"
        exit 0
        ;;
    -l | --lite)
        edition=lite
        ;;
    -d | --donor)
        [ $# -ge 2 ] || usage_error "argument $1: expected one argument"
        donor=$2
        shift
        ;;
    --donor=*)
        donor=${1#--donor=}
        ;;
    -d?*)
        donor=${1#-d}
        ;;
    *)
        usage_error "unrecognized arguments: $1"
        ;;
    esac
    shift
done

# A relative donor path is taken from the current directory.
case $donor in
/*) ;;
*) donor=$(pwd)/$donor ;;
esac

# Everything the build needs, reported together.
missing=""
if ! command -v python3 >/dev/null 2>&1; then
    missing="$missing python3"
elif ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
    missing="$missing python3>=3.10"
elif ! python3 -c 'import fontTools' 2>/dev/null; then
    missing="$missing fontTools"
fi
command -v tx >/dev/null 2>&1 || missing="$missing tx"
[ -r "$ROOT/VERSION" ] || missing="$missing VERSION"
if [ -n "$missing" ]; then
    echo "$PROG: not found:$missing" >&2
    exit 1
fi

export PYTHONDONTWRITEBYTECODE=1
exec python3 "$ROOT/tools/mtp2otf.py" "$edition" "$donor"
