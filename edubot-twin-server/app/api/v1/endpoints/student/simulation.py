from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_student_id
from app.crud import container as crud_container
from app.crud import experiment as crud_experiment
from app.core.port_allocator import PortExhaustedError
from app.db.database import get_db
from app.schemas.common import ApiResponse
from app.schemas.container import ContainerCreate
from app.schemas.experiment import StudentSimulationStartRequest, StudentSimulationStartResponse

router = APIRouter()


@router.post("/start", response_model=ApiResponse[StudentSimulationStartResponse], summary="开始仿真")
async def start_simulation(
    data: StudentSimulationStartRequest,
    db: AsyncSession = Depends(get_db),
    student_id: int = Depends(get_current_student_id),
):
    version = await crud_experiment.get_version(db, data.version_id)
    if not version or not version.is_visible or version.publish_status.value != "published":
        raise HTTPException(status_code=404, detail="EXPERIMENT_VERSION_NOT_FOUND")

    existing = await crud_container.get_container_by_user(db, student_id)

    if (
        existing
        and not data.force_recreate
        and existing.current_version_id == version.id
        and existing.status.value == "running"
    ):
        return ApiResponse(
            data=StudentSimulationStartResponse(
                task_id=None,
                container_status="running",
                experiment_context={
                    "experiment_id": version.experiment_id,
                    "version_id": version.id,
                    "environment_key": version.environment_key,
                },
            )
        )

    if existing:
        await crud_container.delete_container(db, existing)

    try:
        container = await crud_container.create_container(
            db,
            ContainerCreate(
                user_id=student_id,
                image_name=version.image_name,
                current_version_id=version.id,
            ),
        )
    except PortExhaustedError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))

    return ApiResponse(
        data=StudentSimulationStartResponse(
            task_id=None,
            container_status=container.status.value,
            experiment_context={
                "experiment_id": version.experiment_id,
                "version_id": version.id,
                "environment_key": version.environment_key,
            },
        )
    )
