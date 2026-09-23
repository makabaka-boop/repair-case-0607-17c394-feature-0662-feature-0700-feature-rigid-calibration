"""/api/precheck 接口测试：穿越/相切/圈内段、排序、三位小数展示与全部字段错误。"""

import math

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

PATH = "/api/precheck"


def post(body):
    return client.post(PATH, json=body)


def base_body(**over):
    body = {
        "nodes": [{"x": 0, "y": 0}, {"x": 100, "y": 0}],
        "cable_radius": 5,
        "circles": [],
    }
    body.update(over)
    return body


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_feasible_route():
    r = post(base_body(circles=[{"x": 50, "y": 30, "radius": 10}]))
    assert r.status_code == 200
    data = r.json()
    assert data["feasible"] is True
    assert data["collision_count"] == 0
    assert data["first_collision"] is None
    assert data["collisions"] == []


def test_crossing_returns_nearest_and_expanded():
    r = post(base_body(circles=[{"x": 50, "y": 0, "radius": 10}]))
    data = r.json()
    assert r.status_code == 200
    assert data["feasible"] is False
    assert data["collision_count"] == 1
    first = data["first_collision"]
    assert first["segment_index"] == 0
    assert first["circle_index"] == 0
    assert first["nearest"] == {"x": 50.0, "y": 0.0}
    assert first["distance"] == 0.0
    assert first["expanded_radius"] == 15.0
    # 圆与扩张圈都在响应中，供前端绘制
    assert data["circles"][0]["expanded_radius"] == 15.0


def test_tangent_is_collision():
    """相切（距离恰等于扩张半径）必须判碰撞。"""
    r = post(base_body(circles=[{"x": 50, "y": 15, "radius": 10}]))
    data = r.json()
    assert data["feasible"] is False
    assert data["collisions"][0]["distance"] == 15.0
    assert data["collisions"][0]["nearest"] == {"x": 50.0, "y": 0.0}


def test_response_sorted_by_segment_then_circle():
    body = base_body(
        nodes=[{"x": 0, "y": 0}, {"x": 10, "y": 0}, {"x": 10, "y": 10}],
        cable_radius=2,
        circles=[
            {"x": 10, "y": 15, "radius": 3},  # seg1/c0
            {"x": 5, "y": 0, "radius": 1},    # seg0/c1
            {"x": 10, "y": 5, "radius": 1},   # seg1/c2
        ],
    )
    data = post(body).json()
    order = [(c["segment_index"], c["circle_index"]) for c in data["collisions"]]
    assert order == [(0, 1), (1, 0), (1, 2)]
    # first_collision 与升序列表首项一致
    first = data["first_collision"]
    assert (first["segment_index"], first["circle_index"]) == (0, 1)


def test_endpoint_clamped_nearest():
    body = base_body(
        nodes=[{"x": 0, "y": 0}, {"x": 30, "y": 0}],
        circles=[{"x": 40, "y": 0, "radius": 10}],
        cable_radius=5,
    )
    c = post(body).json()["collisions"][0]
    assert c["nearest"] == {"x": 30.0, "y": 0.0}
    assert c["distance"] == 10.0


def test_segment_entirely_inside_circle():
    body = base_body(
        nodes=[{"x": 0, "y": 0}, {"x": 10, "y": 10}],
        circles=[{"x": -50, "y": -50, "radius": 100}],
        cable_radius=5,
    )
    data = post(body).json()
    assert data["collision_count"] == 1
    qx, qy = data["collisions"][0]["nearest"].values()
    assert 0.0 <= qx <= 10.0 and math.isclose(qx, qy)


def test_display_coordinates_rounded_to_three_decimals():
    # 斜线段垂足产生多位小数，输出只展示三位，内部仍双精度判定。
    body = base_body(
        nodes=[{"x": 0, "y": 0}, {"x": 3, "y": 1}],
        circles=[{"x": 1, "y": 1, "radius": 1}],
        cable_radius=1,
    )
    c = post(body).json()["collisions"][0]
    # 垂足 (1.2, 0.4)；距 hypot(0.2,0.6)=0.632455... <= 2
    assert c["nearest"]["x"] == 1.2
    assert c["nearest"]["y"] == 0.4
    assert c["distance"] == 0.632
    assert len(str(c["distance"]).split(".")[1]) <= 3


