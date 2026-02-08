from fastapi import APIRouter, HTTPException
import httpx

from services.erp_client import ERPClient
from schemas.responses import ApiResponse

router = APIRouter(prefix="/test", tags=["test"])

_erp = ERPClient()


@router.delete("/invoice/{invoice_id}", response_model=ApiResponse[dict])
async def delete_test_invoice(invoice_id: str):
    """
    Delete a Purchase Invoice from ERPNext (used for test cleanup).
    
    This endpoint is for testing purposes only.
    """
    try:
        await _erp.delete_purchase_invoice(invoice_id)
        return ApiResponse(data={"success": True})
    except httpx.HTTPStatusError as e:
        # Handle 404 if invoice doesn't exist
        if e.response.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail=f"Invoice {invoice_id} not found in ERPNext"
            )
        # Handle other HTTP errors
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete invoice: {str(e)}"
        )
    except Exception as e:
        # Handle any other errors
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete invoice: {str(e)}"
        )
