import { createHash } from "crypto";
import { readFileSync, statSync } from "fs";
import { join } from "path";

const ROOT = join(__dirname, "../..");

function readPngChunkTypes(buf: Buffer): string[] {
  const sig = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
  if (!buf.subarray(0, 8).equals(sig)) {
    throw new Error("Invalid PNG signature");
  }
  const chunks: string[] = [];
  let offset = 8;
  while (offset + 8 <= buf.length) {
    const length = buf.readUInt32BE(offset);
    const ctype = buf.subarray(offset + 4, offset + 8).toString("ascii");
    chunks.push(ctype);
    offset += 12 + length;
  }
  return chunks;
}

describe("#13633 — Website brand mark (382: B / 390: A)", () => {
  const generatedPngs = [
    "public/brand/bainluck-mark-1024.png",
    "public/brand/bainluck-mark-128.png",
    "public/brand/bainluck-drawing-1024.png",
    "public/icon-16.png",
    "public/icon-32.png",
    "public/icon-192.png",
    "public/icon-512.png",
    "app/icon.png",
    "app/apple-icon.png",
  ];

  it.each(generatedPngs)("%s contains critical PNG chunks only (IHDR/IDAT/IEND)", (rel) => {
    const buf = readFileSync(join(ROOT, rel));
    const chunks = readPngChunkTypes(buf);
    expect(chunks.length).toBeGreaterThanOrEqual(3);
    expect(chunks[0]).toBe("IHDR");
    expect(chunks[chunks.length - 1]).toBe("IEND");
    expect(new Set(chunks)).toEqual(new Set(["IHDR", "IDAT", "IEND"]));
  });

  it("includes favicon.ico and transparent 1024 mark + opaque 1024 drawing", () => {
    const ico = statSync(join(ROOT, "app/favicon.ico"));
    expect(ico.size).toBeGreaterThan(200);

    const mark = readFileSync(join(ROOT, "public/brand/bainluck-mark-1024.png"));
    // PNG IHDR width/height/colorType (RGBA = 6)
    expect(mark.readUInt32BE(16)).toBe(1024);
    expect(mark.readUInt32BE(20)).toBe(1024);
    expect(mark.readUInt8(25)).toBe(6);

    const drawing = readFileSync(join(ROOT, "public/brand/bainluck-drawing-1024.png"));
    expect(drawing.readUInt32BE(16)).toBe(1024);
    expect(drawing.readUInt32BE(20)).toBe(1024);
    expect(drawing.readUInt8(25)).toBe(2); // RGB opaque

    const dataUriModule = readFileSync(join(ROOT, "lib/og/brandDrawingDataUri.ts"), "utf8");
    const m = dataUriModule.match(/data:image\/png;base64,([A-Za-z0-9+/=]+)/);
    expect(m).not.toBeNull();
    const uriPng = Buffer.from(m![1], "base64");
    expect(new Set(readPngChunkTypes(uriPng))).toEqual(new Set(["IHDR", "IDAT", "IEND"]));
    expect(uriPng.readUInt32BE(16)).toBe(96);
    expect(uriPng.readUInt32BE(20)).toBe(96);
    expect(createHash("sha256").update(uriPng).digest("hex")).toBeTruthy();
  });

  it("replaces every brand clover emoji across shell chrome, brand pages, and OG share images", () => {
    const brandFiles = [
      "app/layout.tsx",
      "components/Footer.tsx",
      "components/DesktopNav.tsx",
      "components/BottomNav.tsx",
      "app/about/page.tsx",
      "app/kernels-preview/page.tsx",
      "app/play/page.tsx",
      "app/opengraph-image.tsx",
      "app/about/opengraph-image.tsx",
      "app/events/[id]/opengraph-image.tsx",
      "app/futures/[id]/opengraph-image.tsx",
      "components/og/UnfurlCard.tsx",
    ];
    for (const rel of brandFiles) {
      const src = readFileSync(join(ROOT, rel), "utf8");
      expect(src).not.toContain("\u{1F340}");
    }
  });
});
