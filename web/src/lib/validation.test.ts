import { describe, expect, it } from "vitest";
import { buildPayload, validateDraft, type FormDraft } from "./validation";

const okDraft: FormDraft = {
  cableRadius: "5",
  nodes: [
    { x: "0", y: "0" },
    { x: "100", y: "0" },
  ],
  circles: [{ x: "50", y: "30", radius: "10" }],
};

describe("录入校验 validateDraft（与后端字段键一致）", () => {
  it("合法录入无错误", () => {
    expect(validateDraft(okDraft)).toEqual({});
    expect(buildPayload(okDraft)).toEqual({
      cable_radius: 5,
      nodes: [
        { x: 0, y: 0 },
        { x: 100, y: 0 },
      ],
      circles: [{ x: 50, y: 30, radius: 10 }],
    });
  });

  it("节点不足报错", () => {
    const d: FormDraft = { ...okDraft, nodes: [{ x: "0", y: "0" }] };
    expect(validateDraft(d).nodes).toContain("至少");
  });

  it("非正电缆半径报错", () => {
    expect(validateDraft({ ...okDraft, cableRadius: "0" }).cable_radius).toBeTruthy();
    expect(validateDraft({ ...okDraft, cableRadius: "-2" }).cable_radius).toBeTruthy();
  });

  it("非整数毫米坐标报错，且拒绝 NaN / Infinity", () => {
    const cases = ["12.5", "abc", "NaN", "Infinity", "-Infinity", ""];
    for (const bad of cases) {
      const d: FormDraft = {
        ...okDraft,
        nodes: [
          { x: "0", y: "0" },
          { x: bad, y: "0" },
        ],
      };
      expect(validateDraft(d)["nodes[1].x"], `bad=${bad}`).toBeTruthy();
    }
  });

  it("相邻重复节点报错（挂字段级键）", () => {
    const d: FormDraft = {
      ...okDraft,
      nodes: [
        { x: "7", y: "7" },
        { x: "7", y: "7" },
      ],
    };
    const errors = validateDraft(d);
    expect(errors["nodes[1].x"]).toContain("重合");
  });

  it("禁入圈半径必须为有限正数", () => {
    const d: FormDraft = {
      ...okDraft,
      circles: [{ x: "0", y: "0", radius: "0" }],
    };
    expect(validateDraft(d)["circles[0].radius"]).toBeTruthy();
  });

  it("多个字段错误可同时收集", () => {
    const d: FormDraft = {
      cableRadius: "-1",
      nodes: [{ x: "x", y: "0" }],
      circles: [{ x: "1", y: "2", radius: "NaN" }],
    };
    const errors = validateDraft(d);
    expect(Object.keys(errors).sort()).toEqual(
      ["cable_radius", "circles[0].radius", "nodes", "nodes[0].x"].sort(),
    );
  });
});
