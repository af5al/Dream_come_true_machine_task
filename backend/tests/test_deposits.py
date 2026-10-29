from decimal import Decimal
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app.models import Wallet, Transaction

client = TestClient(app)
USER_ID = 5001

def setup_user_wallet(balance=Decimal('0.00')):
    with SessionLocal() as db:
        db.query(Transaction).filter_by(user_id=USER_ID).delete()
        db.query(Wallet).filter_by(user_id=USER_ID).delete()
        db.add(Wallet(user_id=USER_ID, balance=balance))
        db.commit()

def test_valid_deposit_credits_wallet():
    setup_user_wallet(Decimal('10.00'))
    
    mock_tx = {
        'network': 'ethereum',
        'token': 'USDT',
        'to': '0xmerchant',
        'status': 'success',
        'confirmations': 15,
        'amount': '50.00'
    }
    
    with patch('app.main.MockChain.lookup', return_value=mock_tx):
        res = client.post(
            '/deposits/verify',
            headers={'X-User-Id': str(USER_ID)},
            json={'tx_hash': '0xvalid123', 'amount': 50.00}
        )
        assert res.status_code == 200
        assert float(res.json()['balance']) == 60.00

def test_replay_deposit_rejected():
    # Attempting to verify the exact same tx_hash again must return 409
    mock_tx = {
        'network': 'ethereum',
        'token': 'USDT',
        'to': '0xmerchant',
        'status': 'success',
        'confirmations': 15,
        'amount': '50.00'
    }
    with patch('app.main.MockChain.lookup', return_value=mock_tx):
        res = client.post(
            '/deposits/verify',
            headers={'X-User-Id': str(USER_ID)},
            json={'tx_hash': '0xvalid123', 'amount': 50.00}
        )
        assert res.status_code == 409

def test_deposit_confirmations_below_12():
    setup_user_wallet(Decimal('0.00'))
    mock_tx = {
        'network': 'ethereum',
        'token': 'USDT',
        'to': '0xmerchant',
        'status': 'success',
        'confirmations': 5,
        'amount': '50.00'
    }
    with patch('app.main.MockChain.lookup', return_value=mock_tx):
        res = client.post(
            '/deposits/verify',
            headers={'X-User-Id': str(USER_ID)},
            json={'tx_hash': '0xunconfirmed', 'amount': 50.00}
        )
        assert res.status_code == 400

def test_deposit_amount_mismatch():
    setup_user_wallet(Decimal('0.00'))
    mock_tx = {
        'network': 'ethereum',
        'token': 'USDT',
        'to': '0xmerchant',
        'status': 'success',
        'confirmations': 12,
        'amount': '50.00'
    }
    with patch('app.main.MockChain.lookup', return_value=mock_tx):
        # User claims 500.00 when tx is 50.00
        res = client.post(
            '/deposits/verify',
            headers={'X-User-Id': str(USER_ID)},
            json={'tx_hash': '0xmismatch', 'amount': 500.00}
        )
        assert res.status_code == 400

def test_deposit_rpc_failure():
    setup_user_wallet(Decimal('0.00'))
    with patch('app.main.MockChain.lookup', side_effect=Exception('RPC down')):
        res = client.post(
            '/deposits/verify',
            headers={'X-User-Id': str(USER_ID)},
            json={'tx_hash': '0xerror', 'amount': 50.00}
        )
        assert res.status_code == 503
