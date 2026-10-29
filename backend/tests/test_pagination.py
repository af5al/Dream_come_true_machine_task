from decimal import Decimal
from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app.models import Transaction, Wallet

client = TestClient(app)
USER_ID = 8888

def setup_transactions(count=25):
    with SessionLocal() as db:
        db.query(Transaction).filter_by(user_id=USER_ID).delete()
        for i in range(1, count + 1):
            db.add(Transaction(
                user_id=USER_ID,
                amount=Decimal(f"{i}.00"),
                kind="deposit",
                status="completed",
                reference=f"ref-page-{i}"
            ))
        db.commit()

def test_keyset_pagination_page_traversal():
    setup_transactions(count=25)

    # 1. Fetch Page 1: limit 10
    r1 = client.get("/transactions?limit=10", headers={"X-User-Id": str(USER_ID)})
    assert r1.status_code == 200
    p1 = r1.json()
    assert len(p1["items"]) == 10
    assert p1["has_more"] is True
    assert p1["next_cursor"] is not None

    page1_ids = [t["id"] for t in p1["items"]]
    # IDs should be strictly descending
    assert page1_ids == sorted(page1_ids, reverse=True)

    # 2. Fetch Page 2 using next_cursor
    cursor = p1["next_cursor"]
    r2 = client.get(f"/transactions?limit=10&cursor={cursor}", headers={"X-User-Id": str(USER_ID)})
    assert r2.status_code == 200
    p2 = r2.json()
    assert len(p2["items"]) == 10
    assert p2["has_more"] is True

    page2_ids = [t["id"] for t in p2["items"]]
    # Prove NO overlap between page 1 and page 2
    assert set(page1_ids).isdisjoint(set(page2_ids))

    # 3. Fetch Page 3 (final page with remaining 5 items)
    r3 = client.get(f"/transactions?limit=10&cursor={p2['next_cursor']}", headers={"X-User-Id": str(USER_ID)})
    assert r3.status_code == 200
    p3 = r3.json()
    assert len(p3["items"]) == 5
    assert p3["has_more"] is False
    assert p3["next_cursor"] is None

def test_limit_capping():
    setup_transactions(count=5)
    # Requesting limit 1000 must be capped at 50
    res = client.get("/transactions?limit=1000", headers={"X-User-Id": str(USER_ID)})
    assert res.status_code == 200
    assert len(res.json()["items"]) <= 50
