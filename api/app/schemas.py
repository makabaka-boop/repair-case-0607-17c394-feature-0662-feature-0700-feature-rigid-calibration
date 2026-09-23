"""Pydantic 输入/输出模型与字段级校验。

所有非法情形都产生携带字段定位的错误，交由异常处理器转为 422：
非有限数值、节点不足、非正半径、相邻重复节点、非整数毫米坐标、布尔值等。
"""

from __future__ import annotations

import math
from typing import Annotated, List, Tuple

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)
from pydantic.functional_validators import BeforeValidator
from pydantic.types import StrictFloat, StrictInt


def _strict_mm_int(v):
    """整数毫米：只接受 int（拒绝 bool）；float/字符串一律拒绝。

    这样 JSON 中的 "NaN"/"Infinity"/"1.5" 等都无法借宽松解析混入。
    """
    if isinstance(v, bool):
        raise ValueError("必须是整数毫米数值，不能是布尔值")
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        if not math.isfinite(v):
            raise ValueError("必须是有限数值（不能是 NaN 或无穷）")
        raise ValueError("坐标必须是整数毫米，不接受小数")
    raise ValueError("必须是整数毫米数值")


def _positive_finite(v):
    """正数半径：接受有限的 int/float，拒绝布尔、NaN、Infinity 与非正数值。"""
    if isinstance(v, bool):
        raise ValueError("必须是正数，不能是布尔值")
    if isinstance(v, int):
        f = float(v)
    elif isinstance(v, float):
        f = v
    else:
        # 字符串等类型：交给 StrictFloat/StrictInt 核心报类型错误。
        return v
    if not math.isfinite(f):
        raise ValueError("必须是有限正数（不能是 NaN 或无穷）")
    if f <= 0:
        raise ValueError("必须为正数")
    return f


def _strict_finite_number(v):
    """标定坐标：接受有限 int/float（含小数），拒绝布尔、字符串与非有限值。"""
    if isinstance(v, bool):
        raise ValueError("必须是数值，不能是布尔值")
    if isinstance(v, (int, float)):
        if not math.isfinite(float(v)):
            raise ValueError("必须是有限数值（不能是 NaN 或无穷）")
        return v
    # 让 float 核心给出统一的 number 类型错误。
    raise ValueError("必须是数值，不能是字符串或其他类型")


# 整数毫米坐标；外层 StrictInt 确保 "NaN" 之类字符串不被宽松解析。
MmInt = Annotated[StrictInt, BeforeValidator(_strict_mm_int)]
# 正数半径（可以是小数毫米）；StrictFloat/StrictInt 拒绝字符串。
PositiveRadius = Annotated[
    StrictFloat | StrictInt, BeforeValidator(_positive_finite)
]
FiniteNumber = Annotated[
    StrictFloat | StrictInt, BeforeValidator(_strict_finite_number)
]


class StrictPointIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: MmInt
    y: MmInt


class StrictCircleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: MmInt
    y: MmInt
    radius: PositiveRadius


class CalibrationPointIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: FiniteNumber
    y: FiniteNumber


class CalibrationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    survey_points: Annotated[List[CalibrationPointIn], Field(min_length=2, max_length=20)]
    path_points: Annotated[List[CalibrationPointIn], Field(min_length=2, max_length=20)]
    max_rms_error: PositiveRadius

    @field_validator("survey_points", "path_points")
    @classmethod
    def _reject_all_coincident_points(
        cls, points: List[CalibrationPointIn]
    ) -> List[CalibrationPointIn]:
        first = points[0]
        if all(p.x == first.x and p.y == first.y for p in points[1:]):
            raise ValueError("控制点不能全部重合")
        return points

    @field_validator("path_points")
    @classmethod
    def _validate_path_points(cls, points: List[CalibrationPointIn], info):
        first = points[0]
        if all(p.x == first.x and p.y == first.y for p in points[1:]):
            raise ValueError("控制点不能全部重合")
        survey_points = info.data.get("survey_points")
        if survey_points is not None and len(survey_points) != len(points):
            raise ValueError("path_points 必须与 survey_points 等长并逐对对应")
        return points


class PrecheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: Annotated[List[StrictPointIn], Field(min_length=2)]
    cable_radius: PositiveRadius
    circles: List[StrictCircleIn]
    calibration: CalibrationIn | None = None

    @field_validator("nodes")
    @classmethod
    def _reject_adjacent_duplicate_nodes(cls, nodes: List[StrictPointIn]):
        # 相邻重复节点会产生退化（零长）线段；错误挂在 nodes 字段上。
        for i in range(len(nodes) - 1):
            a = nodes[i]
            b = nodes[i + 1]
            if a.x == b.x and a.y == b.y:
                raise ValueError(
                    f"相邻节点 #{i} 与 #{i + 1} 完全重合，禁止相邻重复节点"
                )
        return nodes


class PointOut(BaseModel):
    x: float
    y: float


class CollisionOut(BaseModel):
    segment_index: int
    circle_index: int
    nearest: PointOut          # 判定位置（展示坐标，四舍五入至三位小数）
    distance: float            # 圆心到判定位置的距离（三位小数）
    expanded_radius: float     # 禁入圈半径 + 电缆半径（三位小数）
    circle_center: PointOut
    circle_radius: float
    cable_radius: float


class CircleOut(BaseModel):
    center: PointOut
    radius: float            # 展示用（三位小数）
    expanded_radius: float   # radius + cable_radius（三位小数）


class IntervalPieceOut(BaseModel):
    """区间内单条线段上的侵入片段（展示值，三位小数）。"""

    segment_index: int
    circle_index: int
    entry: PointOut             # 进入点
    exit: PointOut              # 离开点（与进入点相同即相切零长点）
    start_mileage: float        # 进入点累计里程
    end_mileage: float          # 离开点累计里程
    length: float               # 片段侵入长度（零长相切为 0）


class IntrusionIntervalOut(BaseModel):
    """可施工定位的连续侵入区间（展示值，三位小数）。"""

    circle_index: int
    entry_segment_index: int    # 进入线段
    exit_segment_index: int     # 离开线段
    entry: PointOut
    exit: PointOut
    start_mileage: float        # 区间起点累计里程
    end_mileage: float          # 区间终点累计里程
    length: float               # 区间侵入长度（end - start；零长相切为 0）
    pieces: List[IntervalPieceOut]  # 覆盖到的线段片段（路径顺序），供 SVG 高亮


class CompoundPieceOut(BaseModel):
    """复合侵入段在一条原线段上的片段（展示值，三位小数）。"""

    segment_index: int
    circle_indices: List[int]   # 该片段上同时活动的全部禁入圈（升序）
    entry: PointOut
    exit: PointOut
    start_mileage: float
    end_mileage: float
    length: float               # 零长点（拐点相切）为 0


class CompoundIntrusionSegmentOut(BaseModel):
    """同时落入至少两个扩张圈的最大连续分段（展示值，三位小数）。"""

    circle_indices: List[int]        # 恒为该分段的活动圈集合（升序）
    start_mileage: float             # 起始累计里程（未舍入排序，展示三位）
    end_mileage: float               # 终止累计里程
    start: PointOut                  # 起点坐标
    end: PointOut                    # 终点坐标
    start_inclusive: bool            # 是否包含起始里程（开邻域起点为 false）
    end_inclusive: bool              # 是否包含终止里程
    length: float                    # end_mileage - start_mileage（零长点为 0）
    pieces: List[CompoundPieceOut]   # 按原线段切分的片段，供 SVG 高亮


RotationMatrixOut = Tuple[Tuple[float, float], Tuple[float, float]]


class CalibrationPointResidualOut(BaseModel):
    index: int
    survey_point: PointOut
    path_point: PointOut
    residual: float


class CalibrationOut(BaseModel):
    rotation: RotationMatrixOut
    translation: PointOut
    rms_error: float
    max_rms_error: float
    point_residuals: List[CalibrationPointResidualOut]


class PrecheckResponse(BaseModel):
    feasible: bool
    cable_radius: float      # 展示用（三位小数）
    nodes: List[PointOut]
    circles: List[CircleOut]
    collision_count: int
    first_collision: CollisionOut | None = None
    collisions: List[CollisionOut]
    intrusion_intervals: List[IntrusionIntervalOut] = Field(default_factory=list)
    compound_intrusion_segments: List[CompoundIntrusionSegmentOut] = Field(
        default_factory=list
    )
    calibration: CalibrationOut | None = None
