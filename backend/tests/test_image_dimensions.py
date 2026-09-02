"""Guards for true-pixel-dimension derivation (app/utils/image_dimensions.py).

The class of defect these exist to catch: a stored width that is LARGER than the
raster it describes. A `srcset` descriptor built from an overstated width tells
the browser a small image is big, the browser picks it for a slot it cannot
fill, and the user sees an upscale where they previously saw a sharp photo.
That is the regression that blocked the first attempt at this work, and it was
invisible to a fully green suite because every test there compared a rung to
the URL it came from and none compared a descriptor to the PIXELS it returns.

So these tests compare against pixels. The header fixtures are real bytes from
production photos, and the derivation tests assert the inequality directly
rather than asserting a particular arithmetic.
"""

import ast
import math
import pathlib

import pytest

from app.utils.image_dimensions import (
    delivered_dimensions,
    dimensions_from_header,
    tmdb_declared_width,
)

# Leading bytes of https://images.pexels.com/photos/10010407/... ?h=350 as
# actually served, in both formats the host content-negotiates. Truth measured
# independently with Pillow: 622x350.
REAL_AVIF_HEADER = bytes.fromhex(
    "0000001c6674797061766966000000006d696631617669666d696166000001156d65"
    "7461000000000000002168646c720000000000000000706963740000000000000000"
    "000000000000000034696c6f63000000004440000200010000000001390001000000"
    "000000774d0002000000007886000100000000000000820000003869696e66000000"
    "00000200000015696e66650200000000010000617630310000000015696e66650200"
    "00010002000045786966000000000e7069746d000000000001000000546970727000"
    "0000366970636f0000000c6176314381010c00000000146973706500000000000002"
    "6e0000015e00"
)
REAL_JPEG_HEADER = bytes.fromhex(
    "ffd8ffe100804578696600004d4d002a000000080005011200030000000100010000"
    "011a0005000000010000004a011b0005000000010000005201280003000000010002"
    "000087690004000000010000005a0000000000000048000000010000004800000001"
    "0002a0020004000000010000026ea0030004000000010000015e00000000ffdb0043"
    "0006040506050406060506070706080a100a0a09090a140e0f0c1017141818171416"
    "161a1d251f1a1b231c1616202c20232627292a29191f2d302d283025282928ffdb00"
    "43010707070a080a130a0a13281a161a282828282828282828282828282828282828"
    "2828282828282828282828282828282828282828282828282828282828282828ffc0"
    "001108015e026e03"
)
REAL_SIZE = (622, 350)


class TestHeaderParsing:
    """Exact dimensions out of the leading bytes, for the formats really served."""

    @pytest.mark.parametrize(
        "fixture", [REAL_AVIF_HEADER, REAL_JPEG_HEADER], ids=["avif", "jpeg"]
    )
    def test_reads_real_production_headers(self, fixture):
        assert dimensions_from_header(fixture) == REAL_SIZE

    @pytest.mark.parametrize(
        "fixture", [REAL_AVIF_HEADER, REAL_JPEG_HEADER], ids=["avif", "jpeg"]
    )
    def test_truncation_never_yields_a_wrong_answer(self, fixture):
        """The backfill reads a bounded prefix, so short input is the normal case.

        A truncated read may legitimately fail to find the size. It must never
        report a DIFFERENT size — a confidently wrong number would be written to
        the database and believed.
        """
        for cut in range(0, len(fixture)):
            got = dimensions_from_header(fixture[:cut])
            assert got in (None, REAL_SIZE), f"prefix of {cut} bytes gave {got}"

    def test_unknown_container_returns_none(self):
        assert dimensions_from_header(b"not an image at all, just some bytes") is None
        assert dimensions_from_header(b"") is None
        assert dimensions_from_header(None) is None

    def test_png_and_gif(self):
        png = (
            b"\x89PNG\r\n\x1a\n"
            + b"\x00\x00\x00\rIHDR"
            + (940).to_bytes(4, "big")
            + (627).to_bytes(4, "big")
        )
        assert dimensions_from_header(png) == (940, 627)
        # A real GIF continues past the size field with the rest of the logical
        # screen descriptor and at least one block, so the fixture does too.
        gif = (
            b"GIF89a"
            + (300).to_bytes(2, "little")
            + (200).to_bytes(2, "little")
            + b"\xf7\x00\x00"  # packed fields, background index, aspect ratio
            + b"\x00" * 8  # start of the global colour table
        )
        assert dimensions_from_header(gif) == (300, 200)