def test_near_miss_not_changed_by_three_decimal_display():
    body = base_body(
        nodes=[{"x": 0, "y": 0}, {"x": 1, "y": 0}],
        cable_radius=5,
        circles=[{"x": 3, "y": 10, "radius": 5.1978}],
    )
    data = post(body).json()
    assert data["feasible"] is True
    assert data["collision_count"] == 0
    assert data["first_collision"] is None
    assert data["collisions"] == []


def test_shared_endpoint_returns_collision_for_each_segment():
    body = base_body(
        nodes=[{"x": -10, "y": 0}, {"x": 0, "y": 0}, {"x": 0, "y": 10}],
        cable_radius=1,
        circles=[{"x": 1, "y": -1, "radius": 0.5}],
    )
    data = post(body).json()
    assert data["collision_count"] == 2
    order = [
        (c["segment_index"], c["circle_index"])
        for c in data["collisions"]
    ]
    assert order == [(0, 0), (1, 0)]
    assert (
        data["first_collision"]["segment_index"],
        data["first_collision"]["circle_index"],
    ) == (0, 0)
    assert data["first_collision"]["nearest"] == {"x": 0.0, "y": 0.0}


def test_first_collision_follows_order_not_intrusion_depth():
    body = base_body(
        nodes=[{"x": 0, "y": 0}, {"x": 10, "y": 0}, {"x": 20, "y": 0}],
        cable_radius=1,
        circles=[
            {"x": 5, "y": 2, "radius": 1.1},
            {"x": 15, "y": 0, "radius": 1},
        ],
    )
    data = post(body).json()
    assert data["collision_count"] == 2
    assert [
        (c["segment_index"], c["circle_index"])
        for c in data["collisions"]
    ] == [(0, 0), (1, 1)]
    first = data["first_collision"]
    assert (first["segment_index"], first["circle_index"]) == (0, 0)
    assert first["distance"] == 2.0
    assert first["expanded_radius"] == 2.1


# ---------- 字段级错误：整次预检失败且不产生结论 ----------

def assert_field_error(body, field_fragment):
    r = post(body)
    assert r.status_code == 422, r.text
    data = r.json()
    assert data["ok"] is False
    assert "errors" in data and data["errors"]
    assert any(field_fragment in k for k in data["errors"]), data["errors"]
    # 错误响应不含任何旧结论字段
    assert "feasible" not in data and "collisions" not in data


def test_error_non_finite_coordinate_nan_and_infinity():
    body = base_body(nodes=[{"x": 0, "y": 0}, {"x": "NaN", "y": 0}])
    assert_field_error(body, "nodes[1].x")
    body = base_body(nodes=[{"x": 0, "y": 0}, {"x": "Infinity", "y": 0}])
    assert_field_error(body, "nodes[1].x")
    body = base_body(nodes=[{"x": 0, "y": 0}, {"x": "-Infinity", "y": 0}])
    assert_field_error(body, "nodes[1].x")


def test_error_non_finite_radii():
    body = base_body(circles=[{"x": 0, "y": 0, "radius": "NaN"}])
    assert_field_error(body, "circles[0].radius")
    body = base_body(cable_radius="Infinity")
    assert_field_error(body, "cable_radius")


def test_error_too_few_nodes():
    body = base_body(nodes=[{"x": 0, "y": 0}])
    assert_field_error(body, "nodes")


def test_error_non_integer_millimeter_coordinate():
    body = base_body(nodes=[{"x": 0, "y": 0}, {"x": 12.5, "y": 0}])
    assert_field_error(body, "nodes[1].x")


def test_error_non_positive_radii():
    body = base_body(cable_radius=0)
    assert_field_error(body, "cable_radius")
    body = base_body(cable_radius=-3)
    assert_field_error(body, "cable_radius")
    body = base_body(circles=[{"x": 1, "y": 1, "radius": 0}])
    assert_field_error(body, "circles[0].radius")
    body = base_body(circles=[{"x": 1, "y": 1, "radius": -2}])
    assert_field_error(body, "circles[0].radius")


def test_error_adjacent_duplicate_nodes_is_field_level():
    body = base_body(nodes=[{"x": 5, "y": 5}, {"x": 5, "y": 5}])
    assert_field_error(body, "nodes")


def test_error_boolean_rejected():
    body = base_body(cable_radius=True)
    assert_field_error(body, "cable_radius")


def test_error_wrong_type_string():
    body = base_body(nodes=[{"x": "a", "y": 0}, {"x": 1, "y": 0}])
    assert_field_error(body, "nodes[0].x")




