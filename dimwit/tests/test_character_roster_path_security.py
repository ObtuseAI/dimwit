import pytest

from scripts.pipeline import batch_characters
from scripts.qa import dimwit_cloud
from dimwit.character_roster_ids import CHARACTER_IDS


@pytest.mark.parametrize("name", CHARACTER_IDS)
def test_batch_accepts_each_owned_character_id(name):
    assert batch_characters.selected_names([name]) == [name]


@pytest.mark.parametrize(
    "name",
    ["../01_vorlax", r"..\01_vorlax", r"D:\escape\victim", r"\\host\share\victim", "09_unknown", ""],
)
def test_batch_rejects_path_and_unknown_character_ids(name):
    with pytest.raises(ValueError, match="unknown character id"):
        batch_characters.selected_names([name])


def test_provider_plan_fails_closed_if_one_redo_name_is_invalid():
    plan = {
        "queue": [
            {"name": "01_vorlax", "action": "redo"},
            {"name": "../01_vorlax", "action": "redo"},
        ]
    }
    with pytest.raises(ValueError, match="unknown character id"):
        dimwit_cloud._validated_redos(plan)


def test_provider_plan_preserves_valid_redo_subset():
    plan = {
        "queue": [
            {"name": "01_vorlax", "action": "redo"},
            {"name": "02_ekris", "action": "accept"},
        ]
    }
    assert dimwit_cloud._validated_redos(plan) == ["01_vorlax"]
