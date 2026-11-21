"""GSUB and GPOS tables."""

from fontTools.otlLib.builder import (
    buildAlternateSubstSubtable,
    buildLigatureSubstSubtable,
    buildLookup,
    buildPairPosGlyphs,
    buildSingleSubstSubtable,
    buildValue,
)
from fontTools.ttLib import newTable
from fontTools.ttLib.tables import otTables

SCRIPTS = ("DFLT", "latn", "math")
WINDOWS_ENGLISH = ((3, 1, 0x409),)


def build_gsub(plan, font_name, names):
    """One lookup per feature, in the order of application."""
    lookups, features = [], []
    for index, feature in enumerate(plan.features):
        lookups.append(buildLookup([_subtable(feature, font_name)]))
        features.append(
            (feature.tag, [index], _parameters(feature, names)))
    return _table("GSUB", lookups, features)


def build_gpos(plan, font_name, glyph_ids):
    pairs = {
        (font_name[left], font_name[right]):
            (buildValue({"XAdvance": value}), None)
        for (left, right), value in plan.kerns.items()}
    lookup = buildLookup(buildPairPosGlyphs(pairs, glyph_ids))
    return _table("GPOS", [lookup], [("kern", [0], None)])


def _subtable(feature, font_name):
    if feature.kind == "single":
        return buildSingleSubstSubtable({
            font_name[glyph]: font_name[target]
            for glyph, target in feature.mapping.items()})
    if feature.kind == "alternate":
        return buildAlternateSubstSubtable({
            font_name[glyph]: [font_name[target] for target in targets]
            for glyph, targets in feature.mapping.items()})
    return buildLigatureSubstSubtable({
        tuple(font_name[glyph] for glyph in glyphs): font_name[target]
        for glyphs, target in feature.mapping.items()})


def _parameters(feature, names):
    """User-interface names of a cv or ss feature."""
    if not feature.name:
        return None

    def add(text):
        return names.addName(text, platforms=WINDOWS_ENGLISH)

    if feature.tag.startswith("ss"):
        parameters = otTables.FeatureParamsStylisticSet()
        parameters.Version = 0
        parameters.UINameID = add(feature.name)
        return parameters
    parameters = otTables.FeatureParamsCharacterVariants()
    parameters.Format = 0
    parameters.FeatUILabelNameID = add(feature.name)
    parameters.FeatUITooltipTextNameID = add(feature.description)
    parameters.SampleTextNameID = add(
        "".join(chr(c) for c in feature.characters))
    options = [add(option) for option in feature.options]
    parameters.NumNamedParameters = len(options)
    parameters.FirstParamUILabelNameID = options[0] if options else 0
    parameters.CharCount = len(feature.characters)
    parameters.Character = list(feature.characters)
    return parameters


def _table(tag, lookups, features):
    """Every feature is registered for the default language of SCRIPTS."""
    features = sorted(features, key=lambda feature: feature[0])
    table = getattr(otTables, tag)()
    table.Version = 0x00010000
    table.LookupList = otTables.LookupList()
    table.LookupList.Lookup = lookups
    table.FeatureList = otTables.FeatureList()
    table.FeatureList.FeatureRecord = []
    for feature, indices, parameters in features:
        record = otTables.FeatureRecord()
        record.FeatureTag = feature
        record.Feature = otTables.Feature()
        record.Feature.FeatureParams = parameters
        record.Feature.LookupListIndex = indices
        table.FeatureList.FeatureRecord.append(record)
    table.ScriptList = otTables.ScriptList()
    table.ScriptList.ScriptRecord = []
    for script in SCRIPTS:
        record = otTables.ScriptRecord()
        record.ScriptTag = script
        record.Script = otTables.Script()
        record.Script.LangSysRecord = []
        record.Script.DefaultLangSys = language = otTables.DefaultLangSys()
        language.ReqFeatureIndex = 0xFFFF
        language.LookupOrder = None
        language.FeatureIndex = list(range(len(features)))
        table.ScriptList.ScriptRecord.append(record)
    result = newTable(tag)
    result.table = table
    return result
