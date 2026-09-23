export interface Point {
  x: number;
  y: number;
}

export interface Collision {
  segment_index: number;
  circle_index: number;
  nearest: Point;
  distance: number;
  expanded_radius: number;
  circle_center: Point;
  circle_radius: number;
  cable_radius: number;
}

export interface CircleView {
  center: Point;
  radius: number;
  expanded_radius: number;
}

export interface IntervalPiece {
  segment_index: number;
  circle_index: number;
  entry: Point;
  exit: Point;
  start_mileage: number;
  end_mileage: number;
  length: number;
}

export interface IntrusionInterval {
  circle_index: number;
  entry_segment_index: number;
  exit_segment_index: number;
  entry: Point;
  exit: Point;
  start_mileage: number;
  end_mileage: number;
  length: number;
  pieces: IntervalPiece[];
}

export interface CompoundPiece {
  segment_index: number;
  circle_indices: number[];
  entry: Point;
  exit: Point;
  start_mileage: number;
  end_mileage: number;
  length: number;
}

export interface CompoundIntrusionSegment {
  circle_indices: number[];
  start_mileage: number;
  end_mileage: number;
  start: Point;
  end: Point;
  start_inclusive: boolean;
  end_inclusive: boolean;
  length: number;
  pieces: CompoundPiece[];
}

export type RotationMatrix = [[number, number], [number, number]];

export interface CalibrationPointResidual {
  index: number;
  survey_point: Point;
  path_point: Point;
  residual: number;
}

export interface CalibrationResult {
  rotation: RotationMatrix;
  translation: Point;
  rms_error: number;
  max_rms_error: number;
  point_residuals: CalibrationPointResidual[];
}

export interface PrecheckResponse {
  feasible: boolean;
  cable_radius: number;
  nodes: Point[];
  circles: CircleView[];
  collision_count: number;
  first_collision: Collision | null;
  collisions: Collision[];
  intrusion_intervals: IntrusionInterval[];
  compound_intrusion_segments: CompoundIntrusionSegment[];
  calibration?: CalibrationResult;
}

export interface CalibrationPayload {
  survey_points: Point[];
  path_points: Point[];
  max_rms_error: number;
}

export interface PrecheckPayload {
  nodes: Point[];
  cable_radius: number;
  circles: Array<Point & { radius: number }>;
  calibration?: CalibrationPayload;
}

export type FieldErrors = Record<string, string>;
