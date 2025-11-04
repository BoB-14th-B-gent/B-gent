# TODO : 실행 Layer OS에 맞추어 테스트 필요 (Unix에서는 실행 시 sudo 권한 필요 / Windows는 별도 권한 설정 불필요)

"""Velociraptor 디스크 이미지 마운트

Velociraptor MCP 사용을 위해 디스크 이미지를 Velociraptor 클라이언트로 변환하는 기능 제공
"""
import os
import subprocess
import time
import logging
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

BGENT_ROOT = Path("/Users/me0w2en/Documents/8-BoB/B-gent")
VELOCIRAPTOR_ROOT = Path("/Users/me0w2en/Documents/8-BoB/velociraptor")

DATA_DIR = BGENT_ROOT / "data"
VELOCIRAPTOR_BIN = VELOCIRAPTOR_ROOT / "velociraptor"

_velociraptor_client_process: Optional[subprocess.Popen] = None


class VelociraptorMountError(Exception):
    """Velociraptor 마운트 관련 에러"""
    pass


def create_symlink(disk_image_name: str) -> Path:
    """디스크 이미지 심볼릭 링크 생성

    Args:
        disk_image_name: 디스크 이미지 파일명 (예: "Image.E01")

    Returns:
        Path: 생성된 심볼릭 링크 경로

    Raises:
        VelociraptorMountError: 원본 파일이 없거나 심볼릭 링크 생성 실패 시
    """
    source_path = DATA_DIR / disk_image_name
    target_path = VELOCIRAPTOR_ROOT / disk_image_name

    if not source_path.exists():
        raise VelociraptorMountError(f"디스크 이미지 파일이 존재하지 않습니다: {source_path}")

    if target_path.is_symlink():
        logger.info(f"기존 심볼릭 링크 삭제: {target_path}")
        target_path.unlink()
    elif target_path.exists():
        raise VelociraptorMountError(f"심볼릭 링크를 생성할 수 없습니다 (파일 존재): {target_path}")

    try:
        target_path.symlink_to(source_path)
        logger.info(f"심볼릭 링크 생성 완료: {target_path} -> {source_path}")
        return target_path
    except Exception as e:
        raise VelociraptorMountError(f"심볼릭 링크 생성 실패: {e}")


