import functools
import importlib
import logging
import multiprocessing

# for Schrodinger 2021-2 and higher version
importlib.reload(multiprocessing)
import os
import signal
import subprocess
import time
from multiprocessing import Pool
from typing import Callable, Iterable

import requests
import urllib3
from rich.progress import (BarColumn, Progress, SpinnerColumn, TextColumn,
                           TimeElapsedColumn, TimeRemainingColumn)
from rich.table import Column

from .common import FixedThread, TimeoutError

NUM_PARALLEL = multiprocessing.cpu_count() // 4 * 3
logger = logging.getLogger(__name__)


def makedirs_from_list(dir_list: list) -> None:
    """Make directories from a list.

    Args:
        dir_list (list): list of required directory names
    """
    for dir in dir_list:
        os.makedirs(dir, exist_ok=True)


def _get_progress(name: str, description: str, total: int, start: bool = False):
    """Create a progress bar.

    Args:
        name (str): name of the progress bar
        description (str): style description of the progress bar
        total (int): total number of tasks
        start (bool, optional): start the progress bar immediately. Defaults to False.

    Returns:
        rich.progress.Progress: Progress bar object
    """

    text_column = TextColumn("{task.description}",
                             table_column=Column(), justify='right')
    percent_column = TextColumn(
        "[bold green]{task.percentage:.1f}%", table_column=Column())
    finished_column = TextColumn(
        "[bold purple]{task.completed} of {task.total}")
    bar_column = BarColumn(bar_width=None, table_column=Column())
    progress = Progress(SpinnerColumn(), text_column, "•", TimeElapsedColumn(
    ), "•", percent_column, bar_column, finished_column, TimeRemainingColumn())

    taskID = progress.add_task('[%s]%s' % (
        description, name), total=total, start=start)

    return progress, taskID


def _func_timeout(func, *args, timeout=0, **kwargs):
    """Run a function with a timeout.

    Args:
        func (Callable): the function to run
        timeout (int, optional): timeout for the function. Defaults to 0.
    """
    def timeout_handler(signum, frame):
        raise TimeoutError()
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(timeout)
    try:
        result = func(*args, **kwargs)
    except TimeoutError:
        args_list = [str(arg) for arg in args]
        kwargs_list = [f"{k}={v}" for k, v in kwargs.items()]
        error_info = f"Task timed out after {timeout} seconds: {func.__name__}({', '.join(args_list)})"
        if kwargs_list:
            error_info = error_info.replace(
                ")", f", {', '.join(kwargs_list)})")
        raise TimeoutError(error_info)
    return result


