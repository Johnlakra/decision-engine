// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppNav } from "./AppNav";

const pathname = vi.hoisted(() => ({ value: "/sources" }));
vi.mock("next/navigation", () => ({ usePathname: () => pathname.value }));

afterEach(cleanup);

describe("AppNav", () => {
  it("links to Sources and Insights", () => {
    render(<AppNav locale="en" />);

    expect(screen.getByRole("link", { name: "Sources" }).getAttribute("href")).toBe("/sources");
    expect(screen.getByRole("link", { name: "Insights" }).getAttribute("href")).toBe("/insights");
  });

  it("marks only the current section", () => {
    pathname.value = "/insights";
    render(<AppNav locale="en" />);

    expect(screen.getByRole("link", { name: "Insights" }).getAttribute("aria-current")).toBe("page");
    expect(screen.getByRole("link", { name: "Sources" }).getAttribute("aria-current")).toBeNull();
  });

  it("uses the Hindi labels", () => {
    render(<AppNav locale="hi" />);

    expect(screen.getByRole("link", { name: "स्रोत" }).getAttribute("href")).toBe("/sources");
  });
});
