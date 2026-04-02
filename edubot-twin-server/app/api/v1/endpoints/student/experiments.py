from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_student_id
from app.crud import experiment as crud_experiment
from app.db.database import get_db
from app.schemas.common import ApiResponse
from app.schemas.experiment import StudentAvailableVersionItem

router = APIRouter()


@router.get("/available", response_model=ApiResponse[list[StudentAvailableVersionItem]], summary="学生可用实验版本")
async def list_available_versions(
    db: AsyncSession = Depends(get_db),
    _: int = Depends(get_current_student_id),
):
    versions = await crud_experiment.list_student_available_versions(db)
    items: list[StudentAvailableVersionItem] = []
    for version in versions:
        exp = version.experiment
        summary = exp.description if exp else None
        items.append(
            StudentAvailableVersionItem(
                version_id=version.id,
                experiment_id=version.experiment_id,
                experiment_name=exp.name if exp else "",
                version_name=version.version_name,
                environment_key=version.environment_key,
                summary=summary,
            )
        )
    return ApiResponse(data=items)