def run_deaddisk(disk_image_name: str) -> Path:
    """Velociraptor deaddisk 명령 실행하여 remapping.yaml 생성

    Args:
        disk_image_name: 디스크 이미지 파일명 (예: "Image.E01")

    Returns:
        Path: 생성된 remapping.yaml 파일 경로

    Raises:
        VelociraptorMountError: deaddisk 명령 실행 실패 시
    """
    remapping_file = VELOCIRAPTOR_ROOT / ".remapping.yaml"
    remapping_yaml = VELOCIRAPTOR_ROOT / "remapping.yaml"

    if remapping_file.exists():
        with open(remapping_file, 'r') as f:
            content = f.read()
            if len(content) > 100:
                logger.info(f"기존 .remapping.yaml 파일 사용 ({len(content)} bytes)")
                return remapping_file
            else:
                backup_file = VELOCIRAPTOR_ROOT / f".remapping.yaml.backup.{int(time.time())}"
                remapping_file.rename(backup_file)
                logger.info(f"손상된 .remapping.yaml 백업: {backup_file}")

    if remapping_yaml.exists():
        backup_file = VELOCIRAPTOR_ROOT / f"remapping.yaml.backup.{int(time.time())}"
        remapping_yaml.rename(backup_file)
        logger.info(f"기존 remapping.yaml 백업: {backup_file}")

    cmd = [
        str(VELOCIRAPTOR_BIN),
        "deaddisk",
        f"--add_windows_disk=./{disk_image_name}",
        "./.remapping.yaml",
        "-v"
    ]

    logger.info(f"deaddisk 명령 실행: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            cwd=str(VELOCIRAPTOR_ROOT),
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode != 0:
            raise VelociraptorMountError(
                f"deaddisk 명령 실패 (exit code: {result.returncode})\n"
                f"stdout: {result.stdout}\n"
                f"stderr: {result.stderr}"
            )

        logger.info(f"deaddisk 명령 완료:\n{result.stdout}")

        if not remapping_file.exists():
            raise VelociraptorMountError(".remapping.yaml 파일이 생성되지 않았습니다")

        with open(remapping_file, 'r') as f:
            content = f.read()
            if len(content) < 100:
                raise VelociraptorMountError(
                    f".remapping.yaml 파일이 제대로 생성되지 않았습니다 (크기: {len(content)} bytes)\n"
                    f"내용: {content}"
                )

        logger.info(f"remapping 파일 생성 완료: {remapping_file} ({len(content)} bytes)")
        return remapping_file

    except subprocess.TimeoutExpired:
        raise VelociraptorMountError("deaddisk 명령 타임아웃 (60초 초과)")
    except VelociraptorMountError:
        raise
    except Exception as e:
        raise VelociraptorMountError(f"deaddisk 명령 실행 중 오류: {e}")


def start_velociraptor_client() -> subprocess.Popen:
    """Velociraptor 클라이언트 백그라운드 실행

    Returns:
        subprocess.Popen: 실행 중인 프로세스 객체

    Raises:
        VelociraptorMountError: 클라이언트 실행 실패 시
    """
    config_file = VELOCIRAPTOR_ROOT / "client.root.config.yaml"
    remapping_file = VELOCIRAPTOR_ROOT / ".remapping.yaml"
    writeback_file = VELOCIRAPTOR_ROOT / "remapping.writeback.yaml"

    if not config_file.exists():
        raise VelociraptorMountError(f"설정 파일이 존재하지 않습니다: {config_file}")
    if not remapping_file.exists():
        raise VelociraptorMountError(f"remapping 파일이 존재하지 않습니다: {remapping_file}")

    with open(remapping_file, 'r') as f:
        remapping_content = f.read()
        if len(remapping_content) < 100:
            raise VelociraptorMountError(
                f".remapping.yaml이 제대로 생성되지 않았습니다.\n"
                f"내용: {remapping_content}\n"
                f"deaddisk 명령을 다시 실행해야 합니다."
            )

    cmd = [
        "sudo",
        str(VELOCIRAPTOR_BIN),
        "--remap", "./.remapping.yaml",
        "--config", "./client.root.config.yaml",
        "client",
        "-v",
        "--config.client-writeback-windows=./remapping.writeback.yaml"
    ]

    logger.info(f"Velociraptor 클라이언트 실행: {' '.join(cmd)}")

    log_file = VELOCIRAPTOR_ROOT / "client.log"
    err_file = VELOCIRAPTOR_ROOT / "client.err"

    try:
        with open(log_file, 'w') as log_f, open(err_file, 'w') as err_f:
            process = subprocess.Popen(
                cmd,
                cwd=str(VELOCIRAPTOR_ROOT),
                stdout=log_f,
                stderr=err_f,
                text=True
            )

        logger.info(f"Velociraptor 클라이언트 시작됨 (PID: {process.pid})")
        logger.info(f"로그 파일: {log_file}")
        logger.info(f"에러 파일: {err_file}")

        time.sleep(3)

        if process.poll() is not None:
            with open(log_file, 'r') as f:
                stdout = f.read()
            with open(err_file, 'r') as f:
                stderr = f.read()

            raise VelociraptorMountError(
                f"Velociraptor 클라이언트가 시작 직후 종료되었습니다 (exit code: {process.returncode})\n"
                f"stdout: {stdout}\n"
                f"stderr: {stderr}"
            )

        logger.info(f"Velociraptor 클라이언트 실행 중 (PID: {process.pid})")
        return process

    except VelociraptorMountError:
        raise
    except Exception as e:
        raise VelociraptorMountError(f"Velociraptor 클라이언트 실행 실패: {e}")


def check_client_status(process: subprocess.Popen, timeout: int = 10) -> bool:
    """Velociraptor 클라이언트 상태 확인

    Args:
        process: 실행 중인 프로세스 객체
        timeout: 상태 확인 대기 시간 (초)

    Returns:
        bool: 클라이언트가 정상 실행 중이면 True
    """
    log_file = VELOCIRAPTOR_ROOT / "client.log"
    err_file = VELOCIRAPTOR_ROOT / "client.err"

    logger.info(f"클라이언트 상태 확인 중 ({timeout}초)...")

    for i in range(timeout):
        if process.poll() is not None:
            stdout = ""
            stderr = ""

            if log_file.exists():
                with open(log_file, 'r') as f:
                    stdout = f.read()

            if err_file.exists():
                with open(err_file, 'r') as f:
                    stderr = f.read()

            logger.error(
                f"Velociraptor 클라이언트가 종료되었습니다 (exit code: {process.returncode})\n"
                f"stdout: {stdout}\n"
                f"stderr: {stderr}"
            )
            return False

        if (i + 1) % 3 == 0:
            logger.info(f"  [{i+1}/{timeout}] 클라이언트 실행 중 (PID: {process.pid})")

        time.sleep(1)

    logger.info(f"클라이언트 정상 실행 확인 완료 (PID: {process.pid})")

    if log_file.exists():
        with open(log_file, 'r') as f:
            recent_logs = f.read()
            if recent_logs:
                logger.info(f"최근 로그:\n{recent_logs[-500:]}")

    return True



def mount_disk_for_velociraptor(
    disk_image_name: str = "Image.E01",
    check_status: bool = True
) -> Tuple[Path, subprocess.Popen]:
    """Velociraptor용 디스크 이미지 마운트 전체 프로세스

    1. 심볼릭 링크 생성
    2. deaddisk 실행 (remapping.yaml 생성)
    3. Velociraptor 클라이언트 백그라운드 실행
    4. 클라이언트 상태 확인 (옵션)

    Args:
        disk_image_name: 디스크 이미지 파일명 (기본값: "Image.E01")
        check_status: 클라이언트 상태 확인 여부 (기본값: True)

    Returns:
        Tuple[Path, subprocess.Popen]: (remapping.yaml 경로, 클라이언트 프로세스)

    Raises:
        VelociraptorMountError: 마운트 프로세스 실패 시

    Example:
        >>> remapping_path, client_process = mount_disk_for_velociraptor("Image.E01")
        >>> print(f"Velociraptor 클라이언트 PID: {client_process.pid}")
    """
    logger.info(f"=== Disk Image Mount ===")
    logger.info(f"디스크 이미지: {disk_image_name}")

    try:
        logger.info("[1/4] 심볼릭 링크 생성")
        symlink_path = create_symlink(disk_image_name)

        logger.info("[2/4] deaddisk 실행")
        remapping_path = run_deaddisk(disk_image_name)

        logger.info("[3/4] Velociraptor 클라이언트 실행")
        client_process = start_velociraptor_client()

        if check_status:
            logger.info("[4/4] 클라이언트 상태 확인")
            if not check_client_status(client_process):
                raise VelociraptorMountError("클라이언트 상태 확인 실패")

        return remapping_path, client_process

    except VelociraptorMountError as e:
        logger.error(f"마운트 실패: {e}")
        raise
    except Exception as e:
        logger.error(f"예상치 못한 오류 발생: {e}")
        raise VelociraptorMountError(f"마운트 중 오류: {e}")


def stop_velociraptor_client(process: subprocess.Popen, timeout: int = 10) -> None:
    """Velociraptor 클라이언트 종료

    Args:
        process: 실행 중인 프로세스 객체
        timeout: 종료 대기 시간 (초)
    """
    if process.poll() is not None:
        logger.info("클라이언트가 이미 종료되었습니다")
        return

    logger.info(f"Velociraptor 클라이언트 종료 중 (PID: {process.pid})...")

    try:
        process.terminate()
        process.wait(timeout=timeout)
        logger.info("[✓] 클라이언트 정상 종료")
    except subprocess.TimeoutExpired:
        logger.warning("클라이언트가 종료되지 않아 강제 종료합니다")
        process.kill()
        process.wait()
        logger.info("[✓] 클라이언트 강제 종료")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    try:
        remapping, client = mount_disk_for_velociraptor("Image.E01")
        print(f"\n마운트 성공!")
        print(f"Remapping 파일: {remapping}")
        print(f"클라이언트 PID: {client.pid}")
        print("\n클라이언트를 종료하려면 Ctrl+C를 누르세요...")

        client.wait()

    except KeyboardInterrupt:
        print("\n\n클라이언트 종료 중...")
        stop_velociraptor_client(client)
    except VelociraptorMountError as e:
        print(f"\n마운트 실패: {e}")