/**
 * The smallest `document` that lets `react-dom/client` mount and update a
 * component under `testEnvironment: 'node'` — no jsdom, no react-test-renderer,
 * nothing added to package.json (the sandbox that runs this suite cannot reach
 * the npm registry; see `sectionErrorBoundary.test.tsx`).
 *
 * It is NOT a browser. It knows how to hold a tree of elements and text nodes,
 * append/insert/remove them, and answer `textContent`; nothing else. That is
 * exactly the surface a hook harness rendering one text node needs, and it is
 * enough for react-dom's feature probes at import time (`createElement('div')`
 * and `.style`). Import this module BEFORE `react-dom` and BEFORE `swr` — both
 * read `window`/`document` at module evaluation.
 */

type Node = {
  nodeType: number;
  tagName?: string;
  data?: string;
  nodeValue?: string;
  childNodes: Node[];
  parentNode: Node | null;
  ownerDocument: Node | null;
  namespaceURI: string;
  style: Record<string, string>;
  textContent: string;
  firstChild: Node | null;
  lastChild: Node | null;
  nextSibling: Node | null;
  addEventListener: () => void;
  removeEventListener: () => void;
  appendChild: (c: Node) => Node;
  insertBefore: (c: Node, ref: Node | null) => Node;
  removeChild: (c: Node) => Node;
  setAttribute: (k: string, v: unknown) => void;
  removeAttribute: (k: string) => void;
  [extra: string]: unknown;
};

function makeNode(nodeType: number, tagName?: string): Node {
  const node = {
    nodeType,
    tagName,
    childNodes: [] as Node[],
    parentNode: null as Node | null,
    ownerDocument: null as Node | null,
    namespaceURI: "http://www.w3.org/1999/xhtml",
    style: {} as Record<string, string>,
    addEventListener() {},
    removeEventListener() {},
    appendChild(c: Node) { node.childNodes.push(c); c.parentNode = node; return c; },
    insertBefore(c: Node, ref: Node | null) {
      const i = ref ? node.childNodes.indexOf(ref) : -1;
      node.childNodes.splice(i < 0 ? node.childNodes.length : i, 0, c);
      c.parentNode = node;
      return c;
    },
    removeChild(c: Node) {
      const i = node.childNodes.indexOf(c);
      if (i >= 0) node.childNodes.splice(i, 1);
      c.parentNode = null;
      return c;
    },
    setAttribute(k: string, v: unknown) { (node as Record<string, unknown>)[k] = v; },
    removeAttribute(k: string) { delete (node as Record<string, unknown>)[k]; },
    get textContent(): string {
      return node.childNodes.map((n) => (n.nodeType === 3 ? n.data ?? "" : n.textContent)).join("");
    },
    set textContent(v: string) { node.childNodes = v === "" ? [] : [makeText(v)]; },
    get firstChild() { return node.childNodes[0] ?? null; },
    get lastChild() { return node.childNodes[node.childNodes.length - 1] ?? null; },
    get nextSibling() {
      const p = node.parentNode;
      if (!p) return null;
      return p.childNodes[p.childNodes.indexOf(node) + 1] ?? null;
    },
  } as Node;
  return node;
}

function makeText(data: string): Node {
  const node = makeNode(3);
  node.data = data;
  Object.defineProperty(node, "nodeValue", {
    get: () => node.data,
    set: (v: string) => { node.data = v; },
  });
  return node;
}

export function installMinimalDom(): { document: Node; body: Node } {
  const document = makeNode(9, "#document");
  const doc = document as Node & Record<string, unknown>;
  doc.createElement = (tag: string) => {
    const el = makeNode(1, tag.toUpperCase());
    el.ownerDocument = document;
    return el;
  };
  doc.createElementNS = (_ns: string, tag: string) => (doc.createElement as (t: string) => Node)(tag);
  doc.createTextNode = (data: string) => {
    const t = makeText(data);
    t.ownerDocument = document;
    return t;
  };
  const html = (doc.createElement as (t: string) => Node)("html");
  const body = (doc.createElement as (t: string) => Node)("body");
  html.appendChild(body);
  doc.documentElement = html;
  doc.body = body;
  doc.activeElement = body;
  const window = {
    document,
    addEventListener() {},
    removeEventListener() {},
    navigator: { userAgent: "node" },
    location: { href: "http://localhost/" },
    HTMLIFrameElement: function HTMLIFrameElement() {},
  };
  doc.defaultView = window;
  (globalThis as Record<string, unknown>).window = window;
  (globalThis as Record<string, unknown>).document = document;
  // react-dom reads the BARE global `navigator` at module load once `window`
  // exists. Node 21+ defines one; CI runs Node 20, which does not.
  if (typeof (globalThis as Record<string, unknown>).navigator === "undefined") {
    Object.defineProperty(globalThis, "navigator", {
      value: window.navigator,
      configurable: true,
      writable: true,
    });
  }
  (globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;
  return { document, body };
}

export const minimalDom = installMinimalDom();
