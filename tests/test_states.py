import pytest

from app.states import (
    ACCEPTED,
    CANCELLED,
    COOKING,
    DELIVERED,
    OUT_FOR_DELIVERY,
    PLACED,
    TransitionError,
    apply_update,
    assert_cancel,
    assert_move,
    can_move,
    is_backwards,
    is_cancellable,
    progress,
    remaining_stages,
)


def test_legal_order_transitions():
    assert can_move(PLACED, ACCEPTED)
    assert can_move(ACCEPTED, COOKING)
    assert can_move(COOKING, OUT_FOR_DELIVERY)
    assert can_move(OUT_FOR_DELIVERY, DELIVERED)


def test_skipping_order_stage_is_rejected():
    assert not can_move(PLACED, OUT_FOR_DELIVERY)

    with pytest.raises(TransitionError):
        assert_move(PLACED, OUT_FOR_DELIVERY)


def test_order_cannot_move_to_same_status():
    with pytest.raises(TransitionError, match="already placed"):
        assert_move(PLACED, PLACED)


def test_cancellation_allowed_before_cooking():
    assert is_cancellable(PLACED)
    assert is_cancellable(ACCEPTED)
    assert assert_cancel(PLACED) == CANCELLED
    assert assert_cancel(ACCEPTED) == CANCELLED


def test_cancellation_rejected_after_cooking_starts():
    for status in (COOKING, OUT_FOR_DELIVERY, DELIVERED):
        assert not is_cancellable(status)

        with pytest.raises(TransitionError):
            assert_cancel(status)


def test_cancelled_order_cannot_move():
    with pytest.raises(TransitionError):
        assert_move(CANCELLED, ACCEPTED)


def test_backwards_transition_is_detected():
    assert is_backwards(COOKING, ACCEPTED)
    assert not is_backwards(COOKING, CANCELLED)


def test_stale_expected_status_is_rejected():
    with pytest.raises(TransitionError, match="moved to cooking"):
        apply_update(COOKING, OUT_FOR_DELIVERY, expected=ACCEPTED)


def test_valid_update_with_expected_status():
    assert apply_update(PLACED, ACCEPTED, expected=PLACED) == ACCEPTED


def test_cancelled_order_has_zero_progress():
    assert progress(CANCELLED) == 0.0


def test_delivered_order_has_full_progress():
    assert progress(DELIVERED) == 1.0


def test_remaining_stages():
    assert remaining_stages(PLACED) == [
        ACCEPTED,
        COOKING,
        OUT_FOR_DELIVERY,
        DELIVERED,
    ]
    assert remaining_stages(DELIVERED) == []
    assert remaining_stages(CANCELLED) == []