def shell_run(command: str, timeout: int = None) -> str:
    """Run a shell command.

    Args:
        command (str): shell command to run
        timeout (int, optional): timeout for the command. Defaults to None.

    Returns:
        str: command output
    """
    try:
        result = subprocess.run(command, shell=True, check=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        return result.stdout.decode('utf-8').strip()
    except subprocess.CalledProcessError as e:
        logger.error(f"Error running command: {command}")
        raise e
    except subprocess.TimeoutExpired as e:
        logger.error(f"Timeout running command: {command}")
        raise e


def multiprocssing_run(func: Callable, iterable: Iterable, job_name: str, num_parallel: int, timeout: int = None, **kwargs) -> list:
    """Run a function in parallel using multiprocessing.

    Args:
        func (Callable): the function to run in parallel
        iterable (Iterable): the iterable to pass to the function. Each item in the iterable will be applied as an argument to the function
        job_name (str): the job name to display in the progress bar
        num_parallel (int): cpu core number
        timeout (int, optional): timeout for each function call. Defaults to None.
        kwargs: additional keyword arguments to pass to the function

    Returns:
        list: a list of return values from the function
    """
    timeout = 0 if timeout is None else timeout
    progress, taskID = _get_progress(job_name, 'bold cyan', len(iterable))
    returns = []
    progress.start()
    progress.start_task(taskID)

    def success_handler(result):
        returns.append(result)
        progress.update(taskID, advance=1)

    def error_handler(exception: Exception):
        logger.debug(f'Multiprocessing Run Warnning: {exception}')
        progress.update(taskID, advance=1)

    pool = Pool(num_parallel, maxtasksperchild=1)
    for item in iterable:
        pool.apply_async(_func_timeout, (func, item), kwds={
                         **kwargs, "timeout": timeout}, callback=success_handler, error_callback=error_handler)
    pool.close()
    pool.join()
    progress.stop()

    return returns


def download_pdb(pdbid: str, save_dir: str = None, overwrite: bool = False) -> None:
    """Download a PDB file from RCSB PDB.

    Args:
        pdbid (str): PDB ID to download
        save_dir (str, optional): directory to save the pdb file. Defaults to current working directory.
        overwrite (bool, optional): whether to overwrite the pdb file when it exists. Defaults to False.
    """
    base_url = 'https://files.rcsb.org/download/'
    pdbfile = f'{pdbid}.pdb'
    save_dir = os.getcwd() if save_dir is None else save_dir
    downloaded_file = os.path.join(save_dir, pdbfile)

    if os.path.exists(downloaded_file) and not overwrite:
        return

    url = base_url + pdbfile
    logger.debug(f'Downloading {pdbid} from URL {url}')
    urllib3.disable_warnings()
    response = requests.get(url)
    if response.status_code != 200:
        raise RuntimeError(f'Failed to download {pdbid}.pdb')
    pdb_data = response.text
    with open(downloaded_file, 'w') as f:
        f.write(pdb_data)

    logger.debug(f'{pdbid}.pdb has been downloaded to {save_dir}')


def download_pdb_list(pdblist: list, save_dir: str = None, overwrite: bool = False) -> None:
    """Download a list of PDB files from RCSB PDB.

    Args:
        pdblist (list): a list of PDB IDs to download
        save_dir (str, optional): directory to save the pdb files. Defaults to current working directory.
        overwrite (bool, optional): whether to overwrite the pdb files when they exist. Defaults to False.
    """
    save_dir = os.getcwd() if save_dir is None else save_dir
    threads = []
    for pdbid in pdblist:
        t = FixedThread(target=download_pdb, args=(pdbid, save_dir, overwrite))
        threads.append(t)
    for t in threads:
        t.start()
    for t in threads:
        t.join()


def timeit(func: Callable):
    """Decorator to measure the execution time of a function.

    Args:
        func (Callable): the function to measure the execution time

    Returns:
        wrapper: a wrapper function
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        end = time.time()
        logger.info(
            f'Start: {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(start))}')
        logger.info(
            f'End: {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(end))}')
        logger.info(
            f'Duration: {time.strftime("%H:%M:%S", time.gmtime(end - start))}')
        return result
    return wrapper


def _find_execu(path: str) -> bool:
    """Check if an executable is available in the PATH.

    Args:
        path (str): executable path, e.g., 'g16', 'Multiwfn', 'pmemd.cuda', etc.

    Returns:
        bool: True if the executable is available, False otherwise
    """
    p = subprocess.run(f"which {path}", shell=True,
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    if not os.path.exists(p.stdout.decode('utf-8').strip()):
        logger.info(f"\033[31m{path} is not installed or not in PATH.\033[0m")
        return False
    else:
        return True


def _check_execu_help(path: str) -> bool:
    """Check if an executable is available in the PATH by running the help command.

    Args:
        path (str): executable path

    Returns:
        bool: True if the executable is available, False otherwise
    """
    p = subprocess.run(f"{path} -h", shell=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if p.returncode == 0:
        return True
    else:
        logger.info(f"\033[31m{path} is not installed or not in PATH.\033[0m")
        return False


def _check_execu_version(path: str) -> bool:
    """Check if an executable is available in the PATH by running the version command.

    Args:
        path (str): executable path

    Returns:
        bool: True if the executable is available, False otherwise
    """
    p = subprocess.run(f"{path} --version", shell=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if p.returncode == 0:
        return True
    else:
        logger.info(f"\033[31m{path} is not installed or not in PATH.\033[0m")
        return False


def is_amber_available() -> bool:
    """Check if AMBER is available in the PATH.

    Returns:
        bool: True if AMBER is available, False otherwise
    """
    if not all([
        _check_execu_help('tleap'),
        _check_execu_version('sander'),
        _check_execu_version('cpptraj'),
        _check_execu_version('parmed'),
        _check_execu_version('pdb4amber'),
        _check_execu_help('antechamber')]
    ):
        return False
    else:
        return True


def is_pmemd_cuda_available() -> bool:
    """Check if pmemd.cuda is available in the PATH.

    Returns:
        bool: True if pmemd.cuda is available, False otherwise
    """
    return _check_execu_version('pmemd.cuda')


def is_gaussian_available() -> bool:
    """Check if Gaussian is available in the PATH.

    Returns:
        bool: True if Gaussian is available, False otherwise
    """
    return _find_execu('g16')


def is_multiwfn_available() -> bool:
    """Check if Multiwfn is available in the PATH.

    Returns:
        bool: True if Multiwfn is available, False otherwise
    """
    return _find_execu('Multiwfn')
