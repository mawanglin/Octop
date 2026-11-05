import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { requestMock } = vi.hoisted(() => ({ requestMock: vi.fn() }));

// A stable `t`, like the real react-i18next hook returns.
const translate = (
  key: string,
  opts?: string | { defaultValue?: string; count?: number },
) => {
  if (typeof opts === "string") return opts;
  if (opts?.defaultValue)
    return opts.defaultValue.replace("{{count}}", String(opts.count));
  return key;
};
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: translate }),
}));
vi.mock("../../../api/request", () => ({ request: requestMock }));
vi.mock("../../../components/PillScroller", () => ({
  default: ({
    options,
    active,
    onSelect,
  }: {
    options: { value: string; label: string }[];
    active: string;
    onSelect: (v: string) => void;
  }) => (
    <div>
      {options.map((o) => (
        <button
          key={o.value}
          data-testid={`scene-${o.value || "all"}`}
          aria-pressed={o.value === active}
          onClick={() => onSelect(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  ),
}));
vi.mock("./ExpertCard", () => ({
  ExpertCard: ({
    expert,
    isInstalled,
    onCreate,
  }: {
    expert: { id: string; label: { zh?: string } };
    isInstalled: boolean;
    onCreate: (e: unknown) => void;
  }) => (
    <button
      data-testid={`card-${expert.id}`}
      data-installed={isInstalled}
      onClick={() => onCreate(expert)}
    >
      {expert.label.zh}
    </button>
  ),
}));

import BuiltinLibraryTab from "./BuiltinLibraryTab";

const rows = [
  { id: "default", label: { zh: "空白专家" }, description: {}, scene: null },
  {
    id: "fact-checker",
    label: { zh: "内容核验员" },
    description: { zh: "逐条核对" },
    scene: "content-creation",
  },
  {
    id: "architect",
    label: { zh: "架构师专家" },
    description: { zh: "方案设计" },
    scene: "tech",
  },
  {
    id: "fullstack-dev",
    label: { zh: "全栈开发专家" },
    description: { zh: "写代码" },
    scene: "tech",
  },
];

function renderTab(extra: { installed?: string[] } = {}) {
  const onRequestCreate = vi.fn();
  render(
    <BuiltinLibraryTab
      lang="zh"
      installedExpertIds={new Set(extra.installed ?? [])}
      onRequestCreate={onRequestCreate}
    />,
  );
  return onRequestCreate;
}

describe("BuiltinLibraryTab", () => {
  beforeEach(() => {
    requestMock.mockReset();
    requestMock.mockResolvedValue(rows);
  });

  it("lists bundled templates from /experts, without the blank default seed", async () => {
    renderTab();
    await screen.findByTestId("card-fact-checker");
    expect(requestMock).toHaveBeenCalledWith("/experts");
    expect(screen.queryByTestId("card-default")).toBeNull();
    expect(screen.getByText("共 3 个内置专家")).toBeTruthy();
  });

  it("filters by scene, and searching ignores the scene filter", async () => {
    renderTab();
    await screen.findByTestId("card-architect");
    fireEvent.click(screen.getByTestId("scene-tech"));
    expect(screen.queryByTestId("card-fact-checker")).toBeNull();
    expect(screen.getByTestId("card-architect")).toBeTruthy();
    fireEvent.change(screen.getByPlaceholderText("搜索内置专家"), {
      target: { value: "核对" },
    });
    await waitFor(() =>
      expect(screen.getByTestId("card-fact-checker")).toBeTruthy(),
    );
    expect(screen.queryByTestId("card-architect")).toBeNull();
  });

  it("marks installed templates and hands the chosen one to the create drawer", async () => {
    const onRequestCreate = renderTab({ installed: ["architect"] });
    const card = await screen.findByTestId("card-architect");
    expect(card.getAttribute("data-installed")).toBe("true");
    expect(
      screen.getByTestId("card-fact-checker").getAttribute("data-installed"),
    ).toBe("false");
    fireEvent.click(screen.getByTestId("card-fact-checker"));
    expect(onRequestCreate).toHaveBeenCalledWith(
      expect.objectContaining({ id: "fact-checker" }),
    );
  });

  it("shows an empty state and a retry on failure", async () => {
    requestMock.mockRejectedValueOnce(new Error("boom"));
    renderTab();
    await screen.findByText("内置专家模板加载失败");
    requestMock.mockResolvedValueOnce(rows);
    fireEvent.click(screen.getByText("common.refresh"));
    await screen.findByTestId("card-architect");

    requestMock.mockResolvedValue([rows[0]]);
    renderTab();
    await screen.findAllByText("暂无内置专家模板");
  });
});
