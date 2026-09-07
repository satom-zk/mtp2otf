"""Installation identities shared by the build and metadata checks."""

EDITIONS = {
    'full': ('MTPro2 Math', 'MTPro2Math'),
    'lite': ('MTPro2 Math Lite', 'MTPro2MathLite'),
}
FONT_REVISION = 1.0
FONT_VERSION = 'Version 1.0'


def identity(edition):
    if edition not in EDITIONS:
        raise ValueError(f'unknown edition: {edition}')
    family, basename = EDITIONS[edition]
    return family, basename, 'MTP2;' + basename
