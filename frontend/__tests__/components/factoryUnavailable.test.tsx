import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import FactoryFloor from "@/app/factory/FactoryFloor";

jest.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: jest.fn() }),
}));
jest.mock("@/hooks/usePageTracking", () => ({ usePageTracking: jest.fn() }));
jest.mock("@/hooks/useScrollDepth", () => ({ useScrollDepth: jest.fn() }));
jest.mock("@/hooks/useEngagementTime", () => ({
  useEngagementTime: jest.fn(),
}));

it("shows an unavailable floor and the last good time without any historical counts", () => {
  const html = renderToStaticMarkup(
    <FactoryFloor
      data={null}
      lastGoodAt="2026-11-18T01:14:00Z"
      renderedAt="2026-11-18T02:00:00Z"
    />,
  );
  expect(html).toContain("The floor can&#x27;t be read right now");
  expect(html).toContain("5:14 PM PT");
  expect(html).not.toContain("Shipped today");
  expect(html).not.toContain("Saved snapshot");
});
