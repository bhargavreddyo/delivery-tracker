# Food Delivery Order Tracker

**Language:** Python (FastAPI) &nbsp;|&nbsp; **Needs:** Postgres + Redis

This is a **starter**. The application already works. Your job is everything
that gets it building, tested and running in CI.

---

## You do not need Python installed

You will build this into a container, and the container brings its own
Python 3.12. You are not being asked to extend the app — you are being asked
to ship it.

---

## 1. What this app needs

| | |
|---|---|
| **Runtime** | Python 3.12 |
| **Install dependencies** | `pip install -r requirements.txt` |
| **Start the app** | `uvicorn app.main:app --host 0.0.0.0 --port 8080` |
| **Listens on** | port 8080, bound to `0.0.0.0` |
| **Environment variables** | `DATABASE_URL`, `REDIS_URL` |
| **Needs running first** | Postgres, Redis, and the migrations applied |

### What it does

An order goes placed -> accepted -> cooking -> out for delivery -> delivered. Restaurant staff push it along, customers watch it move, and a customer can cancel - but only until the kitchen starts cooking. Every change is published so a watching client hears about it without polling.

### Endpoints

```
GET  /health
POST /orders                      {"customer":"asha","restaurant":"Sagar",
                                   "items":[{"name":"Dosa","paise":12000}]}
GET  /orders/{id}                 current state, served from the cache
POST /orders/{id}/status          {"to":"cooking","expected":"accepted","actor":"raj"}
POST /orders/{id}/cancel          {"actor":"asha"}
GET  /orders/{id}/watch?timeout=5 blocks on pub/sub until the status moves
GET  /restaurants/{name}/queue    what the kitchen still has to do
```

`/health` reports Postgres and Redis **separately**. If it says
`postgres: false` the app started fine and your compose wiring is wrong —
do not go looking in the application code.

### Migrations

`migrations/` holds `.sql` files applied **in filename order** before the app
starts. They create the tables and insert sample data. A container running
`psql` over them in order is enough; you do not need a migration tool.

---

## 2. What you must write

| File | What it has to do |
|---|---|
| `Dockerfile` | Install dependencies **before** copying source, pin the base image, do not run as root. |
| `docker-compose.yml` | App + Postgres + Redis + a migration step, one `docker compose up`. |
| `.circleci/config.yml` | lint → unit tests → integration tests → secret scan → image build |
| Unit tests | For `app/states.py`. No database, no network. |
| Integration tests | Against a real Postgres and Redis as CircleCI service containers. |

Then push your image to **your own Docker Hub account**, tagged `:1.0`.

### When it works

```bash
docker compose up --build
curl localhost:8080/health
```

```json
{"status":"ok","postgres":true,"redis":true}
```

---

## Where the marks are

`app/states.py` is **pure logic** — plain functions over plain data, no
database and no HTTP. Start your tests there. Use pytest:
`pytest --cov=app --cov-report=term-missing`. Minimum 70%.

`app/states.py` has no database in it, so the whole state machine is testable directly. Walk every pair of statuses - there are only thirty-six - and assert `can_move` agrees with the TRANSITIONS table. Then the interesting ones: `is_backwards` must separate 'illegal' from 'somebody beat you to it', because those are a 400 and a 409 and the difference matters to whoever is on the other end.

## Why Redis is here

Two jobs. Every status change is PUBLISHed on `orders:{id}` and `orders:all`, so a screen in the kitchen and the customer's phone both hear it without hammering the database every second. And each order's current state is cached, because 'where is my food' is asked far more often than it is answered.

Note what the cache is *not* used for: deciding whether a transition is legal. A cache can be stale, and a stale cache that is allowed to authorise a state change is how an order goes backwards.

## The hard part

**Two restaurant staff updating the same order at the same time must not move it backwards.**

Both have the order open showing the same status, and both tap the button they see. Work out why read-then-write loses here, make the database refuse the second one, then prove it by firing two updates at the same order in parallel.

Write your answer in your README. It is worth more marks than the feature.

---

## Getting unstuck

| Symptom | Almost always |
|---|---|
| `/health` says `postgres: false` | Wrong hostname. In compose the host is the **service name**, not `localhost`. |
| Page will not load, logs fine | No `ports:` mapping, or bound to `127.0.0.1` not `0.0.0.0`. |
| `relation "..." does not exist` | Migrations did not run, or the app started before they finished. |
| Build takes minutes each time | `COPY . .` is above your dependency install. |
| CI cannot reach the database | In CircleCI service containers the host **is** `localhost` — opposite of compose. |
