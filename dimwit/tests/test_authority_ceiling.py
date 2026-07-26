import pytest

from dimwit.authority import is_ceiling_violation
from dimwit.pipelines.base import OPERATOR_ONLY


@pytest.mark.parametrize("state", sorted(OPERATOR_ONLY))
@pytest.mark.parametrize(
    "actor",
    ["", "operator", "non-operator-agent", "live_operator", "operator_impersonator", " human_operator ", None],
)
def test_operator_substrings_and_untrusted_labels_fail_closed(state, actor):
    assert is_ceiling_violation({"state": state, "actor": actor})


def test_exact_operator_actor_is_immediate_containment():
    state = sorted(OPERATOR_ONLY)[0]
    assert not is_ceiling_violation({"state": state, "actor": "human_operator"})
    assert not is_ceiling_violation({"state": f"State.{state}", "actor": "HUMAN_OPERATOR"})


def test_autonomous_states_do_not_require_operator_actor():
    assert not is_ceiling_violation({"state": "PROMOTED_TO_REVIEW", "actor": "codex"})
