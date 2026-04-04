from fleet_service.domain.etag import (
    generate_master_etag,
    generate_spec_etag,
    parse_master_etag,
    parse_spec_etag,
)


def test_master_etag_generation():
    asset_id = "01H1234567890ABCDEFGHJKMNP"
    etag = generate_master_etag("VEHICLE", asset_id, 5)
    assert etag == f'W/"vehicle-{asset_id}-v5"'

    etag = generate_master_etag("TRAILER", asset_id, 1)
    assert etag == f'W/"trailer-{asset_id}-v1"'


def test_spec_etag_generation():
    asset_id = "01H1234567890ABCDEFGHJKMNP"
    etag = generate_spec_etag("VEHICLE", asset_id, 3)
    assert etag == f'W/"vehicle-{asset_id}-sv3"'

    etag = generate_spec_etag("TRAILER", asset_id, 0)
    assert etag == f'W/"trailer-{asset_id}-sv0"'


def test_parse_master_etag():
    asset_id = "01H1234567890ABCDEFGHJKMNP"
    header = f'W/"vehicle-{asset_id}-v12"'
    asset_type, aid, version = parse_master_etag(header)
    assert asset_type == "VEHICLE"
    assert aid == asset_id
    assert version == 12


def test_parse_spec_etag():
    asset_id = "01H1234567890ABCDEFGHJKMNP"
    header = f'W/"trailer-{asset_id}-sv7"'
    asset_type, aid, version = parse_spec_etag(header)
    assert asset_type == "TRAILER"
    assert aid == asset_id
    assert version == 7


def test_parse_invalid_etags():
    assert parse_master_etag("invalid") is None
    assert parse_master_etag('W/"vehicle-short-v1"') is None
    assert parse_master_etag('W/"other-01H1234567890ABCDEFGHJKMNP-v1"') is None
    assert parse_spec_etag('W/"vehicle-01H1234567890ABCDEFGHJKMNP-v1"') is None  # Mixed v and sv
