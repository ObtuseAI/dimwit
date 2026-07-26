from dimwit.pipelines.animation import ASSET_FOR
from dimwit.pipelines.roster_fidelity import active_roster_targets


def test_anim_asset_for_covers_all_14_active():
    keys = {t["key"] for t in active_roster_targets()}
    missing = [k for k in keys if k not in ASSET_FOR]
    assert missing == [], f"animation.ASSET_FOR missing active roster keys: {missing}"
