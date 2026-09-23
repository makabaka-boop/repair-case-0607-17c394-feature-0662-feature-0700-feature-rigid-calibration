"""二维最小二乘保距刚体标定（survey 坐标 -> path 施工局部坐标）。

变换只含旋转与平移：``p = R*s + t``，其中 ``R`` 是行列式为 1 的二维正交
矩阵。实现不引入第三方矩阵库，也不通过相似变换估计尺度：二维闭式解直接
最大化平方残差意义下的旋转项，再以相对首点的向量计算平移，避免大坐标
平移时的灾难性抵消。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence, Tuple

Point = Tuple[float, float]


class CalibrationError(ValueError):
    """标定业务错误；``loc`` 为 calibration 下的明确定位片段。"""

    def __init__(self, message: str, loc: Tuple[str | int, ...] = ()) -> None:
        super().__init__(message)
        self.loc = loc


@dataclass(frozen=True)
class RigidTransform2D:
    rotation: Tuple[Tuple[float, float], Tuple[float, float]]
    translation: Point
    rms_error: float
    residuals: Tuple[float, ...]
    survey_anchor: Point
    path_anchor: Point
    translation_correction: Point

    def apply(self, p: Point) -> Point:
        # 用首点相对坐标求值，避免把巨大的绝对平移再与巨大坐标相减。
        dx = p[0] - self.survey_anchor[0]
        dy = p[1] - self.survey_anchor[1]
        return (
            self.path_anchor[0]
            + self.rotation[0][0] * dx
            + self.rotation[0][1] * dy
            + self.translation_correction[0],
            self.path_anchor[1]
            + self.rotation[1][0] * dx
            + self.rotation[1][1] * dy
            + self.translation_correction[1],
        )


def _all_coincident(points: Sequence[Point]) -> bool:
    x0, y0 = points[0]
    return all(x == x0 and y == y0 for x, y in points[1:])


def fit_rigid_transform_2d(
    survey_points: Sequence[Point],
    path_points: Sequence[Point],
    max_rms_error: float,
) -> RigidTransform2D:
    """求 survey -> path 的最小二乘 proper rotation + translation。

    输入点集已由 Pydantic 保证有限、等长且数量为 2～20。这里仍显式拒绝
    任一组全部重合的退化点集；两组均非共线时，用协方差行列式符号识别
    镜像对应关系。残差超过 ``max_rms_error`` 时抛出定位到阈值字段的错误。
    """
    if len(survey_points) != len(path_points):
        raise CalibrationError(
            "survey_points 与 path_points 必须等长",
            ("survey_points",),
        )
    if not math.isfinite(max_rms_error) or max_rms_error <= 0:
        raise CalibrationError("max_rms_error 必须为正数", ("max_rms_error",))

    n = len(survey_points)
    if n < 2:
        raise CalibrationError("至少需要 2 对控制点", ("survey_points",))

    if _all_coincident(survey_points):
        raise CalibrationError(
            "survey_points 全部重合，无法唯一确定旋转；至少需要两个不同测量点",
            ("survey_points",),
        )
    if _all_coincident(path_points):
        raise CalibrationError(
            "path_points 全部重合，无法唯一确定旋转；至少需要两个不同路径点",
            ("path_points",),
        )

    survey_anchor = survey_points[0]
    path_anchor = path_points[0]

    def _relative_mean(points: Sequence[Point], anchor: Point) -> Point:
        return (
            math.fsum(x - anchor[0] for x, _ in points) / n,
            math.fsum(y - anchor[1] for _, y in points) / n,
        )

    survey_delta_mean = _relative_mean(survey_points, survey_anchor)
    path_delta_mean = _relative_mean(path_points, path_anchor)

    sxx = syy = sxy = 0.0
    pxx = pyy = pxy = 0.0
    k00 = k01 = k10 = k11 = 0.0
    for sp, pp in zip(survey_points, path_points):
        sx = (sp[0] - survey_anchor[0]) - survey_delta_mean[0]
        sy = (sp[1] - survey_anchor[1]) - survey_delta_mean[1]
        px = (pp[0] - path_anchor[0]) - path_delta_mean[0]
        py = (pp[1] - path_anchor[1]) - path_delta_mean[1]
        sxx += sx * sx
        syy += sy * sy
        sxy += sx * sy
        pxx += px * px
        pyy += py * py
        pxy += px * py
        k00 += sx * px
        k01 += sx * py
        k10 += sy * px
        k11 += sy * py

    survey_var = sxx + syy
    path_var = pxx + pyy
    det_survey = sxx * syy - sxy * sxy
    det_path = pxx * pyy - pxy * pxy
    det_cov = k00 * k11 - k01 * k10

    # 只有两侧都能确定二维方向时，镜像才在数学上可判定。
    survey_rank2 = abs(det_survey) > 1e-12 * survey_var * survey_var
    path_rank2 = abs(det_path) > 1e-12 * path_var * path_var
    mirror_scale = max(1.0, survey_var * path_var)
    if survey_rank2 and path_rank2 and det_cov < -1e-10 * mirror_scale:
        raise CalibrationError(
            "控制点对应关系包含镜像；标定只允许旋转和平移，禁止缩放或镜像",
            ("survey_points",),
        )

    # max Tr(RK), R=[[cos,-sin],[sin,cos]]:
    # Tr(RK)=cos*(K00+K11)+sin*(K01-K10)。
    a = k00 + k11
    b = k01 - k10
    norm = math.hypot(a, b)
    cos_t = 1.0 if norm == 0.0 else a / norm
    sin_t = 0.0 if norm == 0.0 else b / norm
    rotation: Tuple[Tuple[float, float], Tuple[float, float]] = (
        (cos_t, -sin_t),
        (sin_t, cos_t),
    )

    # t = p0 - R*s0 + mean(δp - R*δs)。残差也只使用相对首点的小向量计算。
    rds0 = rotation[0][0] * survey_delta_mean[0] + rotation[0][1] * survey_delta_mean[1]
    rds1 = rotation[1][0] * survey_delta_mean[0] + rotation[1][1] * survey_delta_mean[1]
    correction = (
        path_delta_mean[0] - rds0,
        path_delta_mean[1] - rds1,
    )
    tx = path_anchor[0] - (
        rotation[0][0] * survey_anchor[0] + rotation[0][1] * survey_anchor[1]
    ) + correction[0]
    ty = path_anchor[1] - (
        rotation[1][0] * survey_anchor[0] + rotation[1][1] * survey_anchor[1]
    ) + correction[1]

    # 残差只使用相对首点的小向量：在任意巨大绝对坐标系下都与绝对坐标
    # 表达式 (R*s+t)-p 等价，但避免 1e15 量级的平移项参与减法。
    residuals: list[float] = []
    for sp, pp in zip(survey_points, path_points):
        dsx = sp[0] - survey_anchor[0]
        dsy = sp[1] - survey_anchor[1]
        dpx = pp[0] - path_anchor[0]
        dpy = pp[1] - path_anchor[1]
        ex = rotation[0][0] * dsx + rotation[0][1] * dsy - rds0 + path_delta_mean[0] - dpx
        ey = rotation[1][0] * dsx + rotation[1][1] * dsy - rds1 + path_delta_mean[1] - dpy
        residuals.append(math.hypot(ex, ey))

    rms_error = math.sqrt(math.fsum(r * r for r in residuals) / n)
    if not math.isfinite(rms_error) or rms_error > max_rms_error:
        raise CalibrationError(
            f"标定残差 RMS {rms_error:.12g} mm 超过允许上限 "
            f"{max_rms_error:.12g} mm",
            ("max_rms_error",),
        )

    return RigidTransform2D(
        rotation=rotation,
        translation=(tx, ty),
        rms_error=rms_error,
        residuals=tuple(residuals),
        survey_anchor=survey_anchor,
        path_anchor=path_anchor,
        translation_correction=correction,
    )
