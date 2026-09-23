"""标定刚体变换测试：以独立写出的二维矩阵计算核对结果。"""

import math

import pytest

from app.calibration import CalibrationError, fit_rigid_transform_2d


def independent_fit(survey, path):
    """测试内独立实现：中心化 2x2 协方差后闭式求二维 proper rotation。"""
    n = len(survey)
    smx = sum(x for x, _ in survey) / n
    smy = sum(y for _, y in survey) / n
    pmx = sum(x for x, _ in path) / n
    pmy = sum(y for _, y in path) / n

    a = b = 0.0
    for (sx, sy), (px, py) in zip(survey, path):
        sx -= smx
        sy -= smy
        px -= pmx
        py -= pmy
        a += sx * px + sy * py
        b += sx * py - sy * px

    norm = math.hypot(a, b)
    c = a / norm
    s = b / norm
    rotation = ((c, -s), (s, c))
    tx = pmx - (rotation[0][0] * smx + rotation[0][1] * smy)
    ty = pmy - (rotation[1][0] * smx + rotation[1][1] * smy)
    residuals = [
        math.hypot(
            rotation[0][0] * sx + rotation[0][1] * sy + tx - px,
            rotation[1][0] * sx + rotation[1][1] * sy + ty - py,
        )
        for (sx, sy), (px, py) in zip(survey, path)
    ]
    rms = math.sqrt(sum(r * r for r in residuals) / n)
    return rotation, (tx, ty), rms, residuals


def assert_proper_rotation(r):
    c, s = r[0][0], r[0][1]
    assert math.isclose(r[1][0], -r[0][1], abs_tol=1e-14)
    assert math.isclose(r[1][1], r[0][0], abs_tol=1e-14)
    assert math.isclose(c * c + s * s, 1.0, abs_tol=1e-14)
    assert math.isclose(c * c - (-s) * s, 1.0, abs_tol=1e-14)


def assert_matrix_close(got, expected, abs_tol):
    for i in range(2):
        for j in range(2):
            assert math.isclose(got[i][j], expected[i][j], abs_tol=abs_tol)


def test_pure_translation_matches_independent_matrix_calculation():
    survey = [(0.0, 0.0), (2.0, 0.0), (0.0, 3.0), (5.0, -1.0)]
    path = [(x + 1234.5, y - 67.25) for x, y in survey]
    expected_r, expected_t, expected_rms, expected_residuals = independent_fit(survey, path)

    got = fit_rigid_transform_2d(survey, path, 1e-9)
    assert_proper_rotation(got.rotation)
    assert_matrix_close(got.rotation, expected_r, 1e-14)
    assert got.translation == pytest.approx(expected_t, abs=1e-12)
    assert got.translation == pytest.approx((1234.5, -67.25), abs=1e-11)
    assert got.rms_error == pytest.approx(expected_rms, abs=1e-12)
    assert got.residuals == pytest.approx(expected_residuals, abs=1e-12)


def test_ninety_degree_rotation_and_translation():
    survey = [(0, 0), (1, 0), (0, 1), (2, 3)]
    # CCW 90°: (x,y) -> (-y,x)，再平移。
    path = [(-y + 100, x - 200) for x, y in survey]
    expected_r, expected_t, _, _ = independent_fit(survey, path)

    got = fit_rigid_transform_2d(survey, path, 1e-9)
    assert_matrix_close(got.rotation, expected_r, 1e-14)
    assert_matrix_close(got.rotation, ((0.0, -1.0), (1.0, 0.0)), 1e-14)
    assert got.translation == pytest.approx((100.0, -200.0), abs=1e-12)
    assert got.rms_error == pytest.approx(0.0, abs=1e-13)
    assert got.apply((10, -4)) == pytest.approx((104.0, -190.0), abs=1e-11)


def test_light_noise_returns_least_squares_result():
    survey = [(0, 0), (10, 0), (10, 10), (0, 10), (5, 12)]
    path = [(x + 7, y - 3) for x, y in survey]
    noisy_path = [
        (path[0][0] + 0.002, path[0][1] - 0.001),
        (path[1][0] - 0.001, path[1][1] + 0.002),
        (path[2][0] + 0.001, path[2][1] + 0.001),
        (path[3][0] - 0.002, path[3][1]),
        (path[4][0], path[4][1] - 0.002),
    ]
    expected_r, expected_t, expected_rms, expected_residuals = independent_fit(
        survey, noisy_path
    )

    got = fit_rigid_transform_2d(survey, noisy_path, 0.01)
    assert_proper_rotation(got.rotation)
    assert_matrix_close(got.rotation, expected_r, 1e-13)
    assert got.translation == pytest.approx(expected_t, abs=1e-12)
    assert got.rms_error == pytest.approx(expected_rms, abs=1e-13)
    assert got.rms_error < 0.01
    assert got.residuals == pytest.approx(expected_residuals, abs=1e-13)


def test_residual_over_threshold_is_rejected_without_geometry_side_effect():
    survey = [(0, 0), (10, 0), (10, 10)]
    path = [(0, 0), (9, 0), (10, 10)]
    expected = independent_fit(survey, path)
    with pytest.raises(CalibrationError) as info:
        fit_rigid_transform_2d(survey, path, 0.1)
    assert info.value.loc == ("max_rms_error",)
    assert expected[2] > 0.1


def test_survey_or_path_all_coincident_is_degenerate():
    survey = [(1.0, 2.0), (1.0, 2.0), (1.0, 2.0)]
    path = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]
    with pytest.raises(CalibrationError) as info:
        fit_rigid_transform_2d(survey, path, 1.0)
    assert info.value.loc == ("survey_points",)

    with pytest.raises(CalibrationError) as info:
        fit_rigid_transform_2d(path, survey, 1.0)
    assert info.value.loc == ("path_points",)


def test_non_collinear_mirror_correspondence_is_rejected():
    survey = [(0, 0), (1, 0), (0, 1), (2, 3)]
    mirrored = [(x, -y) for x, y in survey]
    with pytest.raises(CalibrationError) as info:
        fit_rigid_transform_2d(survey, mirrored, 100.0)
    assert info.value.loc == ("survey_points",)
    assert "镜像" in str(info.value)


def test_large_coordinates_remain_stable_in_relative_transform():
    base = 1e15
    survey = [(base, base), (base + 1, base), (base, base + 1), (base + 4, base - 2)]
    path = [(2 * base, 3 * base), (2 * base + 1, 3 * base),
            (2 * base, 3 * base + 1), (2 * base + 4, 3 * base - 2)]
    got = fit_rigid_transform_2d(survey, path, 1e-9)
    assert got.translation == pytest.approx((base, 2 * base), rel=1e-15, abs=1e-9)
    assert got.rms_error == 0.0
    assert got.apply((base + 10, base + 20)) == pytest.approx(
        (2 * base + 10, 3 * base + 20), abs=1e-9
    )
