from pathlib import Path

# 宿主机数据目录（相对路径，CWD 固定为 edubot-twin-server/）
STUDENTS_DATA_ROOT           = Path("data/students")
EXPERIMENT_ASSETS_ROOT       = Path("data/experiment_assets")
ENV_BUNDLES_BASE_DIR         = Path("data/env_bundles")
FILE_BUNDLES_BASE_DIR        = Path("data/file_bundles")
EXAM_ENV_SNAPSHOTS_BASE_DIR  = Path("data/exam_env_snapshots")
EXAM_FILE_SNAPSHOTS_BASE_DIR = Path("data/exam_file_snapshots")
EXAM_EVAL_SCRIPTS_BASE_DIR   = Path("data/exam_eval_scripts")
EXAM_SUBMISSIONS_ROOT        = Path("data/exam_submissions")
EXAM_ARTIFACTS_ROOT          = Path("data/exam_artifacts")
TEMPLATES_DIR                = Path("data/templates/ros_packages")
SYSTEM_SCRIPTS_DIR           = Path("data/system")
SIDECAR_SCRIPT_HOST          = Path("data/system/agent/mini_file_server.py")

# 容器内固定路径
CONTAINER_WORKSPACE_DIR  = Path("/home/student/workspace")
CONTAINER_EXPERIMENT_DIR = Path("/home/student/experiment")


def get_student_root(student_id: int) -> Path:
    return STUDENTS_DATA_ROOT / str(student_id)


def get_student_workspace_host_dir(student_id: int) -> Path:
    return get_student_root(student_id) / "workspace"


def get_student_experiment_host_dir(student_id: int) -> Path:
    return get_student_root(student_id) / "experiment"


def get_experiment_bundle_root(experiment_id: int, bundle_id: int) -> Path:
    return EXPERIMENT_ASSETS_ROOT / str(experiment_id) / str(bundle_id)
