-- Seed Location Service (location_service)
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
    )
VALUES (
        '01HNKX6R6J5S6W66W6W6W6W6W1',
        'LOC_IST_001',
        'Istanbul Warehouse',
        'Istanbul Warehouse',
        'ISTANBUL WAREHOUSE',
        'ISTANBUL WAREHOUSE',
        41.008200,
        28.978400,
        true,
        1,
        now(),
        now()
    ),
    (
        '01HNKX6R6J5S6W66W6W6W6W6W2',
        'LOC_ANK_001',
        'Ankara Depot',
        'Ankara Depot',
        'ANKARA DEPOT',
        'ANKARA DEPOT',
        39.933400,
        32.859700,
        true,
        1,
        now(),
        now()
    ) ON CONFLICT (location_id) DO NOTHING;
INSERT INTO route_pairs (
        route_pair_id,
        pair_code,
        origin_location_id,
        destination_location_id,
        profile_code,
        pair_status,
        row_version,
        created_at_utc,
        updated_at_utc
    )
VALUES (
        '01HNKX6R6J5S6W66W6W6W6W6W3',
        'RP_01HNKX6R6J5S6W66W6W6W6W6W3',
        '01HNKX6R6J5S6W66W6W6W6W6W1',
        '01HNKX6R6J5S6W66W6W6W6W6W2',
        'TIR',
        'ACTIVE',
        1,
        now(),
        now()
    ) ON CONFLICT (route_pair_id) DO NOTHING;
-- Seed Driver Service (driver_service)
INSERT INTO driver_drivers (
        driver_id,
        full_name,
        full_name_search_key,
        company_driver_code,
        phone_e164,
        phone_normalization_status,
        license_class,
        employment_start_date,
        status,
        row_version,
        created_by_actor_id,
        updated_by_actor_id,
        created_at_utc,
        updated_at_utc
    )
VALUES (
        '01HNKX6R6J5S6W66W6W6W6W6D1',
        'John Doe',
        'JOHN DOE',
        'D-1001',
        '+905550001122',
        'NORMALIZED',
        'CE',
        '2024-01-01',
        'ACTIVE',
        1,
        'system',
        'system',
        now(),
        now()
    ) ON CONFLICT (driver_id) DO NOTHING;
-- Seed Fleet Service (fleet_service)
INSERT INTO fleet_vehicles (
        vehicle_id,
        asset_code,
        plate_raw_current,
        normalized_plate_current,
        ownership_type,
        status,
        row_version,
        spec_stream_version,
        created_by_actor_type,
        created_by_actor_id,
        updated_by_actor_type,
        updated_by_actor_id,
        created_at_utc,
        updated_at_utc
    )
VALUES (
        '01HNKX6R6J5S6W66W6W6W6V1',
        'V-34-AAA-01',
        '34 AAA 01',
        '34AAA01',
        'OWNED',
        'ACTIVE',
        1,
        0,
        'SYSTEM',
        'system',
        'SYSTEM',
        'system',
        now(),
        now()
    ) ON CONFLICT (vehicle_id) DO NOTHING;
INSERT INTO fleet_trailers (
        trailer_id,
        asset_code,
        plate_raw_current,
        normalized_plate_current,
        ownership_type,
        status,
        row_version,
        spec_stream_version,
        created_by_actor_type,
        created_by_actor_id,
        updated_by_actor_type,
        updated_by_actor_id,
        created_at_utc,
        updated_at_utc
    )
VALUES (
        '01HNKX6R6J5S6W66W6W6W6T1',
        'T-34-BBB-01',
        '34 BBB 01',
        '34BBB01',
        'OWNED',
        'ACTIVE',
        1,
        0,
        'SYSTEM',
        'system',
        'SYSTEM',
        'system',
        now(),
        now()
    ) ON CONFLICT (trailer_id) DO NOTHING;