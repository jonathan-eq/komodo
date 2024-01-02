import pytest

from komodo.symlink.sanity_check import assert_root_nodes


def test_assert_root_nodes_error_message():
    link_dict = {
        "links": {
            "stable": "2012.01",
            "testing": "2012.03",
            "missing_root_1": "2011.12",
            "missing_root_2": "2011.11",
            "missing_root_3": "2011.10",
        },
        "root_links": ["stable", "testing"],
    }

    with pytest.raises(
        AssertionError,
        match=r"Missing root\(s\): {(?=.*missing_root_1)(?=.*missing_root_2)(?=.*missing_root_3)",
    ):
        assert_root_nodes(link_dict)
