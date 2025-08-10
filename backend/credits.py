"""Credit management utilities backed by Supabase.

This module encapsulates Supabase client creation and exposes helper
functions that can be imported from both the API layer and background
processing without causing circular imports.
"""
import os
import logging
from decimal import Decimal
from fastapi import HTTPException
from supabase import create_client, Client

logger = logging.getLogger(__name__)

# Initialize Supabase client (service role) if available
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

if SUPABASE_URL and SUPABASE_SERVICE_KEY:
    supabase: Client | None = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
else:
    supabase = None
    logger.warning("Supabase configuration missing. Credit system will be disabled.")


async def get_or_create_user_credits(user_id: str) -> dict:
    if not supabase:
        raise HTTPException(status_code=500, detail="Credit system not configured")

    try:
        result = supabase.table('user_credits').select('*').eq('user_id', user_id).execute()
        if result.data:
            return result.data[0]
        new_credit = supabase.table('user_credits').insert({
            'user_id': user_id,
            'credits': 5.00
        }).execute()
        return new_credit.data[0]
    except Exception as e:
        logger.error(f"Error managing user credits for {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to manage user credits")


async def update_user_credits(user_id: str, new_amount: float) -> dict:
    if not supabase:
        raise HTTPException(status_code=500, detail="Credit system not configured")

    try:
        result = supabase.table('user_credits').update({
            'credits': new_amount
        }).eq('user_id', user_id).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="User credits not found")
        return result.data[0]
    except Exception as e:
        logger.error(f"Error updating credits for {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update user credits")


async def deduct_user_credits(user_id: str, amount: float) -> dict:
    if not supabase:
        raise HTTPException(status_code=500, detail="Credit system not configured")
    try:
        current_credits = await get_or_create_user_credits(user_id)
        current_amount = float(current_credits['credits'])
        if current_amount < amount:
            raise HTTPException(status_code=400, detail="Insufficient credits")
        new_amount = current_amount - amount
        return await update_user_credits(user_id, new_amount)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deducting credits for {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to deduct credits")


async def refund_credits_on_failure(user_id: str, amount: float, task_id: str):
    """Refund credits if conversion fails.

    This mirrors the logic used during deduction but adds a transaction log when possible.
    """
    if not supabase or not amount:
        return
    try:
        logger.info(f"Processing refund for user {user_id}: ${amount}")
        credits_response = supabase.table("user_credits").select("*").eq("user_id", user_id).execute()
        if credits_response.data:
            current_credits = Decimal(str(credits_response.data[0]["credits"]))
            refund_amount = Decimal(str(amount))
            new_credits = current_credits + refund_amount

            update_response = supabase.table("user_credits").update({
                "credits": float(new_credits),
                "updated_at": "now()"
            }).eq("user_id", user_id).execute()
            logger.info(f"Credit refund result: {update_response}")

            # Attempt to log refund transaction
            try:
                transaction_response = supabase.table("credit_transactions").insert({
                    "user_id": user_id,
                    "added_amount": float(refund_amount),
                    "previous_credits": float(current_credits),
                    "new_credits": float(new_credits),
                    "remaining_credits": float(new_credits),
                    "transaction_type": "credit",
                    "description": f"Refund for failed conversion (task: {task_id})",
                    "updated_at": "now()"
                }).execute()
                logger.info(f"Refund transaction logged: {transaction_response}")
            except Exception as transaction_error:
                logger.warning(f"Failed to log refund transaction: {transaction_error}")
    except Exception as e:
        logger.error(f"Failed to refund credits: {e}")


