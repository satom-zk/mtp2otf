"""Read Type1 dictionaries and acquire native handles without copies."""

from contextlib import contextmanager, ExitStack
import sys


def _close(handle):
    active_error = sys.exc_info()[0] is not None
    try:
        handle.close()
    except Exception:
        if not active_error:
            raise


@contextmanager
def native_font(path=None):
    """The caller owns this handle through its last
    copy/reference/generate.
    """
    import fontforge

    handle = fontforge.font() if path is None else fontforge.open(str(path))
    try:
        yield handle
    finally:
        _close(handle)


def read_type1(path):
    from fontTools.t1Lib import T1Font

    font = T1Font(str(path))
    font.parse()
    if not isinstance(font['Encoding'], list):
        raise ValueError(str(path) + ': no usable Type1 Encoding')
    return font


def slot_names(font):
    names = font['CharStrings']
    return {
        slot: name
        for slot, name in enumerate(font['Encoding'])
        if name != '.notdef' and name in names
    }


def slot_path(font, pfb_path, slot):
    from fontTools.pens.recordingPen import RecordingPen
    from fontTools.pens.boundsPen import BoundsPen

    names = slot_names(font)
    if slot not in names:
        raise ValueError(
            f'{pfb_path.name}: Encoding/CharStrings slot {slot} missing'
        )
    name = names[slot]
    glyphs = font.getGlyphSet()
    rec = RecordingPen()
    glyphs[name].draw(rec)
    bounds = BoundsPen(glyphs)
    glyphs[name].draw(bounds)
    return dict(
        source_file=pfb_path.name,
        slot=slot,
        glyph_name=name,
        bounds=list(bounds.bounds or (0, 0, 0, 0)),
        path=[
            dict(op=op, points=[[float(x), float(y)] for x, y in pts])
            for op, pts in rec.value
        ],
    )


@contextmanager
def source_faces(source_dir, edition, snapshot):
    """Use catalog metrics; only the native backend opens FontForge
    PFBs.
    """
    from declarations import active_tags
    from metrics import from_data

    faces = {}
    with ExitStack() as owners:
        for tag in active_tags(edition):
            entry = snapshot['catalog'][tag]
            path = source_dir / (entry['stem'] + '.pfb')
            try:
                pfb = owners.enter_context(native_font(path))
                slots = {
                    g.encoding: g.glyphname
                    for g in pfb.glyphs()
                    if g.encoding < 0x10000
                }
                tfm = from_data(entry['metrics'])
                for slot in snapshot['plan']['native'].get(tag, []):
                    if slot not in slots or slot not in tfm.chars:
                        raise ValueError(f'required native slot {slot} absent')
                faces[tag] = pfb, tfm, slots
            except Exception as exc:
                raise ValueError(
                    f'native source {path.name} role={tag}: {exc}'
                ) from exc
        yield faces
