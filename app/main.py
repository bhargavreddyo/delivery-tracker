import json
import time

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from . import cache, db
from .states import (
    CANCELLED,
    PLACED,
    STATUSES,
    TransitionError,
    apply_update,
    assert_cancel,
    check_status,
    describe,
)

app = FastAPI(title="delivery-tracker")

ALL_CHANNEL = "orders:all"


def order_key(oid):
    return "order:%d" % oid


def channel(oid):
    return "orders:%d" % oid


@app.get("/health")
def health():
    out = {"status": "ok", "postgres": False, "redis": False}
    try:
        db.query("SELECT 1")
        out["postgres"] = True
    except Exception as e:
        out["pg_error"] = str(e)
    try:
        cache.client().ping()
        out["redis"] = True
    except Exception as e:
        out["redis_error"] = str(e)
    return out if out["postgres"] and out["redis"] else JSONResponse(out, status_code=503)


def load(oid):
    row = db.one("SELECT id, customer, restaurant, items, total_paise, status,"
                 " version, placed_at, updated_at FROM orders WHERE id=%s", (oid,))
    if not row:
        raise HTTPException(404, "no order with id %d" % oid)
    return row


def snapshot(row):
    """Everything a client needs about one order, built from a full row.

    One builder, used both by the cache writer and by the plain read, so a
    cached order can never come back with fewer fields than an uncached one.
    """
    return {"id": row["id"], "customer": row["customer"],
            "restaurant": row["restaurant"], "items": row["items"],
            "total_paise": row["total_paise"],
            "total_rupees": round(row["total_paise"] / 100, 2),
            "version": row["version"],
            "placed_at": row["placed_at"].isoformat(),
            "updated_at": row["updated_at"].isoformat(),
            **describe(row["status"])}


def publish(oid, actor="", previous=None):
    """Cache the new state and tell everyone who is listening.

    Both only happen AFTER the database has committed the change, so nothing
    ever announces a transition that did not actually take. who-did-what
    rides on the pub/sub message only; it is not part of the order itself.
    """
    state = snapshot(load(oid))
    cache.set_json(order_key(oid), state, ttl=3600)
    payload = json.dumps({**state, "previous": previous, "actor": actor},
                         default=str)
    r = cache.client()
    r.publish(channel(oid), payload)
    r.publish(ALL_CHANNEL, payload)
    return state


def move(oid, target, actor, expected=None):
    """One status change, decided by the database rather than by us.

    The conditional UPDATE is the whole concurrency story: the WHERE clause
    carries the status we believe the order is in, so if anybody moved it
    between our read and our write, zero rows come back and we lose.
    """
    current = load(oid)
    try:
        target = apply_update(current["status"], target, expected=expected)
    except TransitionError as e:
        raise HTTPException(409 if e.conflict else 400, str(e))

    row = db.one(
        "UPDATE orders SET status=%s, version=version+1, updated_at=now()"
        " WHERE id=%s AND status=%s RETURNING id",
        (target, oid, current["status"]))
    if row is None:
        # Somebody else got there between our read and our write.
        latest = load(oid)
        raise HTTPException(409, "the order moved to %s while you were acting on %s"
                            % (latest["status"], current["status"]))

    db.query("INSERT INTO order_events (order_id, from_status, to_status, actor)"
             " VALUES (%s,%s,%s,%s)",
             (oid, current["status"], target, actor), fetch=False)
    return publish(oid, actor=actor, previous=current["status"])


@app.post("/orders", status_code=201)
def create(payload: dict = Body(...)):
    customer = str(payload.get("customer", "")).strip()
    restaurant = str(payload.get("restaurant", "")).strip()
    if not customer or not restaurant:
        raise HTTPException(400, "an order needs a customer and a restaurant")
    items = payload.get("items") or []
    if not isinstance(items, list) or not items:
        raise HTTPException(400, "an order needs at least one item")
    try:
        total = sum(int(i["paise"]) for i in items)
    except (KeyError, TypeError, ValueError):
        raise HTTPException(400, "every item needs a whole number of paise")
    if total <= 0:
        raise HTTPException(400, "an order has to cost something")

    row = db.one(
        "INSERT INTO orders (customer, restaurant, items, total_paise, status)"
        " VALUES (%s,%s,%s::jsonb,%s,%s) RETURNING id",
        (customer, restaurant, json.dumps(items), total, PLACED))
    db.query("INSERT INTO order_events (order_id, from_status, to_status, actor)"
             " VALUES (%s,%s,%s,%s)", (row["id"], PLACED, PLACED, customer),
             fetch=False)
    return publish(row["id"], actor=customer)


@app.get("/orders/{oid}")
def get_order(oid: int):
    hit = cache.get_json(order_key(oid))
    if hit:
        return {**hit, "cached": True}
    out = snapshot(load(oid))
    cache.set_json(order_key(oid), out, ttl=3600)
    return {**out, "cached": False}


@app.post("/orders/{oid}/status")
def set_status(oid: int, payload: dict = Body(...)):
    target = payload.get("to")
    if target is None:
        raise HTTPException(400, "say what to move the order to: %s"
                            % ", ".join(STATUSES))
    try:
        check_status(target)
        expected = check_status(payload["expected"]) if payload.get("expected") else None
    except TransitionError as e:
        raise HTTPException(400, str(e))
    return move(oid, target, str(payload.get("actor", "")).strip(), expected=expected)


@app.post("/orders/{oid}/cancel")
def cancel(oid: int, payload: dict = Body(None)):
    payload = payload or {}
    current = load(oid)
    try:
        assert_cancel(current["status"])
    except TransitionError as e:
        raise HTTPException(409, str(e))
    return move(oid, CANCELLED, str(payload.get("actor", "")).strip(),
                expected=payload.get("expected"))


@app.get("/orders/{oid}/watch")
def watch(oid: int, timeout: int = Query(5)):
    """Block on pub/sub until this order moves, or until the timeout.

    Bounded on purpose - an unbounded subscribe holds a worker forever, and
    an order that is already delivered will never move again.
    """
    if not 1 <= timeout <= 20:
        raise HTTPException(400, "timeout must be between 1 and 20 seconds")
    row = load(oid)
    if describe(row["status"])["terminal"]:
        return {"order_id": oid, "moved": False,
                "reason": "the order is already %s and will not move again"
                          % row["status"], **describe(row["status"])}
    sub = cache.client().pubsub(ignore_subscribe_messages=True)
    sub.subscribe(channel(oid))
    try:
        # Loop rather than one long get_message: the first call is spent
        # swallowing the subscribe confirmation and returns None straight
        # away, so a single call would report "nothing happened" instantly.
        deadline = time.monotonic() + timeout
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                break
            message = sub.get_message(timeout=min(1.0, left))
            if message and message.get("type") == "message":
                return {"order_id": oid, "moved": True,
                        "event": json.loads(message["data"])}
        return {"order_id": oid, "moved": False,
                "reason": "nothing happened within %ds" % timeout}
    finally:
        sub.close()


@app.get("/restaurants/{name}/queue")
def queue(name: str):
    rows = db.query(
        "SELECT id, customer, status, total_paise, placed_at FROM orders"
        " WHERE restaurant=%s AND status NOT IN ('delivered','cancelled')"
        " ORDER BY placed_at", (name,))
    if not rows:
        raise HTTPException(404, "nothing outstanding for %r" % name)
    return {"restaurant": name, "outstanding": len(rows),
            "orders": [{**r, **describe(r["status"])} for r in rows]}
