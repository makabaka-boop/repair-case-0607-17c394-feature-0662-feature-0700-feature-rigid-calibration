import type { FieldErrors } from "../types";

/** 表单中的原始字段都以字符串保存，提交时统一解析、校验。 */
export interface NodeDraft {
  x: string;
  y: string;
}
export interface CircleDraft {
  x: string;
  y: string;
  radius: string;
}
export interface FormDraft {
  cableRadius: string;
  nodes: NodeDraft[];
  circles: CircleDraft[];
}

function parseFiniteInt(raw: string): number {
  const t = raw.trim();
  if (!/^[+-]?\d+$/.test(t)) {
    // 拒绝空串、小数、NaN、Infinity、字母等
    throw new Error("必须是整数毫米");
  }
  const n = Number(t);
  if (!Number.isSafeInteger(n)) throw new Error("整数超出安全范围");
  return n;
}

function parsePositiveFinite(raw: string): number {
  const t = raw.trim();
  if (t === "") throw new Error("不能为空");
  const n = Number(t);
  if (!Number.isFinite(n)) throw new Error("必须是有限数值");
  if (n <= 0) throw new Error("必须为正数");
  return n;
}

/** 与后端一致的字段级校验；返回 errors 映射（空对象表示通过）。 */
export function validateDraft(draft: FormDraft): FieldErrors {
  const errors: FieldErrors = {};

  try {
    parsePositiveFinite(draft.cableRadius);
  } catch (e) {
    errors.cable_radius = `电缆半径${(e as Error).message}`;
  }

  if (draft.nodes.length < 2) {
    errors.nodes = "路径至少需要两个节点";
  }
  draft.nodes.forEach((node, i) => {
    try {
      parseFiniteInt(node.x);
    } catch (e) {
      errors[`nodes[${i}].x`] = `X ${(e as Error).message}`;
    }
    try {
      parseFiniteInt(node.y);
    } catch (e) {
      errors[`nodes[${i}].y`] = `Y ${(e as Error).message}`;
    }
  });

  // 相邻重复节点
  for (let i = 0; i < draft.nodes.length - 1; i++) {
    const a = draft.nodes[i];
    const b = draft.nodes[i + 1];
    if (
      a.x.trim() !== "" &&
      a.y.trim() !== "" &&
      b.x.trim() !== "" &&
      b.y.trim() !== "" &&
      a.x.trim() === b.x.trim() &&
      a.y.trim() === b.y.trim()
    ) {
      errors[`nodes[${i + 1}].x`] = "与上一节点重合，禁止相邻重复节点";
    }
  }

  draft.circles.forEach((c, i) => {
    try {
      parseFiniteInt(c.x);
    } catch (e) {
      errors[`circles[${i}].x`] = `圆心 X ${(e as Error).message}`;
    }
    try {
      parseFiniteInt(c.y);
    } catch (e) {
      errors[`circles[${i}].y`] = `圆心 Y ${(e as Error).message}`;
    }
    try {
      parsePositiveFinite(c.radius);
    } catch (e) {
      errors[`circles[${i}].radius`] = `半径${(e as Error).message}`;
    }
  });

  return errors;
}

/** 解析为后端载荷；调用前应已通过 validateDraft。 */
export function buildPayload(draft: FormDraft) {
  return {
    cable_radius: parsePositiveFinite(draft.cableRadius),
    nodes: draft.nodes.map((n) => ({
      x: parseFiniteInt(n.x),
      y: parseFiniteInt(n.y),
    })),
    circles: draft.circles.map((c) => ({
      x: parseFiniteInt(c.x),
      y: parseFiniteInt(c.y),
      radius: parsePositiveFinite(c.radius),
    })),
  };
}
