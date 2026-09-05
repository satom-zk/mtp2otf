#!/bin/sh
set -eu
for arg in "$@"; do
    case "$arg" in
        --family|--family=*)
            echo "error: --family is not supported; Full and Lite use fixed installation names." >&2
            exit 2 ;;
    esac
done
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export MTP2_ROOT="$ROOT"
PYTHON=${MTP2_SYSTEM_PYTHON:-$(command -v python3 || true)}
[ -n "$PYTHON" ] || { echo "error: python3 not found" >&2; exit 1; }
export MTP2_SYSTEM_PYTHON="$PYTHON"
command -v fontforge >/dev/null 2>&1 || { echo "error: fontforge not found" >&2; exit 1; }
command -v tftopl >/dev/null 2>&1 || { echo "error: tftopl not found" >&2; exit 1; }
OUTROOT="$ROOT/out"
# Validate in out/, then retain each edition in its own directory.
OUT="$OUTROOT"
GEN="$ROOT/build/generated"

# Select the edition explicitly; missing Full inputs must not imply Lite.
EDITION=full
ROMAN_REG_ARG=
ROMAN_BOLD_ARG=
for arg in "$@"; do
    case "$arg" in
        --edition=full) EDITION=full ;;
        --edition=lite) EDITION=lite ;;
        --edition=*) echo "error: unknown edition in $arg (expected full or lite)" >&2; exit 2 ;;
        --roman-regular=*) ROMAN_REG_ARG=${arg#--roman-regular=} ;;
        --roman-bold=*) ROMAN_BOLD_ARG=${arg#--roman-bold=} ;;
        --roman-regular|--roman-bold)
            echo "error: use $arg=/path/to/font (the = form is required)" >&2
            exit 2 ;;
        --roman-*) echo "error: unknown Roman-donor option: $arg" >&2; exit 2 ;;
    esac
done
export MTP2_EDITION="$EDITION"
if [ "$EDITION" = lite ]; then FONTBASE=MTPro2MathLite; else FONTBASE=MTPro2Math; fi
export MTP2_FONTBASE="$FONTBASE"

# source_policy.py validates the required source set.
echo "[stage] MTPro2 edition: $EDITION"
mkdir -p "$ROOT/build/pl" "$GEN" "$OUTROOT"
# Clear transient outputs; retain archived editions.
rm -f \
    "$OUTROOT/MTPro2Math.otf" "$OUTROOT/MTPro2Math.ttf" \
    "$OUTROOT/MTPro2MathLite.otf" "$OUTROOT/MTPro2MathLite.ttf"
EDOUT="$OUTROOT/$EDITION"

# Roman donors supply upright/bold Latin; mathematical italic remains MTPro2.
TEXT_REG=${ROMAN_REG_ARG:-${MTP2_ROMAN_REGULAR:-${MTP2_TIMES_REGULAR:-$ROOT/times/NimbusRoman-Regular.otf}}}
TEXT_BOLD=${ROMAN_BOLD_ARG:-${MTP2_ROMAN_BOLD:-${MTP2_TIMES_BOLD:-$ROOT/times/NimbusRoman-Bold.otf}}}
[ -f "$TEXT_REG" ] || { echo "error: missing upright Regular donor: $TEXT_REG" >&2; exit 1; }
[ -f "$TEXT_BOLD" ] || { echo "error: missing upright Bold donor: $TEXT_BOLD" >&2; exit 1; }
export MTP2_ROMAN_REGULAR="$TEXT_REG"
export MTP2_ROMAN_BOLD="$TEXT_BOLD"
echo "[stage] validate selectable upright Roman donors"
"$PYTHON" "$ROOT/tools/audit_roman_donor_contract.py" \
    --regular "$TEXT_REG" --bold "$TEXT_BOLD" --check-inputs-only

echo "[stage] extract local MTPro2 source policy/geometry"
SOURCE_POLICY_JSON="$GEN/source-policy.json"
"$PYTHON" "$ROOT/tools/source_policy.py" \
    --mtpro2-dir "$ROOT/mtpro2" --edition "$EDITION" --include-geometry \
    -o "$SOURCE_POLICY_JSON"
export MTP2_SOURCE_POLICY_JSON="$SOURCE_POLICY_JSON"

echo "[stage] audit original MTPro2 LaTeX source declarations"
"$PYTHON" "$ROOT/tools/audit_original_source_contract.py" --mtpro2-dir "$ROOT/mtpro2" --edition "$EDITION"

# Build the unified CFF font from MTPro2 and the selected donors.
fontforge -lang=py -script "$ROOT/tools/build.py" --no-ttf "$@"

