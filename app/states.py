"""Pure order state machine. No database, no HTTP.

An order moves placed -> accepted -> cooking -> out_for_delivery -> delivered.
It can be cancelled, but only while the kitchen has not started cooking.

What is worth testing
---------------------
* ``can_move`` - every legal pair returns True, and the illegal ones return
  False: delivered -> cooking, cancelled -> anything, a status to itself,
  and skipping a stage (placed -> out_for_delivery).
* ``assert_move`` - raises with a reason, and the reason names both statuses.
* ``is_cancellable`` / ``assert_cancel`` - placed and accepted can cancel,
  cooking and everything after it cannot. This is the refund rule, so it is
  worth its own tests rather than leaning on can_move.
* ``is_backwards`` - the concurrency guard. cooking -> accepted is backwards,
  cooking -> cancelled is not backwards, it is simply illegal, and the two
  need different error messages.
* ``apply_update`` - the full gate, including the expected-status check that
  stops the second of two staff members undoing the first.
* ``progress`` and ``remaining_stages`` - a cancelled order is not 60% done.
"""

PLACED = "placed"
ACCEPTED = "accepted"
COOKING = "cooking"
OUT_FOR_DELIVERY = "out_for_delivery"
DELIVERED = "delivered"
CANCELLED = "cancelled"

# The happy path, in order. Index in this list is how far along an order is,
# which is what makes "did this update move the order backwards?" answerable.
PIPELINE = (PLACED, ACCEPTED, COOKING, OUT_FOR_DELIVERY, DELIVERED)

STATUSES = PIPELINE + (CANCELLED,)

# Legal moves. Everything not listed here is refused.
TRANSITIONS = {
    PLACED: (ACCEPTED, CANCELLED),
    ACCEPTED: (COOKING, CANCELLED),
    COOKING: (OUT_FOR_DELIVERY,),
    OUT_FOR_DELIVERY: (DELIVERED,),
    DELIVERED: (),
    CANCELLED: (),
}

# Once the kitchen has committed ingredients, the customer owns the order.
CANCELLABLE_BEFORE = COOKING

TERMINAL = (DELIVERED, CANCELLED)


class TransitionError(ValueError):
    """An update that must be refused. ``conflict`` marks the 409 cases."""

    def __init__(self, message, conflict=False):
        super().__init__(message)
        self.conflict = conflict


def check_status(status):
    s = str(status or "").strip().lower()
    if s not in STATUSES:
        raise TransitionError("%r is not an order status (expected one of %s)"
                              % (status, ", ".join(STATUSES)))
    return s


def stage(status):
    """Position on the happy path. A cancelled order is off it, so it has
    no position and comparisons against it are meaningless."""
    status = check_status(status)
    if status == CANCELLED:
        return None
    return PIPELINE.index(status)


def is_terminal(status):
    return check_status(status) in TERMINAL


def next_states(status):
    return list(TRANSITIONS[check_status(status)])


def can_move(current, target):
    return check_status(target) in TRANSITIONS[check_status(current)]


def is_backwards(current, target):
    """Would this update undo work that has already happened?

    Two members of restaurant staff with the order open will both tap the
    button they see. The second tap arrives against a status that has already
    moved on, and must not drag the order back to it. Worth separating from
    "illegal" because the message to the user is different: one is "that is
    not a thing you can do", the other is "somebody beat you to it".
    """
    here, there = stage(current), stage(target)
    if here is None or there is None:
        return False
    return there <= here


def assert_move(current, target):
    """Raise unless this transition is legal, with the right kind of error."""
    current = check_status(current)
    target = check_status(target)
    if current == target:
        raise TransitionError("the order is already %s" % current, conflict=True)
    if is_terminal(current):
        raise TransitionError(
            "a %s order is finished and cannot move to %s" % (current, target),
            conflict=True)
    if is_backwards(current, target):
        raise TransitionError(
            "the order is already %s and cannot go back to %s" % (current, target),
            conflict=True)
    if target == CANCELLED:
        assert_cancel(current)
    if not can_move(current, target):
        raise TransitionError(
            "%s cannot move straight to %s (next: %s)"
            % (current, target, ", ".join(TRANSITIONS[current]) or "nothing"))
    return target


def is_cancellable(status):
    """Cancellation is allowed only before the kitchen starts cooking."""
    here = stage(status)
    if here is None:
        return False
    return here < PIPELINE.index(CANCELLABLE_BEFORE)


def assert_cancel(status):
    status = check_status(status)
    if status == CANCELLED:
        raise TransitionError("the order is already cancelled", conflict=True)
    if not is_cancellable(status):
        raise TransitionError(
            "too late to cancel - the order is already %s" % status, conflict=True)
    return CANCELLED


def apply_update(current, target, expected=None):
    """The whole gate for one status update.

    ``expected`` is the status the caller believed the order was in when
    they pressed the button. When it is supplied and no longer matches,
    somebody else has already moved the order and this update is stale.
    The database does the real check with a conditional UPDATE; this
    function is where the rule is written down and tested.
    """
    current = check_status(current)
    if expected is not None:
        expected = check_status(expected)
        if expected != current:
            raise TransitionError(
                "the order moved to %s while you were looking at %s"
                % (current, expected), conflict=True)
    return assert_move(current, target)


def progress(status):
    """How far along, 0.0 to 1.0. A cancelled order never completes."""
    here = stage(status)
    if here is None:
        return 0.0
    return round(here / (len(PIPELINE) - 1), 2)


def remaining_stages(status):
    here = stage(status)
    if here is None:
        return []
    return list(PIPELINE[here + 1:])


def describe(status):
    """Everything the customer's screen needs about one status."""
    status = check_status(status)
    return {
        "status": status,
        "progress": progress(status),
        "terminal": is_terminal(status),
        "cancellable": is_cancellable(status),
        "next": next_states(status),
        "remaining": remaining_stages(status),
    }


def replay(events, start=PLACED):
    """Fold a list of target statuses over an order, stopping at the first
    illegal one. Returns (final_status, applied, rejected)."""
    current = check_status(start)
    applied, rejected = [], []
    for target in events:
        try:
            current = assert_move(current, target)
            applied.append(current)
        except TransitionError as e:
            rejected.append({"target": target, "reason": str(e)})
    return current, applied, rejected
