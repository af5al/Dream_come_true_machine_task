from decimal import Decimal
from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app.models import Transaction, Wallet

client = TestClient(app)

USER_A = 1001
USER_B = 1002

def test_transaction_detail_idor_prevention():
    # Setup: User A has a transaction
    with SessionLocal() as db:
        db.query(Transaction).filter(Transaction.user_id.in_([USER_A, USER_B])).delete()
        tx = Transaction(
            user_id=USER_A,
            amount=Decimal("25.00"),
            kind="withdraw",
            status="completed",
            reference="ref-user-a-1"
        )
        db.add(tx)
        db.commit()
        tx_id = tx.id

    # 1. User B tries to view User A's transaction -> Must be 404
    res_b = client.get(f"/transactions/{tx_id}", headers={"X-User-Id": str(USER_B)})
    assert res_b.status_code == 404, "User B should not be able to access User A's transaction"

    # 2. User A views their own transaction -> Must be 200
    res_a = client.get(f"/transactions/{tx_id}", headers={"X-User-Id": str(USER_A)})
    assert res_a.status_code == 200
    data = res_a.json()
    assert data["id"] == tx_id
    assert float(data["amount"]) == 25.00
    assert data["user_id"] == USER_A