# Compare serialized fonts against local source values.
echo "[stage] validate OTF"
"$PYTHON" "$ROOT/tools/validate.py" "$OUT/$FONTBASE.otf"
echo "[stage] audit Windows-compatible font metadata"
"$PYTHON" "$ROOT/tools/audit_font_metadata.py" "$OUT/$FONTBASE.otf"
echo "[stage] audit edition-specific install identity"
"$PYTHON" "$ROOT/tools/audit_edition_naming.py" "$OUT/$FONTBASE.otf" --edition "$EDITION"
echo "[stage] audit Greek Latin-shaped aliases"
"$PYTHON" "$ROOT/tools/audit_greek_alias_contract.py" "$OUT/$FONTBASE.otf"
echo "[stage] audit source-wide MTPro2 metric / TopAccent / ordinary-spacing contract"
"$PYTHON" "$ROOT/tools/audit_source_contract.py" "$OUT/$FONTBASE.otf" --contract "$GEN/mtpro2-source-contract.json" --tfm-dir "$ROOT/mtpro2" --edition "$EDITION"
if [ "$EDITION" = full ]; then
    echo "[stage] audit cv03..cv07 original optical-size reachability"
    "$PYTHON" "$ROOT/tools/audit_bb_option_ssty.py" "$OUT/$FONTBASE.otf" --contract "$GEN/mtpro2-source-contract.json"
else
    echo "[stage] cv03..cv07 optical option-family audit: not applicable to MTPro2 Lite"
    echo "[stage] audit MTPro2 Lite semantic/capability contract"
    "$PYTHON" "$ROOT/tools/audit_lite_semantic_contract.py" "$OUT/$FONTBASE.otf"
fi
echo "[stage] audit selectable Roman donor contract"
"$PYTHON" "$ROOT/tools/audit_roman_donor_contract.py" "$OUT/$FONTBASE.otf" --regular "$TEXT_REG" --bold "$TEXT_BOLD" --sty "$ROOT/mtpro2/mtpro2.sty"
echo "[stage] convert OTF -> TTF"
"$PYTHON" "$ROOT/tools/otf2ttf.py" "$OUT/$FONTBASE.otf" "$OUT/$FONTBASE.ttf"
echo "[stage] validate TTF"
"$PYTHON" "$ROOT/tools/validate.py" "$OUT/$FONTBASE.ttf"
echo "[stage] audit Windows-compatible font metadata (TTF)"
"$PYTHON" "$ROOT/tools/audit_font_metadata.py" "$OUT/$FONTBASE.ttf"
echo "[stage] audit edition-specific install identity (TTF)"
"$PYTHON" "$ROOT/tools/audit_edition_naming.py" "$OUT/$FONTBASE.ttf" --edition "$EDITION"
echo "[stage] audit Greek Latin-shaped aliases (TTF)"
"$PYTHON" "$ROOT/tools/audit_greek_alias_contract.py" "$OUT/$FONTBASE.ttf"
if [ "$EDITION" = lite ]; then
    echo "[stage] audit MTPro2 Lite semantic/capability contract (TTF)"
    "$PYTHON" "$ROOT/tools/audit_lite_semantic_contract.py" "$OUT/$FONTBASE.ttf"
fi
echo "[stage] verify OTF/TTF invariants"
"$PYTHON" "$ROOT/tools/verify_otf_ttf.py" "$OUT/$FONTBASE.otf" "$OUT/$FONTBASE.ttf"
echo "[stage] audit source-wide MTPro2 contract (TTF; canonical names resolved by OTF GID)"
"$PYTHON" "$ROOT/tools/audit_source_contract.py" "$OUT/$FONTBASE.ttf" --reference-font "$OUT/$FONTBASE.otf" --contract "$GEN/mtpro2-source-contract.json" --tfm-dir "$ROOT/mtpro2" --edition "$EDITION"
echo "[stage] verify locally computed MATH values (OTF/TTF)"
"$PYTHON" "$ROOT/tools/audit_math_values.py" "$OUT/$FONTBASE.otf" --values "$GEN/math-constants.json"
"$PYTHON" "$ROOT/tools/audit_math_values.py" "$OUT/$FONTBASE.ttf" --values "$GEN/math-constants.json"

# Archive only after all checks pass; preserve the other edition.
[ -f "$OUT/$FONTBASE.otf" ] && [ -f "$OUT/$FONTBASE.ttf" ] || {
    echo "error: current build did not produce $FONTBASE.otf/.ttf in transient out/" >&2
    find "$OUT" -maxdepth 1 -type f -printf '%f\n' >&2 2>/dev/null || true
    exit 1
}
rm -rf "$EDOUT"
mkdir -p "$EDOUT"
mv "$OUT/$FONTBASE.otf" "$EDOUT/$FONTBASE.otf"
mv "$OUT/$FONTBASE.ttf" "$EDOUT/$FONTBASE.ttf"

echo "[stage] write local build evidence"
"$PYTHON" "$ROOT/tools/write_local_evidence.py" \
    --edition "$EDITION" \
    --source-policy "$SOURCE_POLICY_JSON" \
    --source-contract "$GEN/mtpro2-source-contract.json" \
    --math-values "$GEN/math-constants.json" \
    --otf "$EDOUT/$FONTBASE.otf" --ttf "$EDOUT/$FONTBASE.ttf" \
    --mtpro2-dir "$ROOT/mtpro2" \
    --regular-donor "$TEXT_REG" --bold-donor "$TEXT_BOLD" \
    --output-dir "$EDOUT"

echo "generated: $EDOUT/$FONTBASE.otf"
echo "generated: $EDOUT/$FONTBASE.ttf"
echo "local evidence: $EDOUT/LOCAL-BUILD-MEMO.txt"
