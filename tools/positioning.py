"""Serialize original TFM kerns, excluding family skewchar-right pairs.
"""


def install_source_kerns(sources):
    out, fonts, imported = sources.font, sources.faces, sources.imported
    SOURCE_SKEW = dict(sources.rules.skewchar_by_tag)
    # Serialize TFM pair kern without an added italic-correction term.
    out.addLookup(
        'kernL',
        'gpos_pair',
        (),
        (
            (
                'kern',
                (
                    ('DFLT', ('dflt',)),
                    ('latn', ('dflt',)),
                    ('math', ('dflt',)),
                ),
            ),
        ),
    )
    out.addLookupSubtable('kernL', 'kern-1')
    _source_tfm_pairs = {}

    def _remember_source_tfm_pair(gl, gr, xadvance):
        key = (gl, gr)
        previous = _source_tfm_pairs.get(key)
        if previous is not None:
            if previous != xadvance:
                raise RuntimeError(
                    'conflicting source TFM kern %s/%s: %+d vs %+d'
                    % (gl, gr, previous, xadvance)
                )
            return
        _source_tfm_pairs[key] = xadvance
        out[gl].addPosSub('kern-1', gr, 0, 0, xadvance, 0, 0, 0, 0, 0)

    for _tag in tuple(SOURCE_SKEW):
        if _tag not in fonts:
            continue
        _tfm = fonts[_tag][1]
        _sk = SOURCE_SKEW[_tag]
        for (_l, _r), _v in sorted(_tfm.kerns.items()):
            if _sk is not None and _r == _sk:
                continue
            _gl = imported.get((_tag, _l))
            _gr = imported.get((_tag, _r))
            if not _gl or not _gr or _gl not in out or _gr not in out:
                continue
            _k = round((_v or 0.0) * 1000)
            if not _k:
                continue
            _remember_source_tfm_pair(_gl, _gr, int(_k))
