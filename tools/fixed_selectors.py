"""Source-profile fixed designs: provenance order and isolated cv13-19
clones.

Only source identities and structural rules live here. Outlines and
numeric metrics are read from the current build, never from a diagnostic
font.
"""
import copy

from fontTools.ttLib.tables import otTables as ot
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen

from finalize import update_average_width

SPECS = (
    ('cv13', 9182, (('exe', 176, 192), ('exf', 160, 171), ('exg', 160, 165))),
    ('cv14', 9183, (('exe', 144, 160), ('exf', 144, 155), ('exg', 144, 149))),
    (
        'cv15', 9180,
        (
            ('exa', 190, 194), ('exe', 208, 214), ('exf', 177, 183),
            ('exg', 177, 183), ('exa', 195, 195)
        )
    )
)
EXTRA = (
    ('cv16', 40, (('exg', 0),)), ('cv16', 41, (('exg', 1),)),
    ('cv16', 123, (('exf', 8), ('exg', 8))),
    ('cv16', 125, (('exf', 9), ('exg', 9))), ('cv16', 10216, (('exg', 10),)),
    ('cv16', 10217, (('exg', 11),)), ('cv16', 92, (('exg', 15),)),
    ('cv17', 8730, (('exf', 112), ('exg', 112))),
    ('cv18', 770, (('exe', 57), ('exf', 59))), ('cv18', 771, (('exa', 103),)),
    ('cv18', 780, (('exe', 89), ('exf', 91))),
    ('cv19', 123, (('exa', 182), ('exa', 184), ('exa', 186), ('exa', 188))),
    ('cv19', 125, (('exa', 183), ('exa', 185), ('exa', 187), ('exa', 189)))
)
TAGS = tuple(dict.fromkeys([x[0] for x in SPECS + EXTRA] + ['cv20', 'cv21']))
SCRIPT_FIXED_INPUTS = {
    'cv16': (40, 41, 123, 125, 10216, 10217, 92), 'cv17': (8730,),
    'cv19': (123, 125)
}


def add_script_fixed_inputs(font, tag, alternates):
    """Add S/SS inputs atomically, using actual ssty rather than glyph
    names.
    
    This component is also usable on a copy with existing T fixed
    selectors; it neither installs clones nor changes any font table by
    itself.
    """
    if tag not in SCRIPT_FIXED_INPUTS:
        raise ValueError('unsupported script fixed feature ' + tag)
    if 'GSUB' not in font:
        raise ValueError('missing GSUB for script fixed inputs')
    g = font['GSUB'].table
    features = [
        r for r in g.FeatureList.FeatureRecord if r.FeatureTag == 'ssty'
    ]
    if len(features) != 1:
        raise ValueError('ssty must have one feature record')
    feature = features[0].Feature
    indices = feature.LookupListIndex
    if feature.LookupCount != 1 or len(indices) != 1:
        raise ValueError('ssty must reference one lookup')
    index = indices[0]
    if not 0 <= index < len(g.LookupList.Lookup):
        raise ValueError('ssty lookup index out of range')
    lookup = g.LookupList.Lookup[index]
    if (
        lookup.LookupType != 3
        or lookup.LookupFlag != 0
        or lookup.SubTableCount != 1
        or (len(lookup.SubTable) != 1)
        or (not hasattr(lookup.SubTable[0], 'alternates'))
    ):
        raise ValueError('ssty must be one unflagged AlternateSubst subtable')
    cmap = font.getBestCmap()
    glyphs = set(font.getGlyphOrder())
    pending = {}
    rows = []
    for cp in SCRIPT_FIXED_INPUTS[tag]:
        owner = cmap.get(cp)
        forms = alternates.get(owner)
        if (
            owner not in glyphs
            or not forms
            or any((n not in glyphs for n in forms))
        ):
            raise ValueError(
                f'{tag} U+{cp:04X}: missing T owner or fixed candidates'
            )
        styled = lookup.SubTable[0].alternates.get(owner)
        if (
            not styled
            or len(styled) != 2
            or len(set([owner] + list(styled))) != 3
            or any((n not in glyphs for n in styled))
        ):
            raise ValueError(
                f'{tag} U+{cp:04X}: ssty must select distinct S and SS glyphs'
            )
        for level, key in enumerate(styled, 1):
            if key in alternates or key in pending:
                raise ValueError(
                    f'{tag} U+{cp:04X}: existing or colliding S/SS input '
                    f'{key}'
                )
            pending[key] = list(forms)
            rows.append(
                {
                    'feature': tag, 'unicode': cp, 'style': level,
                    'ssty_lookup_index': index,
                    'T_owner_gid': font.getGlyphID(owner),
                    'styled_owner_gid': font.getGlyphID(key),
                    'target_gids': [font.getGlyphID(n) for n in forms]
                }
            )
    if len(pending) != 2 * len(SCRIPT_FIXED_INPUTS[tag]):
        raise ValueError(tag + ': script fixed input count differs')
    alternates.update(pending)
    return rows


