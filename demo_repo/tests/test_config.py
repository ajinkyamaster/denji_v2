"""Configuration merging and rendering."""

import pytest

from app.config import DEFAULTS, describe, is_valid_key, load_config


@pytest.mark.parametrize(
    'overrides, expected',
    [
        pytest.param({}, {'region': 'eu-west', 'retries': 3, 'timeout_s': 30, 'verbose': False}, id="T-0001"),
        pytest.param({'region': 'us-east'}, {'region': 'us-east', 'retries': 3, 'timeout_s': 30, 'verbose': False}, id="T-0002"),
        pytest.param({'retries': 0}, {'region': 'eu-west', 'retries': 0, 'timeout_s': 30, 'verbose': False}, id="T-0003"),
        pytest.param({'timeout_s': 1}, {'region': 'eu-west', 'retries': 3, 'timeout_s': 1, 'verbose': False}, id="T-0004"),
        pytest.param({'verbose': True}, {'region': 'eu-west', 'retries': 3, 'timeout_s': 30, 'verbose': True}, id="T-0005"),
        pytest.param({'region': 'ap-south', 'retries': 5}, {'region': 'ap-south', 'retries': 5, 'timeout_s': 30, 'verbose': False}, id="T-0006"),
        pytest.param({'retries': 9, 'timeout_s': 90}, {'region': 'eu-west', 'retries': 9, 'timeout_s': 90, 'verbose': False}, id="T-0007"),
        pytest.param({'verbose': False, 'region': 'sa-east'}, {'region': 'sa-east', 'retries': 3, 'timeout_s': 30, 'verbose': False}, id="T-0008"),
    ],
)
def test_merge_defaults(overrides, expected):
    """Merge defaults."""
    assert load_config(overrides) == expected


@pytest.mark.parametrize(
    'key, expected',
    [
        pytest.param('region', True, id="T-0009"),
        pytest.param('retries', True, id="T-0010"),
        pytest.param('timeout_s', True, id="T-0011"),
        pytest.param('verbose', True, id="T-0012"),
        pytest.param('unknown', False, id="T-0013"),
        pytest.param('', False, id="T-0014"),
        pytest.param(None, False, id="T-0015"),
        pytest.param(7, False, id="T-0016"),
        pytest.param('Region', False, id="T-0017"),
        pytest.param('region ', False, id="T-0018"),
    ],
)
def test_is_valid_key(key, expected):
    """Is valid key."""
    assert is_valid_key(key) is expected


@pytest.mark.parametrize(
    'config, expected',
    [
        pytest.param({'region': 'eu-west', 'retries': 3, 'timeout_s': 30, 'verbose': False}, 'region=eu-west,retries=3,timeout_s=30,verbose=False', id="T-0019"),
        pytest.param({'region': 'us-east', 'retries': 0, 'timeout_s': 1, 'verbose': True}, 'region=us-east,retries=0,timeout_s=1,verbose=True', id="T-0020"),
        pytest.param({'region': 'ap-south', 'retries': 9, 'timeout_s': 90, 'verbose': False}, 'region=ap-south,retries=9,timeout_s=90,verbose=False', id="T-0021"),
        pytest.param({'region': 'sa-east', 'retries': 1, 'timeout_s': 10, 'verbose': True}, 'region=sa-east,retries=1,timeout_s=10,verbose=True', id="T-0022"),
        pytest.param({'region': 'r1', 'retries': 1, 'timeout_s': 10, 'verbose': True}, 'region=r1,retries=1,timeout_s=10,verbose=True', id="T-0023"),
        pytest.param({'region': 'r2', 'retries': 2, 'timeout_s': 20, 'verbose': False}, 'region=r2,retries=2,timeout_s=20,verbose=False', id="T-0024"),
        pytest.param({'region': 'r3', 'retries': 3, 'timeout_s': 30, 'verbose': True}, 'region=r3,retries=3,timeout_s=30,verbose=True', id="T-0025"),
        pytest.param({'region': 'r4', 'retries': 4, 'timeout_s': 40, 'verbose': False}, 'region=r4,retries=4,timeout_s=40,verbose=False', id="T-0026"),
    ],
)
def test_describe(config, expected):
    """Describe."""
    assert describe(config) == expected


@pytest.mark.parametrize(
    'overrides, expected_error',
    [
        pytest.param({'nosuchkey': 1}, 'KeyError', id="T-0027"),
        pytest.param({'RETRIES': 2}, 'KeyError', id="T-0028"),
        pytest.param({'region': 5}, 'TypeError', id="T-0029"),
        pytest.param({'verbose': 'yes'}, 'TypeError', id="T-0030"),
    ],
)
def test_load_config_rejects_bad_overrides(overrides, expected_error):
    """Load config rejects bad overrides."""
    errors = {'KeyError': KeyError, 'TypeError': TypeError}
    with pytest.raises(errors[expected_error]):
        load_config(overrides)


