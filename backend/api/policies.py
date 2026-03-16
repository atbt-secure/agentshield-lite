from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from ..database import get_db
from ..models import Policy

router = APIRouter(prefix="/api/policies", tags=["policies"])


class PolicyCreate(BaseModel):
    name: str
    description: Optional[str] = None
    tool: str = "*"
    action: str = "*"
    condition: Optional[dict] = {}
    effect: str  # allow / block / alert
    priority: int = 100
    enabled: bool = True


class PolicyUpdate(PolicyCreate):
    pass


@router.get("")
async def list_policies(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Policy).order_by(Policy.priority))
    policies = result.scalars().all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "tool": p.tool,
            "action": p.action,
            "condition": p.condition,
            "effect": p.effect,
            "priority": p.priority,
            "enabled": p.enabled,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in policies
    ]


@router.post("", status_code=201)
async def create_policy(data: PolicyCreate, db: AsyncSession = Depends(get_db)):
    policy = Policy(**data.model_dump())
    db.add(policy)
    await db.commit()
    await db.refresh(policy)
    return {"id": policy.id, "name": policy.name, "effect": policy.effect}


@router.put("/{policy_id}")
async def update_policy(policy_id: int, data: PolicyUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Policy).where(Policy.id == policy_id))
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    for key, value in data.model_dump().items():
        setattr(policy, key, value)
    await db.commit()
    return {"id": policy.id, "name": policy.name}


@router.delete("/{policy_id}", status_code=204)
async def delete_policy(policy_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Policy).where(Policy.id == policy_id))
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    await db.delete(policy)
    await db.commit()
