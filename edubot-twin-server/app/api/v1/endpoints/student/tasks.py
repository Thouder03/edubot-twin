import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_student_id
from app.crud import simulation_task as crud_task
from app.db.database import AsyncSessionLocal, get_db
from app.schemas.common import ApiResponse
from app.schemas.experiment import SimulationTaskStageStatusItem, StudentSimulationTaskResponse

router = APIRouter()


@router.get("/{task_id}", response_model=ApiResponse[StudentSimulationTaskResponse], summary="查询仿真任务")
async def get_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    student_id: int = Depends(get_current_student_id),
):
    task = await crud_task.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="TASK_NOT_FOUND")
    if task.student_id != student_id:
        raise HTTPException(status_code=403, detail="FORBIDDEN")

    stages = [SimulationTaskStageStatusItem(**item) for item in (task.stage_statuses or [])]
    return ApiResponse(
        data=StudentSimulationTaskResponse(
            task_id=task.task_id,
            task_status=task.status.value,
            elapsed_ms=task.elapsed_ms,
            retryable=task.retryable,
            error_code=task.error_code,
            error_message=task.error_message,
            stage_statuses=stages,
        )
    )


@router.get("/{task_id}/stream", summary="任务状态SSE流")
async def stream_task(
    task_id: str,
    student_id: int = Depends(get_current_student_id),
):
    async def event_generator():
        last_payload = None
        keepalive_counter = 0

        while True:
            async with AsyncSessionLocal() as db:
                task = await crud_task.get_task(db, task_id)
                if not task:
                    payload = {"error": "TASK_NOT_FOUND"}
                    yield f"event: error\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    return
                if task.student_id != student_id:
                    payload = {"error": "FORBIDDEN"}
                    yield f"event: error\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    return

                payload = {
                    "task_id": task.task_id,
                    "task_status": task.status.value,
                    "elapsed_ms": task.elapsed_ms,
                    "retryable": task.retryable,
                    "error_code": task.error_code,
                    "error_message": task.error_message,
                    "stage_statuses": task.stage_statuses or [],
                }

                payload_json = json.dumps(payload, ensure_ascii=False)
                if payload_json != last_payload:
                    yield f"event: update\ndata: {payload_json}\n\n"
                    last_payload = payload_json
                    keepalive_counter = 0
                else:
                    keepalive_counter += 1
                    if keepalive_counter >= 60:
                        yield "event: keepalive\ndata: {}\n\n"
                        keepalive_counter = 0

                if task.status.value in ("SUCCEEDED", "FAILED"):
                    return

            await asyncio.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