class TestDeliveredDimensions:
    """The imgix fit=clip derivation used at ingest, where a fetch is free."""

    def test_height_only_box_pins_height(self):
        # ?h=350 on a 3:2 source: height is exact, width follows the aspect.
        w, h = delivered_dimensions("https://x/p.jpg?h=350", 6000, 4000)
        assert h == 350
        assert w == 525

    def test_width_binds_when_source_is_wider_than_the_box(self):
        # A = 1.5 >= 940/650, so width hits the box and height follows.
        assert delivered_dimensions("https://x/p.jpg?h=650&w=940", 6000, 4000) == (
            940,
            626,
        )

    def test_height_binds_when_source_is_squarer_than_the_box(self):
        # A = 1.333 < 940/650, so height hits the box instead.
        assert delivered_dimensions("https://x/p.jpg?h=650&w=940", 4000, 3000) == (
            866,
            650,
        )

    def test_never_upscales_past_the_source(self):
        """A box larger than the photo must not claim pixels that do not exist."""
        assert delivered_dimensions("https://x/p.jpg?h=650&w=940", 300, 200) == (
            300,
            200,
        )

    def test_no_box_returns_the_source(self):
        assert delivered_dimensions("https://x/p.jpg", 1200, 800) == (1200, 800)

    @pytest.mark.parametrize(
        "source_w,source_h",
        [(w, h) for w in (800, 1999, 3000, 4001, 6000) for h in (533, 1000, 2398, 4000)],
    )
    @pytest.mark.parametrize(
        "url",
        [
            "https://x/p.jpg?auto=compress&cs=tinysrgb&h=350",
            "https://x/p.jpg?auto=compress&cs=tinysrgb&h=650&w=940",
        ],
    )
    def test_never_overstates_the_real_raster(self, url, source_w, source_h):
        """THE load-bearing property: the stored size is never bigger than truth.

        Truth is the exact real-valued scale of the source; whatever rounding the
        renderer applies lands at or above our floored value, so a descriptor
        built from this can only ever understate. Understating costs at most one
        pixel of sharpness. Overstating causes the upscale this work exists to
        prevent.
        """
        got = delivered_dimensions(url, source_w, source_h)
        assert got is not None
        width, height = got

        box_w = 940 if "w=940" in url else None
        box_h = 650 if "h=650" in url else 350
        scales = [box_h / source_h] + ([box_w / source_w] if box_w else [])
        scale = min(min(scales), 1.0)
        exact_w, exact_h = source_w * scale, source_h * scale

        assert width <= math.ceil(exact_w)
        assert height <= math.ceil(exact_h)
        assert width <= source_w and height <= source_h
        # And it must still be useful, not trivially small.
        assert width >= math.floor(exact_w)
        assert height >= math.floor(exact_h)

    @pytest.mark.parametrize(
        "bad", [(None, None), (0, 100), (100, 0), (-5, 10), (None, 400)]
    )
    def test_unusable_source_yields_none_not_a_guess(self, bad):
        """NULL is the honest answer; a guess would be written and believed."""
        assert delivered_dimensions("https://x/p.jpg?h=350", *bad) is None

    def test_empty_url_yields_none(self):
        assert delivered_dimensions("", 1000, 800) is None

    def test_garbage_box_params_are_ignored_not_crashed(self):
        assert delivered_dimensions("https://x/p.jpg?h=abc", 1200, 800) == (1200, 800)
        assert delivered_dimensions("https://x/p.jpg?h=0", 1200, 800) == (1200, 800)


class TestEveryImageWriterSizesWhatItWrites:
    """Whoever sets image_url must set the dimensions in the same breath.

    The failure this prevents is quiet and nasty: enrich_tmdb REPLACES a Pexels
    photo with TMDB art. If it updated image_url and left image_width alone, the
    row would carry the old photo's size describing the new image — worse than
    NULL, because NULL is disbelieved and a number is not. Any future writer has
    the same obligation, so the check is on the file, not on one call site.
    """

    WRITER_FILES = [
        "app/tasks/enrich_markets.py",
        "app/tasks/enrich_tmdb.py",
        "scripts/run_image_enrichment.py",
        "scripts/enrich_feed_markets.py",
    ]

    def _writer_functions(self, tree):
        """Functions that assign image_url, by keyword or as a dict key."""
        found = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            writes = False
            for sub in ast.walk(node):
                # .values(image_url=...)
                if isinstance(sub, ast.keyword) and sub.arg == "image_url":
                    writes = True
                # values["image_url"] = ... / {"image_url": ...}
                elif isinstance(sub, ast.Constant) and sub.value == "image_url":
                    writes = True
            if writes:
                found.append(node)
        return found

    @pytest.mark.parametrize("relpath", WRITER_FILES)
    def test_writer_also_sets_dimensions(self, relpath):
        path = pathlib.Path(__file__).resolve().parent.parent / relpath
        # A guard that cannot read its subject must fail loudly, not pass.
        assert path.exists(), f"{relpath} is gone — this guard needs re-pointing"
        source = path.read_text()
        tree = ast.parse(source)  # SyntaxError here should fail the test, not be caught

        writers = self._writer_functions(tree)
        assert writers, (
            f"{relpath} no longer writes image_url anywhere — either the writer "
            f"moved (re-point this guard) or the detector has gone blind"
        )

        for fn in writers:
            body = ast.get_source_segment(source, fn) or ""
            assert "image_width" in body and "image_height" in body, (
                f"{relpath}:{fn.lineno} {fn.name}() sets image_url without setting "
                f"image_width/image_height — stale dimensions would describe the "
                f"wrong photo"
            )


class TestTmdbDeclaredWidth:
    def test_reads_the_width_token(self):
        assert (
            tmdb_declared_width("https://image.tmdb.org/t/p/w1280/abc.jpg") == 1280
        )
        assert tmdb_declared_width("https://image.tmdb.org/t/p/w780/abc.jpg") == 780

    def test_non_tmdb_or_sizeless_url_yields_none(self):
        assert tmdb_declared_width("https://image.tmdb.org/t/p/original/a.jpg") is None
        assert tmdb_declared_width("https://images.pexels.com/photos/1/x.jpeg") is None
        assert tmdb_declared_width("") is None