def records():
    old = [
        (tag, cp, family, slot) for tag, cp, families in SPECS
        for family, start, end in families for slot in range(start, end + 1)
    ]
    return old + [
        (tag, cp, family, slot) for tag, cp, forms in EXTRA
        for family, slot in forms
    ]


def copy_math_attributes(font, source, clone):
    gi = font['MATH'].table.MathGlyphInfo
    state = {}
    for attr, covfield, valuesfield, countfield in (
        (
            'MathItalicsCorrectionInfo', 'Coverage', 'ItalicsCorrection',
            'ItalicsCorrectionCount'
        ),
        (
            'MathTopAccentAttachment', 'TopAccentCoverage',
            'TopAccentAttachment', 'TopAccentAttachmentCount'
        ),
        (
            'MathKernInfo', 'MathKernCoverage', 'MathKernInfoRecords',
            'MathKernCount'
        )
    ):
        table = getattr(gi, attr, None)
        cov = getattr(table, covfield, None) if table else None
        present = bool(cov and source in cov.glyphs)
        state[attr] = present
        if present:
            old = getattr(table, valuesfield)[cov.glyphs.index(source)]
            cov.glyphs.append(clone)
            getattr(table, valuesfield).append(copy.deepcopy(old))
            setattr(table, countfield, len(cov.glyphs))
    ext = gi.ExtendedShapeCoverage
    present = bool(ext and source in ext.glyphs)
    state['ExtendedShapeCoverage'] = present
    if present:
        ext.glyphs.append(clone)
    gdef = font['GDEF'].table
    for attr in ('GlyphClassDef', 'MarkAttachClassDef'):
        table = getattr(gdef, attr, None)
        classes = table.classDefs if table else {}
        state['GDEF.' + attr] = classes.get(source)
        if source in classes:
            classes[clone] = classes[source]
    for attr, covfield, valfield, countfield in (
        ('AttachList', 'Coverage', 'AttachPoint', 'GlyphCount'),
        ('LigCaretList', 'Coverage', 'LigGlyph', 'LigGlyphCount')
    ):
        table = getattr(gdef, attr, None)
        cov = getattr(table, covfield, None) if table else None
        present = bool(cov and source in cov.glyphs)
        state['GDEF.' + attr] = present
        if present:
            value = getattr(table, valfield)[cov.glyphs.index(source)]
            cov.glyphs.append(clone)
            getattr(table, valfield).append(copy.deepcopy(value))
            setattr(table, countfield, len(cov.glyphs))
    return state


def bounds(font, name):
    gs = font.getGlyphSet()
    pen = BoundsPen(gs)
    gs[name].draw(pen)
    if pen.bounds is None:
        raise ValueError('empty fixed source outline ' + name)
    return pen.bounds


def translated_charstring(font, name, dy):
    """Draw CFF source at (0,dy), retaining its original horizontal
    advance.
    """
    cs = font['CFF '].cff.topDictIndex[0].CharStrings[name]
    gs = font.getGlyphSet()
    pen = T2CharStringPen(font['hmtx'][name][0] - cs.private.nominalWidthX, gs)
    gs[name].draw(TransformPen(pen, (1, 0, 0, 1, 0, dy)))
    return pen.getCharString(
        private=cs.private, globalSubrs=cs.globalSubrs, optimize=True
    )


