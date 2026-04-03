from pathlib import Path

# 服务器实验资源根目录（宿主机）
EXPERIMENT_ASSETS_ROOT = Path("data/experiment_assets").resolve()

# 学生数据根目录（宿主机）
STUDENTS_DATA_ROOT = Path("data/students").resolve()

# 容器内固定路径
CONTAINER_WORKSPACE_DIR = Path("/home/student/workspace")
CONTAINER_EXPERIMENT_DIR = Path("/home/student/experiment")


def get_student_root(student_id: int) -> Path:
    return STUDENTS_DATA_ROOT / str(student_id)


def get_student_workspace_host_dir(student_id: int) -> Path:
    return get_student_root(student_id) / "workspace"


def get_student_experiment_host_dir(student_id: int) -> Path:
    return get_student_root(student_id) / "experiment"


def get_experiment_bundle_root(experiment_id: int, bundle_id: int) -> Path:
    return EXPERIMENT_ASSETS_ROOT / str(experiment_id) / str(bundle_id)
