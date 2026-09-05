mtp2otf
=======
Convert your licensed MathTime Professional 2 (MTPro2) installation into
OpenType MATH fonts for local use. Full and Lite have separate font names.

Requirements and inputs
-----------------------
Install Python with fontTools, FontForge with Python support, and TeX Live
with tftopl. Copy your MTPro2 PFB/TFM files and mtpro2.sty into mtpro2/.
Full also requires umt2ms.fd, umt2mf.fd, umt2bb.fd, and umt2hrb.fd there.
The build checks the selected edition's required sources and stops on errors.

Place the default donors from Artifex urw-base35-fonts in times/:
  NimbusRoman-Regular.otf
  NimbusRoman-Bold.otf

Build
-----
From this directory:
  sh build.sh                  # Full
  sh build.sh --edition=lite   # Lite

Each build validates the selected edition's fonts automatically.

Outputs are out/full/MTPro2Math.otf and .ttf, and
out/lite/MTPro2MathLite.otf and .ttf. LOCAL-* files beside them record local
inputs, computed values, and checks.

To select another Roman donor pair at build time:
  sh build.sh --roman-regular=/path/to/Regular.otf \
              --roman-bold=/path/to/Bold.otf
Both donors must be static, upright, proportional fonts from the same family
with the required Latin/digit coverage. CFF OTF and TrueType TTF are accepted;
coordinates and advances are normalized. Extra character coverage varies by
donor. MTP2_ROMAN_REGULAR and MTP2_ROMAN_BOLD provide environment defaults;
command-line paths take precedence.

Use
---
Word: install the TTF and select MTPro2 Math or MTPro2 Math Lite as the math
font. Close Word before replacing an installed font.
LuaLaTeX / XeLaTeX: use unicode-math and select the generated OTF, for example:
  \usepackage{unicode-math}
  \setmathfont{MTPro2Math.otf}
No project-specific package or Lua callback is required.

The doc/ directory contains matching Word and LuaLaTeX specimens, with their
editable sources and PDFs. They use Full with the default Nimbus donors;
Word uses the TTF, and LuaLaTeX uses the OTF. Run lualatex lualatex.tex from doc/.
Rebuilding the LuaLaTeX specimen requires amsmath, fontspec, unicode-math,
and all four Nimbus Roman styles to be discoverable by TeX.

Design and limitations
----------------------
MTPro2 sources determine math metrics and identities. Upright Latin and
mathematical bold Latin/digits use the selected Regular/Bold donors.
Mathematical italic/bold italic and non-Latin-shaped Greek use MTPro2.
Lite does not fill missing Full-only symbols from a donor.

Untransformed MTPro2 glyph advances preserve CHARWD. Source math alphabets
use TopAccent = (WD + IC)/2 + the family skew kern. Combining accents, prime
compatibility forms, and synthesized glyphs have explicit conversion rules.
Ordinary IC and TFM kerning are encoded in GPOS; application depends on the
math engine. Upper-limit placement preserves the Word
compatibility policy, rather than a direct TeX-parameter correspondence.
OTF/TTF checks include layout and outline-origin preservation.

Public vec/bar accents are fixed. Standard \overrightarrow and \wideoverbar
do not automatically use the private wide forms: U+E286 has finite variants;
U+E287 has an assembly. \overline draws a separate rule.
LuaHBTeX may not reproduce the full Type1 ordinary IC + pair-kern combination.
Swash z remains available through cv01/U+E000 where supported; no Word
\zswash registration or default swash is provided.

Mappings are project-authored interoperability metadata, developed with
machine assistance and human interpretation and verification, not mechanical
copies of MTPro2 files. Type 1 names alone were insufficient; TeX/Unicode
semantics, local-source behavior, and rendered results were compared.
Evaluated source metrics are computed locally, not included in public source.

Public input/artifact check:
  python3 tools/audit_public_source.py .

License
-------
Project-authored code and documentation use 0BSD (see LICENSE).
MTPro2, donor fonts, external tools, and generated fonts retain their
respective license terms.

MathTime is a trademark of Publish or Perish, Inc. This independent project
is not affiliated with or endorsed by Publish or Perish, Inc., Personal TeX,
Inc. (PCTeX), or Artifex Software.
