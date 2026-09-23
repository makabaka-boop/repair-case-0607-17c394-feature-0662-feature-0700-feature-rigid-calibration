import { describe, expect, it } from "vitest";
import { buildPayload, validateDraft, type FormDraft } from "./validation";

const calibrationOff = {
  calibrationEnabled: false,
  calibrationMaxRmsError: "1",
  calibrationPairs: [],
};

const okDraft: FormDraft = {
  cableRadius: "5",
  nodes: [
    { x: "0", y: "0" },
    { x: "100", y: "0" },
  ],
  circles: [{ x: "50", y: "30", radius: "10" }],
  ...calibrationOff,
};

const calibrationPairs = [
  { surveyX: "0", surveyY: "0", pathX: "10", pathY: "20" },
  { surveyX: "1", surveyY: "0", pathX: "11", pathY: "20" },
  { surveyX: "0", surveyY: "1", pathX: "10", pathY: "21" },
];

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
      ...calibrationOff,
    };
    const errors = validateDraft(d);
    expect(Object.keys(errors).sort()).toEqual(
      ["cable_radius", "circles[0].radius", "nodes", "nodes[0].x"].sort(),
    );
  });

  it("标定关闭时载荷省略 calibration", () => {
    expect("calibration" in buildPayload(okDraft)).toBe(false);
  });

  it("标定开启时校验成对控制点并生成等长数组", () => {
    const d: FormDraft = {
      ...okDraft,
      calibrationEnabled: true,
      calibrationMaxRmsError: "0.25",
      calibrationPairs,
    };
    expect(validateDraft(d)).toEqual({});
    const payload = buildPayload(d);
    if (!("calibration" in payload)) throw new Error("calibration 应包含在载荷中");
    expect(payload.calibration).toEqual({
      survey_points: [
        { x: 0, y: 0 },
        { x: 1, y: 0 },
        { x: 0, y: 1 },
      ],
      path_points: [
        { x: 10, y: 20 },
        { x: 11, y: 20 },
        { x: 10, y: 21 },
      ],
      max_rms_error: 0.25,
    });
  });

  it("标定控制点少于 2 对、非有限或全部重合时字段报错", () => {
    const onePair: FormDraft = {
      ...okDraft,
      calibrationEnabled: true,
      calibrationPairs: [calibrationPairs[0]],
    };
    expect(validateDraft(onePair)["calibration.survey_points"]).toContain("2～20");

    const invalid = calibrationPairs.map((p, i) =>
      i === 1 ? { ...p, surveyX: "NaN", pathY: "" } : p,
    );
    const errors = validateDraft({
      ...okDraft,
      calibrationEnabled: true,
      calibrationPairs: invalid,
    });
    expect(errors["calibration.survey_points[1].x"]).toBeTruthy();
    expect(errors["calibration.path_points[1].y"]).toBeTruthy();

    const sameSurvey = calibrationPairs.map((p) => ({ ...p, surveyX: "5", surveyY: "6" }));
    expect(
      validateDraft({ ...okDraft, calibrationEnabled: true, calibrationPairs: sameSurvey })[
        "calibration.survey_points"
      ],
    ).toContain("不能全部重合");
  });
});
