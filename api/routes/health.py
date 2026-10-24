from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "aryan_lead_gen",
        "version": "1.0.0"
    }


@router.get("/")
async def root():
    return {
        "message": "Aryan Lead-Gen API",
        "docs": "/docs"
    }