# ---------- 可选坐标标定：survey 圆心 -> path 局部坐标 ----------


def test_error_unknown_field_rejected():
    body = base_body()
    body["nope"] = 1
    assert_field_error(body, "nope")


def calibration_body(**calibration_over):
    calibration = {
        "survey_points": [
            {"x": 1000.0, "y": 2000.0},
            {"x": 1001.0, "y": 2000.0},
            {"x": 1000.0, "y": 2001.0},
        ],
        "path_points": [
            {"x": 10.0, "y": 20.0},
            {"x": 11.0, "y": 20.0},
            {"x": 10.0, "y": 21.0},
        ],
        "max_rms_error": 0.01,
    }
    calibration.update(calibration_over)
    return calibration


def test_request_without_calibration_omits_calibration_response_field():
    r = post(base_body())
    assert r.status_code == 200
    data = r.json()
    assert "calibration" not in data


def test_calibration_pure_translation_moves_only_circle_centers_for_tangent():
    body = base_body(
        nodes=[{"x": 0, "y": 0}, {"x": 100, "y": 0}],
        cable_radius=5,
        circles=[{"x": 1050, "y": 1995, "radius": 10}],
        calibration=calibration_body(),
    )
    r = post(body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feasible"] is False
    assert data["circles"][0]["center"] == {"x": 60.0, "y": 15.0}
    assert data["circles"][0]["radius"] == 10.0
    assert data["circles"][0]["expanded_radius"] == 15.0
    collision = data["collisions"][0]
    assert collision["circle_center"] == {"x": 60.0, "y": 15.0}
    assert collision["nearest"] == {"x": 60.0, "y": 0.0}
    assert collision["distance"] == 15.0

    calibration = data["calibration"]
    assert calibration["rotation"] == [[1.0, 0.0], [0.0, 1.0]]
    assert calibration["translation"] == {"x": -990.0, "y": -1980.0}
    assert calibration["rms_error"] == pytest.approx(0.0, abs=1e-12)
    assert calibration["max_rms_error"] == 0.01
    assert len(calibration["point_residuals"]) == 3


def test_calibrated_geometry_keeps_path_nodes_and_cable_radius_semantics():
    # survey 中心 (1050,2015) 变换到局部 (60,35)，距路径 35；不碰撞。
    body = base_body(
        nodes=[{"x": 0, "y": 0}, {"x": 100, "y": 0}],
        cable_radius=5,
        circles=[{"x": 1050, "y": 2015, "radius": 10}],
        calibration=calibration_body(),
    )
    data = post(body).json()
    assert data["feasible"] is True
    assert data["nodes"] == [{"x": 0.0, "y": 0.0}, {"x": 100.0, "y": 0.0}]
    assert data["cable_radius"] == 5.0
    assert data["circles"][0]["radius"] == 10.0
    assert data["circles"][0]["expanded_radius"] == 15.0

    # survey Y 减 20 后变换到局部 (60,15)：半径 10 + 电缆 5 恰相切。
    tangent_body = dict(body)
    tangent_body["circles"] = [{"x": 1050, "y": 1995, "radius": 10}]
    tangent = post(tangent_body).json()
    assert tangent["feasible"] is False
    assert tangent["circles"][0]["center"] == {"x": 60.0, "y": 15.0}
    assert tangent["collisions"][0]["nearest"] == {"x": 60.0, "y": 0.0}
    assert tangent["collisions"][0]["distance"] == 15.0


def test_calibration_ninety_degree_rotation_and_transformed_compound_intrusion():
    # 局部：路径 (0,0)->(100,0)->(100,100)；survey 由局部点顺时针 90° +
    # 平移得到，因此反向标定为逆时针 90°。
    local_points = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    survey_points = [{"x": 1000.0 - y, "y": 2000.0 + x} for x, y in local_points]
    path_points = [{"x": x, "y": y} for x, y in local_points]

    def survey_circle(local_x, local_y):
        return {
            "x": 1000 - local_y,
            "y": 2000 + local_x,
            "radius": 9,
        }

    body = {
        "nodes": [{"x": 0, "y": 0}, {"x": 100, "y": 0}, {"x": 100, "y": 100}],
        "cable_radius": 1,
        "circles": [survey_circle(20, 0), survey_circle(30, 0)],
        "calibration": {
            "survey_points": survey_points,
            "path_points": path_points,
            "max_rms_error": 1e-9,
        },
    }
    response = post(body)
    data = response.json()
    assert response.status_code == 200, data
    rotation = data["calibration"]["rotation"]
    assert rotation[0][0] == pytest.approx(0.0, abs=1e-12)
    assert rotation[0][1] == pytest.approx(1.0, abs=1e-12)
    assert rotation[1][0] == pytest.approx(-1.0, abs=1e-12)
    assert rotation[1][1] == pytest.approx(0.0, abs=1e-12)
    assert data["circles"][0]["center"] == {"x": 20.0, "y": 0.0}
    assert data["circles"][1]["center"] == {"x": 30.0, "y": 0.0}
    compounds = data["compound_intrusion_segments"]
    assert len(compounds) == 1
    assert compounds[0]["circle_indices"] == [0, 1]
    assert compounds[0]["start"] == {"x": 20.0, "y": 0.0}
    assert compounds[0]["end"] == {"x": 30.0, "y": 0.0}
    assert compounds[0]["pieces"][0]["entry"] == {"x": 20.0, "y": 0.0}
    assert compounds[0]["pieces"][0]["exit"] == {"x": 30.0, "y": 0.0}


def test_calibration_residual_over_threshold_returns_422_and_no_results():
    bad = calibration_body(
        survey_points=[
            {"x": 0.0, "y": 0.0},
            {"x": 10.0, "y": 0.0},
            {"x": 10.0, "y": 10.0},
        ],
        path_points=[
            {"x": 0.0, "y": 0.0},
            {"x": 9.0, "y": 0.0},
            {"x": 10.0, "y": 10.0},
        ],
        max_rms_error=0.001,
    )
    r = post(base_body(calibration=bad))
    assert r.status_code == 422
    data = r.json()
    assert data["ok"] is False
    assert "calibration.max_rms_error" in data["errors"]
    assert "collisions" not in data and "compound_intrusion_segments" not in data


def test_calibration_degenerate_survey_points_return_field_locator():
    bad = calibration_body(
        survey_points=[
            {"x": 1.0, "y": 1.0},
            {"x": 1.0, "y": 1.0},
            {"x": 1.0, "y": 1.0},
        ]
    )
    r = post(base_body(calibration=bad))
    assert r.status_code == 422
    assert "calibration.survey_points" in r.json()["errors"]


def test_calibration_degenerate_path_points_return_field_locator():
    bad = calibration_body(
        path_points=[
            {"x": 1.0, "y": 1.0},
            {"x": 1.0, "y": 1.0},
            {"x": 1.0, "y": 1.0},
        ]
    )
    r = post(base_body(calibration=bad))
    assert r.status_code == 422
    assert "calibration.path_points" in r.json()["errors"]


def test_calibration_non_collinear_mirror_returns_field_locator():
    bad = calibration_body(
        survey_points=[
            {"x": 0.0, "y": 0.0},
            {"x": 1.0, "y": 0.0},
            {"x": 0.0, "y": 1.0},
        ],
        path_points=[
            {"x": 0.0, "y": 0.0},
            {"x": 1.0, "y": 0.0},
            {"x": 0.0, "y": -1.0},
        ],
        max_rms_error=100.0,
    )
    r = post(base_body(calibration=bad))
    assert r.status_code == 422
    assert "calibration.survey_points" in r.json()["errors"]


def test_calibration_unequal_point_arrays_return_path_points_locator():
    bad = calibration_body(
        path_points=[
            {"x": 0.0, "y": 0.0},
            {"x": 1.0, "y": 0.0},
        ]
    )
    r = post(base_body(calibration=bad))
    assert r.status_code == 422
    assert "calibration.path_points" in r.json()["errors"]


def test_calibration_length_count_and_finiteness_errors_are_field_located():
    bad = calibration_body(
        survey_points=[{"x": 0.0, "y": 0.0}],
        path_points=[{"x": 0.0, "y": 0.0}],
    )
    r = post(base_body(calibration=bad))
    assert r.status_code == 422
    assert "calibration.survey_points" in r.json()["errors"]

    bad = calibration_body(max_rms_error=0)
    assert "calibration.max_rms_error" in post(base_body(calibration=bad)).json()["errors"]

    bad = calibration_body(
        survey_points=[
            {"x": "NaN", "y": 0.0},
            {"x": 1.0, "y": 0.0},
            {"x": 0.0, "y": 1.0},
        ]
    )
    r = post(base_body(calibration=bad))
    assert r.status_code == 422
    assert "calibration.survey_points[0].x" in r.json()["errors"]
