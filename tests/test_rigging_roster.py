from dimwit.pipelines.rigging import ASSET_FOR
from dimwit.pipelines.roster_fidelity import active_roster_targets


def test_asset_for_covers_all_14_active():
    keys = {t["key"] for t in active_roster_targets()}
    missing = [k for k in keys if k not in ASSET_FOR]
    assert missing == [], f"rigging.ASSET_FOR missing active roster keys: {missing}"


def test_mech_keys_map_to_mech_assets():
    assert ASSET_FOR["mech_01_glaciera"] == "SM_Char_Mech_01_Glaciera"
    assert ASSET_FOR["mech_08_nightwire"] == "SM_Char_Mech_08_Nightwire"
