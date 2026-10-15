"""Installation identities shared by the build and metadata checks."""

EDITIONS = {
    'full': ('MTPro2 Math', 'MTPro2Math'),
    'lite': ('MTPro2 Math Lite', 'MTPro2MathLite'),
}
# head.fontRevision is a 16.16 fixed-point field.
FONT_REVISION = round(1.2 * 65536) / 65536
FONT_VERSION = 'Version 1.2'


def identity(edition):
    if edition not in EDITIONS:
        raise ValueError(f'unknown edition: {edition}')
    family, basename = EDITIONS[edition]
    return family, basename, 'MTP2;' + basename
