import uuid
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app.models import Wallet, Transaction

client = TestClient(app)
TEST_USER_ID = 9999

def test_withdraw_concurrency_race():
    # 1. Setup isolated test user with balance = 100.00
    with SessionLocal() as db:
        db.query(Transaction).filter_by(user_id=TEST_USER_ID).delete()
        db.query(Wallet).filter_by(user_id=TEST_USER_ID).delete()
        db.add(Wallet(user_id=TEST_USER_ID, balance=Decimal('100.00')))
        db.commit()

    # 2. Worker sending 80.00 withdrawal with unique reference
    def do_withdraw():
        res = client.post(
            "/withdraw",
            headers={"X-User-Id": str(TEST_USER_ID)},
            json={"amount": 80.00, "reference": str(uuid.uuid4())}
        )
        return res.status_code

    # 3. Fire concurrently
    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(do_withdraw)
        f2 = executor.submit(do_withdraw)
        results = [f1.result(), f2.result()]

    # 4. Exactly one 200, one 400
    assert results.count(200) == 1, f"Expected exactly one 200, got: {results}"
    assert results.count(400) == 1, f"Expected exactly one 400, got: {results}"

    # 5. DB balance must be exactly 20.00
    with SessionLocal() as db:
        w = db.query(Wallet).filter_by(user_id=TEST_USER_ID).one()
        assert w.balance == Decimal('20.00')

def test_withdraw_idempotency():
    with SessionLocal() as db:
        db.query(Transaction).filter_by(user_id=TEST_USER_ID).delete()
        db.query(Wallet).filter_by(user_id=TEST_USER_ID).delete()
        db.add(Wallet(user_id=TEST_USER_ID, balance=Decimal('100.00')))
        db.commit()

    ref = f"idem-{uuid.uuid4()}"

    # First call: succeeds
    r1 = client.post("/withdraw", headers={"X-User-Id": str(TEST_USER_ID)}, json={"amount": 30.00, "reference": ref})
    assert r1.status_code == 200
    assert r1.json()["balance"] == "70.00" or float(r1.json()["balance"]) == 70.00

    # Replay with same ref and amount: idempotent 200, balance unchanged
    r2 = client.post("/withdraw", headers={"X-User-Id": str(TEST_USER_ID)}, json={"amount": 30.00, "reference": ref})
    assert r2.status_code == 200
    assert float(r2.json()["balance"]) == 70.00

    # Conflict replay with same ref but DIFFERENT amount: 409 Conflict
    r3 = client.post("/withdraw", headers={"X-User-Id": str(TEST_USER_ID)}, json={"amount": 50.00, "reference": ref})
    assert r3.status_code == 409
