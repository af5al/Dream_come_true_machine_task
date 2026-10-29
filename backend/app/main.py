"""Wallet operations assessment application."""
from multiprocessing import context
from multiprocessing import context
from decimal import Decimal
from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import Base, engine, SessionLocal
from .models import Wallet, Transaction
from .providers import MockLLM, MockChain

app = FastAPI(title='Wallet Operations - Assessment')

# Simple in-memory cache for AI responses: {(user_id, question, latest_tx_id): (answer, verified_data)}
AI_CACHE: dict[tuple[int, str, int | None], dict] = {}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    with SessionLocal() as db:
        yield db

def current_user(x_user_id: int = Header(default=1)) -> int:
    return x_user_id

class MoneyRequest(BaseModel):
    amount: Decimal = Field(gt=0, decimal_places=2)
    reference: str | None = None

class DepositRequest(MoneyRequest):
    tx_hash: str
    network: str = 'ethereum'

class AskRequest(BaseModel):
    question: str
    user_id: int | None = None

@app.on_event('startup')
def initialize():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if not db.scalar(select(Wallet).where(Wallet.user_id == 1)):
            db.add(Wallet(user_id=1, balance=Decimal('100.00')))
        if not db.scalar(select(Wallet).where(Wallet.user_id == 2)):
            db.add(Wallet(user_id=2, balance=Decimal('250.00')))
        db.commit()

@app.get('/wallet')
def wallet(user_id: int = Depends(current_user), db: Session = Depends(get_db)):
    w = db.scalar(select(Wallet).where(Wallet.user_id == user_id))
    if not w:
        raise HTTPException(404, 'Wallet not found')
    return {'user_id': user_id, 'balance': w.balance}

@app.post('/withdraw')
def withdraw(req: MoneyRequest, user_id: int = Depends(current_user), db: Session = Depends(get_db)):

     # 1. Lock the wallet row first (serializes all balance-changing ops for this wallet)
    w = db.scalar(
        select(Wallet)
        .where(Wallet.user_id == user_id)
        .with_for_update()
    )

    if not w:
        raise HTTPException(404, 'Wallet not found');

    # idempotency check
    if req.reference:
      existing_tx = db.scalar(select(Transaction).where(
        Transaction.user_id == user_id,
        Transaction.reference == req.reference
      ))
      if existing_tx:
        if existing_tx.amount == req.amount:
           return {'status': 'completed', 'balance': w.balance}
        raise HTTPException(409, 'Reference already used with different amount')


    # sufficient fund checks
    if w.balance < req.amount:
        raise HTTPException(400, 'Insufficient Fund')

    # status mutation
    w.balance = w.balance - req.amount
    db.add(Transaction(user_id=user_id, amount=req.amount, kind='withdraw', status='completed', reference=req.reference))
    db.commit()
    return {'status': 'completed', 'balance': w.balance}

@app.get('/transactions')
def list_transactions(
        limit: int = 20,
        cursor: int | None = None,
        user_id: int = Depends(current_user),
        db: Session = Depends(get_db)
    ):
    limit = max(1,  min(limit, 50))
    query = select(Transaction).where(Transaction.user_id == user_id)
    
    if cursor is not None:
        query = query.where(Transaction.id < cursor)
        
    query =  query.order_by(Transaction.id.desc()).limit(limit + 1)
    results = db.scalars(query).all()
    
    has_more = len(results) > limit
    items = results[:limit]
    next_cursor = items[-1].id if has_more and items else None
    return {'items': items, 'next_cursor': next_cursor, 'has_more': has_more}

@app.get('/transactions/{transaction_id}')
def transaction_detail(transaction_id: int, user_id: int = Depends(current_user), db: Session = Depends(get_db)):
    
    t = db.scalar(select(Transaction).where(
        Transaction.id == transaction_id, Transaction.user_id == user_id
    ))
    if not t:
        raise HTTPException(404, 'Transaction Not found')
    return {'id': t.id, 'user_id': t.user_id, 'amount': t.amount, 'kind': t.kind, 'status': t.status, 'reference': t.reference, 'failure_reason': t.failure_reason}

@app.post('/ai/ask')
def ask(req: AskRequest, user_id: int = Depends(current_user), db: Session = Depends(get_db)):
    # 1. Strict ownership: ignore req.user_id completely, only use authenticated user_id
    # 2. Get user's wallet and transactions (minimal non-sensitive context)
    w = db.scalar(select(Wallet).where(Wallet.user_id == user_id))
    wallet_balance = str(w.balance) if w else "0.00"

    records = db.scalars(
        select(Transaction)
        .where(Transaction.user_id == user_id)
        .order_by(Transaction.id.desc())
        .limit(20)
    ).all()

    latest_tx_id = records[0].id if records else None

    # 3. Check Cache
    cache_key = (user_id, req.question.strip().lower(), latest_tx_id)
    if cache_key in AI_CACHE:
        return AI_CACHE[cache_key]

    # 4. Strip sensitive references from prompt context
    context = str([
        {'amount': str(t.amount), 'kind': t.kind, 'status': t.status}
        for t in records
    ])

    # 5. Call LLM safely with graceful fallback
    try:
        answer_text = MockLLM().answer(req.question, context)
    except Exception:
        raise HTTPException(503, 'AI assistant temporarily unavailable')

    # 6. Separate verified truth from AI generated answer
    response_payload = {
        'verified_data': {
            'user_id': user_id,
            'wallet_balance': wallet_balance,
            'transaction_count': len(records)
        },
        'answer': answer_text
    }

    AI_CACHE[cache_key] = response_payload
    return response_payload


@app.post('/deposits/verify')
def verify_deposit(req: DepositRequest, user_id: int = Depends(current_user), db: Session = Depends(get_db)):
    # 1. External RPC lookup with outage handling
    try:
        tx = MockChain().lookup(req.tx_hash)
    except Exception:
        raise HTTPException(503, 'Blockchain provider unavailable')

    if not tx:
        raise HTTPException(404, 'Transaction not found')

    # 2. Strict policy validation
    if tx.get('network') != req.network or tx.get('network') != 'ethereum':
        raise HTTPException(400, 'Invalid or mismatched network')
    if tx.get('token') != 'USDT':
        raise HTTPException(400, 'Only USDT token supported')
    if tx.get('to') != '0xmerchant':
        raise HTTPException(400, 'Invalid merchant recipient address')
    if tx.get('status') != 'success':
        raise HTTPException(400, 'Transaction status is not successful')
    if tx.get('confirmations', 0) < 12:
        raise HTTPException(400, 'Insufficient confirmations (minimum 12 required)')
    if Decimal(str(tx.get('amount'))) != Decimal(str(req.amount)):
        raise HTTPException(400, 'Amount mismatch with on-chain record')

    # 3. Deduplication / Replay protection across the entire system
    existing = db.scalar(
        select(Transaction).where(
            Transaction.reference == req.tx_hash,
            Transaction.kind == 'deposit'
        )
    )
    if existing:
        raise HTTPException(409, 'Transaction hash already credited')

    # 4. Lock wallet and credit atomically
    w = db.scalar(
        select(Wallet)
        .where(Wallet.user_id == user_id)
        .with_for_update()
    )
    if not w:
        raise HTTPException(404, 'Wallet not found')

    w.balance = w.balance + Decimal(str(req.amount))
    db.add(Transaction(
        user_id=user_id,
        amount=Decimal(str(req.amount)),
        kind='deposit',
        status='completed',
        reference=req.tx_hash
    ))
    db.commit()
    return {'status': 'credited', 'balance': w.balance}

        
