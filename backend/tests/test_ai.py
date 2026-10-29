from decimal import Decimal
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app, AI_CACHE
from app.db import SessionLocal
from app.models import Transaction, Wallet

client = TestClient(app)
USER_A = 7001
USER_B = 7002

def setup_users():
    AI_CACHE.clear()
    with SessionLocal() as db:
        db.query(Transaction).filter(Transaction.user_id.in_([USER_A, USER_B])).delete()
        db.query(Wallet).filter(Wallet.user_id.in_([USER_A, USER_B])).delete()

        # User A has transactions with sensitive references
        db.add(Wallet(user_id=USER_A, balance=Decimal('500.00')))
        db.add(Transaction(
            user_id=USER_A,
            amount=Decimal('100.00'),
            kind='deposit',
            status='completed',
            reference='SECRET_REF_USER_A_123'
        ))

        # User B has transactions
        db.add(Wallet(user_id=USER_B, balance=Decimal('50.00')))
        db.add(Transaction(
            user_id=USER_B,
            amount=Decimal('50.00'),
            kind='deposit',
            status='completed',
            reference='SECRET_REF_USER_B_456'
        ))
        db.commit()

def test_ai_prompt_context_strips_secret_reference():
    setup_users()
    spy_llm = MagicMock()
    spy_llm.answer.return_value = "Mocked AI reply"

    with patch('app.main.MockLLM', return_value=spy_llm):
        res = client.post(
            '/ai/ask',
            headers={'X-User-Id': str(USER_A)},
            json={'question': 'What are my transactions?'}
        )
        assert res.status_code == 200
        # Check arguments passed to MockLLM.answer(question, context)
        args, _ = spy_llm.answer.call_args
        question_arg, context_arg = args
        assert 'SECRET_REF_USER_A_123' not in context_arg, "Sensitive reference leaked to LLM!"
        assert 'amount' in context_arg

def test_ai_idor_prevention():
    setup_users()
    spy_llm = MagicMock()
    spy_llm.answer.return_value = "Mocked AI reply"

    with patch('app.main.MockLLM', return_value=spy_llm):
        # User A tries to spoof body user_id to User B
        res = client.post(
            '/ai/ask',
            headers={'X-User-Id': str(USER_A)},
            json={'question': 'My balance?', 'user_id': USER_B}
        )
        assert res.status_code == 200
        data = res.json()
        # Must only see User A's verified data
        assert data['verified_data']['user_id'] == USER_A
        assert float(data['verified_data']['wallet_balance']) == 500.00

def test_ai_provider_failure_returns_503():
    setup_users()
    with patch('app.main.MockLLM.answer', side_effect=Exception('OpenAI down')):
        res = client.post(
            '/ai/ask',
            headers={'X-User-Id': str(USER_A)},
            json={'question': 'Any question'}
        )
        assert res.status_code == 503

def test_ai_response_caching():
    setup_users()
    spy_llm = MagicMock()
    spy_llm.answer.return_value = "Generated Once"

    with patch('app.main.MockLLM', return_value=spy_llm):
        # First call hits LLM
        r1 = client.post('/ai/ask', headers={'X-User-Id': str(USER_A)}, json={'question': 'Summary?'})
        assert r1.status_code == 200
        assert spy_llm.answer.call_count == 1

        # Second identical call uses cache
        r2 = client.post('/ai/ask', headers={'X-User-Id': str(USER_A)}, json={'question': 'Summary?'})
        assert r2.status_code == 200
        assert spy_llm.answer.call_count == 1  # Did NOT call LLM again!