def install(font, inventory):
    if 'CFF ' not in font:
        raise ValueError('install fixed selectors before TrueType conversion')
    imports = {(r['tag'], r['slot']): r['glyph'] for r in inventory['imports']}
    original = list(font.getGlyphOrder())
    m = font['MATH'].table.MathVariants
    cons = dict(zip(m.HorizGlyphCoverage.glyphs, m.HorizGlyphConstruction))
    gsub = font['GSUB'].table
    old_features = list(gsub.FeatureList.FeatureRecord)
    if any(
        (r.FeatureTag in TAGS + ('cv97', 'cv98', 'cv99') for r in old_features)
    ):
        raise ValueError('fixed selector tags already present')
    root_changes = []
    for cp, tag, slot in ((9182, 'exe', 176), (9183, 'exe', 144)):
        source = imports.get((tag, slot))
        ordinary = f'uni{cp:04X}'
        if (
            not source
            or source != font.getBestCmap().get(cp)
            or ordinary not in cons
        ):
            raise ValueError(
                f'brace root/source mismatch U+{cp:04X} {tag}:{slot}'
            )
        if (
            cons[source].VariantCount != 35
            or cons[ordinary].VariantCount != 35
        ):
            raise ValueError('source fixed brace series changed')
        if (
            not cons[ordinary].GlyphAssembly
            or len(cons[ordinary].GlyphAssembly.PartRecords) != 5
        ):
            raise ValueError('legacy ordinary brace assembly missing')
        cons[ordinary].MathGlyphVariantRecord = []
        cons[ordinary].VariantCount = 0
        for table in font['cmap'].tables:
            if table.isUnicode() and cp in table.cmap:
                table.cmap[cp] = ordinary
        pair = font['GPOS'].table.LookupList.Lookup[2].SubTable[0]
        if hasattr(pair, 'ExtSubTable'):
            pair = pair.ExtSubTable
        classes = pair.ClassDef2.classDefs
        if source not in classes or ordinary in classes:
            raise ValueError('R4 ordinary-right class changed')
        classes[ordinary] = classes[source]
        root_changes.append(
            {
                'unicode': f'U+{cp:04X}', 'ordinary_root': ordinary,
                'retained_source_root': source, 'ordinary_variant_count': 0,
                'assembly_parts': 5, 'GPOS_ClassDef2': classes[ordinary]
            }
        )
    top = font['CFF '].cff.topDictIndex[0]
    cs = top.CharStrings
    mapping = []
    targets = {tag: {} for tag in TAGS}
    translations = []
    terminals = []
    axis = font['MATH'].table.MathConstants.AxisHeight.Value
    for tag, cp, family, slot in records():
        source = imports.get((family, slot))
        sid = f'{family}:{slot}:{tag}'
        if source not in original:
            raise ValueError('missing fixed source ' + sid)
        clone = source + '.fixed'
        if clone in font.getGlyphOrder() or clone in cs.charStrings:
            raise ValueError('duplicate fixed source ' + sid)
        raw_bbox = bounds(font, source) if tag in ('cv17', 'cv19') else None
        if tag == 'cv19':
            if (
                font['MATH'].table.MathGlyphInfo.MathKernInfo
                and source in (
                    font['MATH'].table.MathGlyphInfo.MathKernInfo
                    .MathKernCoverage.glyphs
                    if font['MATH'].table.MathGlyphInfo.MathKernInfo
                    .MathKernCoverage else []
                )
            ):
                raise ValueError(
                    'cv19 has vertical-position-dependent MathKernInfo: ' + sid
                )
            dy = axis - (raw_bbox[1] + raw_bbox[3]) / 2
            outline = translated_charstring(font, source, dy)
            translations.append(
                {
                    'source_id': sid, 'source_glyph': source,
                    'clone_glyph': clone, 'axis_height': axis,
                    'translation_y': dy, 'source_bbox': list(raw_bbox),
                    'clone_bbox': [
                        raw_bbox[0], raw_bbox[1] + dy, raw_bbox[2],
                        raw_bbox[3] + dy
                    ],
                    'hmtx': list(font['hmtx'][source])
                }
            )
        else:
            outline = copy.deepcopy(cs[source])
        cs.charStrings[clone] = len(cs.charStringsIndex)
        cs.charStringsIndex.items.append(outline)
        top.charset.append(clone)
        font['hmtx'].metrics[clone] = font['hmtx'][source]
        attributes = copy_math_attributes(font, source, clone)
        targets[tag].setdefault(cp, []).append(clone)
        mapping.append(
            {
                'source_id': sid, 'feature': tag, 'unicode': f'U+{cp:04X}',
                'source_tag': family, 'source_slot': slot,
                'source_glyph': source, 'clone_glyph': clone,
                'opentype_value': len(targets[tag][cp]),
                'display_stage': len(targets[tag][cp]),
                'fontspec_alternate': len(targets[tag][cp]) - 1,
                'attributes': attributes, 'source_gid': original.index(source),
                'clone_gid': len(original) + len(mapping)
            }
        )
    # Only cv17 gets an isolated vertical construction. Its leaf must
    # not re-use the raw source: that source is in
    # U+221A's ordinary next chain.
    for r in mapping:
        if r['feature'] != 'cv17':
            continue
        clone = r['clone_glyph']
        leaf = clone + '.terminal'
        if leaf in cs.charStrings:
            raise ValueError('duplicate terminal leaf ' + leaf)
        source = r['source_glyph']
        raw_bbox = bounds(font, source)
        cs.charStrings[leaf] = len(cs.charStringsIndex)
        cs.charStringsIndex.items.append(copy.deepcopy(cs[clone]))
        top.charset.append(leaf)
        font['hmtx'].metrics[leaf] = font['hmtx'][clone]
        attributes = copy_math_attributes(font, clone, leaf)
        advance = round(raw_bbox[3] - raw_bbox[1]) + 1
        if (
            clone in m.VertGlyphCoverage.glyphs
            or source not in (
                v.VariantGlyph for c in m.VertGlyphConstruction
                for v in c.MathGlyphVariantRecord
            )
        ):
            raise ValueError(
                'cv17 ordinary source chain/clone changed ' + r['source_id']
            )
        con = ot.MathGlyphConstruction()
        con.GlyphAssembly = None
        vr = ot.MathGlyphVariantRecord()
        vr.VariantGlyph = leaf
        vr.AdvanceMeasurement = advance
        con.MathGlyphVariantRecord = [vr]
        con.VariantCount = 1
        m.VertGlyphCoverage.glyphs.append(clone)
        m.VertGlyphConstruction.append(con)
        m.VertGlyphCount = len(m.VertGlyphCoverage.glyphs)
        terminals.append(
            {
                'source_id': r['source_id'], 'clone_glyph': clone,
                'leaf_glyph': leaf, 'clone_gid': r['clone_gid'],
                'leaf_gid': len(original) + len(mapping) + len(terminals),
                'advance_measurement': advance, 'source_bbox': list(raw_bbox),
                'hmtx': list(font['hmtx'][clone]), 'attributes': attributes
            }
        )
    font.setGlyphOrder(
        original + [r['clone_glyph'] for r in mapping]
        + [r['leaf_glyph'] for r in terminals]
    )
    font['maxp'].numGlyphs = len(font.getGlyphOrder())
    font['hhea'].numberOfHMetrics = len(font.getGlyphOrder())
    # cv20 roots are stretchable constructions, never fixed clones.
    for cp in (9182, 9183):
        root = f"brace.plain.{('over' if cp == 9182 else 'under')}"
        if root not in m.HorizGlyphCoverage.glyphs:
            raise ValueError('missing cv20 horizontal construction ' + root)
        targets['cv20'][cp] = [root]
    automatic = []
    for cp, slot, expected in (
        (9182, 176, 'uni23DE.curly.exe176'),
        (9183, 144, 'uni23DF.curly.exe144')
    ):
        root = imports.get(('exe', slot))
        con = cons.get(root)
        if (
            root != expected
            or font.getBestCmap().get(cp) != f'uni{cp:04X}'
            or (not con)
            or (con.VariantCount != 35)
            or (len(con.MathGlyphVariantRecord) != 35)
            or (not con.GlyphAssembly)
            or (len(con.GlyphAssembly.PartRecords) != 5)
            or (
                [con.MathGlyphVariantRecord[i].AdvanceMeasurement
                 for i in (0, -1)] != [1201, 29601]
            )
        ):
            raise ValueError(f'cv21 source construction mismatch U+{cp:04X}')
        targets['cv21'][cp] = [root]
        automatic.append(
            {
                'feature': 'cv21', 'unicode': f'U+{cp:04X}',
                'source_tag': 'exe', 'source_slot': slot, 'source_glyph': root,
                'opentype_value': 1, 'fontspec_alternate': 0,
                'source_gid': original.index(root), 'variant_count': 35,
                'assembly_parts': 5
            }
        )
    for tag, by_cp in targets.items():
        sub = ot.AlternateSubst()
        sub.alternates = {
            font.getBestCmap()[cp]: forms for cp, forms in by_cp.items()
        }
        if tag in SCRIPT_FIXED_INPUTS:
            add_script_fixed_inputs(font, tag, sub.alternates)
        if tag == 'cv18':
            # The existing ssty lookup precedes these selector lookups.
            # Its script accent glyphs still represent the same Unicode
            # inputs; route them to the same immutable fixed designs,
            # without moving any historical lookup or modifying the
            # original ssty behavior.
            for cp, forms in by_cp.items():
                root = font.getBestCmap()[cp]
                for level in (1, 2):
                    styled = f'{root}.ssty{level}'
                    if styled not in original:
                        raise ValueError('missing script accent ' + styled)
                    sub.alternates[styled] = forms
        lookup = ot.Lookup()
        lookup.LookupType = 3
        lookup.LookupFlag = 0
        lookup.SubTable = [sub]
        lookup.SubTableCount = 1
        gsub.LookupList.Lookup.append(lookup)
        rec = ot.FeatureRecord()
        rec.FeatureTag = tag
        rec.Feature = ot.Feature()
        rec.Feature.FeatureParams = None
        rec.Feature.LookupListIndex = [len(gsub.LookupList.Lookup) - 1]
        rec.Feature.LookupCount = 1
        gsub.FeatureList.FeatureRecord.append(rec)
    gsub.LookupList.LookupCount = len(gsub.LookupList.Lookup)
    previous = list(gsub.FeatureList.FeatureRecord)
    gsub.FeatureList.FeatureRecord.sort(key=lambda r: r.FeatureTag)
    gsub.FeatureList.FeatureCount = len(previous)
    remap = {
        i: gsub.FeatureList.FeatureRecord.index(r)
        for i, r in enumerate(previous)
    }
    for script in gsub.ScriptList.ScriptRecord:
        for ls in [script.Script.DefaultLangSys] + [
            r.LangSys for r in script.Script.LangSysRecord
        ]:
            if ls is None:
                continue
            ls.FeatureIndex = sorted(
                [remap[i] for i in ls.FeatureIndex] + [
                    remap[i] for i in range(len(old_features), len(previous))
                ]
            )
            ls.FeatureCount = len(ls.FeatureIndex)
            if ls.ReqFeatureIndex != 65535:
                ls.ReqFeatureIndex = remap[ls.ReqFeatureIndex]
    return {
        'profile': 'source', 'edition': inventory['edition'],
        'input_hashes': inventory['input_hashes'],
        'original_glyph_count': len(original), 'clone_count': len(mapping),
        'terminal_leaf_count': len(terminals),
        'glyph_count': len(font.getGlyphOrder()),
        'cv19_translations': translations, 'cv17_terminals': terminals,
        'ordinary_brace_changes': root_changes,
        'automatic_selectors': automatic, 'mapping': mapping
    }


def edit(font, inventory):
    """Install selectors and update the average in the caller-owned font."""
    result = install(font, inventory)
    update_average_width(font)
    return result
