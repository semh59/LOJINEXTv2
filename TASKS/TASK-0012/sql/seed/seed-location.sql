\connect location_service

-- Seed minimal points, pair, routes, and active route versions for trip-context resolution.

INSERT INTO location_points (
    location_id,
    code,
    name_tr,
    name_en,
    normalized_name_tr,
    normalized_name_en,
    latitude_6dp,
    longitude_6dp,
    is_active,
    row_version,
    created_at_utc,
    updated_at_utc
) VALUES
    ('11111111-1111-1111-1111-111111111111', 'TR_IST', 'Istanbul', 'Istanbul', 'ISTANBUL', 'ISTANBUL', 41.008211, 28.978400, true, 1, now(), now()),
    ('22222222-2222-2222-2222-222222222222', 'TR_ANK', 'Ankara', 'Ankara', 'ANKARA', 'ANKARA', 39.933365, 32.859741, true, 1, now(), now())
ON CONFLICT (location_id) DO NOTHING;

INSERT INTO route_pairs (
    route_pair_id,
    pair_code,
    origin_location_id,
    destination_location_id,
    profile_code,
    pair_status,
    forward_route_id,
    reverse_route_id,
    current_active_forward_version_no,
    current_active_reverse_version_no,
    pending_forward_version_no,
    pending_reverse_version_no,
    row_version,
    created_at_utc,
    updated_at_utc
) VALUES (
    '33333333-3333-3333-3333-333333333333',
    'RP_01HV4J0T6PZ7VQ2NQ2NQ2NQ2NQ',
    '11111111-1111-1111-1111-111111111111',
    '22222222-2222-2222-2222-222222222222',
    'TIR',
    'ACTIVE',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    1,
    now(),
    now()
) ON CONFLICT (route_pair_id) DO NOTHING;

INSERT INTO routes (
    route_id,
    route_pair_id,
    route_code,
    direction,
    created_by,
    created_at_utc
) VALUES
    ('44444444-4444-4444-4444-444444444444', '33333333-3333-3333-3333-333333333333', 'R_FWD_01', 'FORWARD', 'smoke', now()),
    ('55555555-5555-5555-5555-555555555555', '33333333-3333-3333-3333-333333333333', 'R_REV_01', 'REVERSE', 'smoke', now())
ON CONFLICT (route_id) DO NOTHING;

UPDATE route_pairs
SET forward_route_id = '44444444-4444-4444-4444-444444444444',
    reverse_route_id = '55555555-5555-5555-5555-555555555555',
    current_active_forward_version_no = 1,
    current_active_reverse_version_no = 1,
    updated_at_utc = now()
WHERE route_pair_id = '33333333-3333-3333-3333-333333333333';

INSERT INTO route_versions (
    route_id,
    version_no,
    processing_run_id,
    processing_status,
    total_distance_m,
    total_duration_s,
    total_ascent_m,
    total_descent_m,
    avg_grade_pct,
    max_grade_pct,
    steepest_downhill_pct,
    known_speed_limit_ratio,
    segment_count,
    validation_result,
    distance_validation_delta_pct,
    duration_validation_delta_pct,
    endpoint_validation_delta_m,
    field_origin_matrix_json,
    field_origin_matrix_hash,
    road_type_distribution_json,
    speed_limit_distribution_json,
    urban_distribution_json,
    warnings_json,
    refresh_reason,
    processing_algorithm_version,
    created_at_utc,
    activated_at_utc
) VALUES
    (
        '44444444-4444-4444-4444-444444444444',
        1,
        NULL,
        'ACTIVE',
        100000.0,
        3600,
        0,
        0,
        0,
        0,
        0,
        1.0,
        1,
        'PASS',
        0,
        0,
        0,
        '{}'::jsonb,
        '0000000000000000000000000000000000000000000000000000000000000000',
        '{}'::jsonb,
        '{}'::jsonb,
        '{}'::jsonb,
        '[]'::jsonb,
        NULL,
        'smoke',
        now(),
        now()
    ),
    (
        '55555555-5555-5555-5555-555555555555',
        1,
        NULL,
        'ACTIVE',
        100000.0,
        3600,
        0,
        0,
        0,
        0,
        0,
        1.0,
        1,
        'PASS',
        0,
        0,
        0,
        '{}'::jsonb,
        '0000000000000000000000000000000000000000000000000000000000000000',
        '{}'::jsonb,
        '{}'::jsonb,
        '{}'::jsonb,
        '[]'::jsonb,
        NULL,
        'smoke',
        now(),
        now()
    )
ON CONFLICT (route_id, version_no) DO NOTHING;

