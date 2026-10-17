// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { NO_FILTER } from "@/lib/queue/filters";
import { FilterChips } from "./FilterChips";

const CHOICES = { niches: ["news_radar", "tech_stack"], sources: ["rss", "webhook"] };

afterEach(() => {
  cleanup();
});

describe("FilterChips", () => {
  it("marks the active chips as pressed and 'All' pressed when nothing is filtered", () => {
    render(<FilterChips locale="en" choices={CHOICES} filter={NO_FILTER} onChange={vi.fn()} />);

    expect(screen.getByRole("button", { name: "All niches" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "news_radar" }).getAttribute("aria-pressed")).toBe("false");
  });

  it("reports a niche pick and keeps the source chip as it was", () => {
    const onChange = vi.fn();
    render(
      <FilterChips
        locale="en"
        choices={CHOICES}
        filter={{ niche: null, source: "rss" }}
        onChange={onChange}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "tech_stack" }));

    expect(onChange).toHaveBeenCalledWith({ niche: "tech_stack", source: "rss" });
  });

  it("clears only its own group when 'All' is pressed", () => {
    const onChange = vi.fn();
    render(
      <FilterChips
        locale="en"
        choices={CHOICES}
        filter={{ niche: "news_radar", source: "webhook" }}
        onChange={onChange}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "All sources" }));

    expect(onChange).toHaveBeenCalledWith({ niche: "news_radar", source: null });
  });

  it("renders nothing when there is nothing to filter by", () => {
    const { container } = render(
      <FilterChips locale="en" choices={{ niches: [], sources: [] }} filter={NO_FILTER} onChange={vi.fn()} />,
    );

    expect(container.textContent).toBe("");
  });
});
