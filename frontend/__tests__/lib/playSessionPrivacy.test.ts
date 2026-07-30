// L2-214 Item 3 — Play session identity must be opaque and device-scoped, never
// name-derived. Mirrors backend/scripts/evals/kid_session_privacy_fixtures.json
// (kid-session-privacy/v1): opaque `kid_device:` prefix, stable per device across
// renames, distinct across devices even with the same name, rotates on storage
// clear, and the legacy `kid:<name>` id is never produced.

class FakeStorage {
  private store: Record<string, string> = {};
  blocked = false;
  getItem(k: string): string | null {
    if (this.blocked) throw new Error("storage blocked");
    return k in this.store ? this.store[k] : null;
  }
  setItem(k: string, v: string): void {
    if (this.blocked) throw new Error("storage blocked");
    this.store[k] = v;
  }
  removeItem(k: string): void {
    delete this.store[k];
  }
}

/** Load a fresh copy of the module so its per-page ephemeral fallback resets. */
function loadSession(storage: FakeStorage) {
  let mod: typeof import("@/lib/play/session");
  jest.isolateModules(() => {
    (global as unknown as { window: object }).window = {};
    (global as unknown as { localStorage: FakeStorage }).localStorage = storage;
    mod = require("@/lib/play/session");
  });
  return mod!;
}

const PREFIX = "kid_device:";

describe("Play session identity — opaque + device-scoped (L2-214)", () => {
  afterEach(() => {
    delete (global as unknown as { window?: object }).window;
    delete (global as unknown as { localStorage?: FakeStorage }).localStorage;
  });

  it("first launch generates an opaque kid_device: id and persists it", () => {
    const storage = new FakeStorage();
    const mod = loadSession(storage);
    const id = mod.kidSessionId();
    expect(id.startsWith(PREFIX)).toBe(true);
    // never a legacy name-derived id
    expect(id.startsWith("kid:")).toBe(false);
    expect(storage.getItem("bainluck_play_device_id_v1")).toBe(id);
  });

  it("repeat launch on the same device returns the SAME id (rename-stable)", () => {
    const storage = new FakeStorage();
    const mod = loadSession(storage);
    const first = mod.kidSessionId();
    const again = mod.kidSessionId();
    expect(again).toBe(first);
    // kidSessionId takes no name — identity is independent of display name.
    expect((mod.kidSessionId as () => string).length).toBe(0);
  });

  it("two devices with the SAME display name get DISTINCT ids", () => {
    const idA = loadSession(new FakeStorage()).kidSessionId();
    const idB = loadSession(new FakeStorage()).kidSessionId();
    expect(idA).not.toBe(idB);
  });

  it("clearing storage rotates the id", () => {
    const storage = new FakeStorage();
    const mod = loadSession(storage);
    const first = mod.kidSessionId();
    storage.removeItem("bainluck_play_device_id_v1");
    const rotated = mod.kidSessionId();
    expect(rotated).not.toBe(first);
    expect(rotated.startsWith(PREFIX)).toBe(true);
  });

  it("a non-opaque legacy value in storage is never reused", () => {
    const storage = new FakeStorage();
    storage.setItem("bainluck_play_device_id_v1", "kid:alex");
    const mod = loadSession(storage);
    const id = mod.kidSessionId();
    expect(id).not.toBe("kid:alex");
    expect(id.startsWith(PREFIX)).toBe(true);
  });

  it("blocked storage still yields a stable ephemeral opaque id (no persistence)", () => {
    const storage = new FakeStorage();
    storage.blocked = true;
    const mod = loadSession(storage);
    const first = mod.kidSessionId();
    const again = mod.kidSessionId();
    expect(first.startsWith(PREFIX)).toBe(true);
    expect(again).toBe(first); // stable within the page
  });

  it("SSR (no window) transmits nothing", () => {
    // isolateModules with window deleted
    let mod: typeof import("@/lib/play/session");
    jest.isolateModules(() => {
      delete (global as unknown as { window?: object }).window;
      mod = require("@/lib/play/session");
    });
    expect(mod!.kidSessionId()).toBe("");
  });
});
