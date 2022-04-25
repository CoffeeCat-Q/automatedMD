import logging
import os

from pyCADD.utils.tool import download_pdb_list, makedirs_from_list, _get_progress, _multiprocssing_run, NUM_PARALLEL
from pyCADD.Dock.common import PDBFile, DockResultFile, LigandFile, MultiInputFile
from pyCADD.Dock.core import minimize, grid_generate, dock
from pyCADD.Dock.data import extra_docking_data

logger = logging.getLogger(__name__)

def split_ligand(ligand_file:LigandFile, save_dir:str=None, overwrite:bool=False) -> list:
    '''
    将单个maestro文件中包含的所有小分子拆分为多个独立mae文件
    
    Parameters
    ----------
    ligand_file : LigandFile
        单个maestro文件
    save_dir : str
        拆分后的mae文件保存的目录
    overwrite : bool
        是否覆盖已存在的mae文件
    
    Returns
    -------
    list
        拆分后的配体文件路径列表   
            配体名称由 唯一索引index + ligand_name 组成 
    '''

    save_dir = ligand_file.file_dir if save_dir is None else save_dir
    logger.debug(f'Prepare to split structure file {ligand_file.file_name} to {save_dir}')

    progress, taskID = _get_progress('Reading Ligands', 'bold cyan', len(ligand_file.structures))
    progress.start()
    progress.start_task(taskID)

    label_list = []
    ligand_path_list = []
    activity_label_name = [f'{_type}_user_{_label}' for _type in ('b', 's') for _label in ('Activity', 'activity')]
    for index, structure in enumerate(ligand_file.structures):
        st_name = f"{index}-{structure.property['s_m_title']}"
        structure.property['i_user_StructureIndex'] = index

        st_activity = ''
        for _label in activity_label_name:
            try:
                st_activity = structure.property[_label]
                break
            except KeyError:
                continue
        label_list.append(f'{st_name},{st_activity}')

        output_file = os.path.join(save_dir, f'{st_name}.mae')
        if not os.path.exists(output_file) or overwrite:
            structure.write(output_file)
        
        ligand_path_list.append(output_file)
        progress.update(taskID, advance=1)

    with open(os.path.join(save_dir, 'label.csv'), 'w') as f:
        f.write('\n'.join(label_list))
    
    progress.stop()

    return ligand_path_list
    
class _Console:
    '''
    Ensemble docking 控制台对象
    '''
    def __init__(self, input_file:MultiInputFile) -> None:
        self.input_file = input_file
        self.pairs_list = input_file.get_pairs_list()
        self.pdbid_list = input_file.get_pdbid_list()
        self.grid_list = None
        self.minimized_list = None

        self.pdbfile_list = None
        self.minimized_file_list = None
        self.ligand_path_list = None
        self.mapping = None
        self.grid_file_list = None
        self.ligand_file_list = None
        self.dock_file_list = None
        self.docking_failed_list = None

        self.pdb_save_dir = os.path.join(os.getcwd(), 'pdb')
        self.minimize_save_dir = os.path.join(os.getcwd(), 'minimize')
        self.grid_save_dir = os.path.join(os.getcwd(), 'grid')
        self.ligand_save_dir = os.path.join(os.getcwd(), 'ligands')
        self.complex_save_dir = os.path.join(os.getcwd(), 'complex')
        self.protein_save_dir = os.path.join(os.getcwd(), 'protein')
        self.base_dock_save_dir = os.path.join(os.getcwd(), 'dockfiles')
        self.result_save_dir = os.path.join(os.getcwd(), 'result')
        
        makedirs_from_list([
            self.pdb_save_dir, 
            self.minimize_save_dir, 
            self.grid_save_dir,
            self.ligand_save_dir,
            self.complex_save_dir,
            self.protein_save_dir,
            self.base_dock_save_dir,
            self.result_save_dir
            ])
    
    def _get_failed_list(self, precision:str='SP'):
        '''
        获取此前对接任务失败的信息列表
        对接失败的任务不应该再次对接 且无结果文件可提取数据
        '''
        _failed_list_file_path = os.path.join(self.result_save_dir, f'docking_failed_{precision}.csv')

        if os.path.exists(_failed_list_file_path):
            with open(_failed_list_file_path, 'r') as f:
                lines = f.read().splitlines()
            _failed_list = [tuple(line.split(',')) for line in lines]
            return [(pdbid, internal_lig, docking_lig) for pdbid, internal_lig, docking_lig in _failed_list]
        else:
            return None

    @staticmethod
    def _creat_mapping(grid_file_list:list, ligand_file_list:list, failed_list:list=None) -> tuple:
        '''
        将所有受体与全部配体小分子建立完全映射关系

        Parameters
        ----------
        grid_file_list : list
            受体格点文件列表
        ligand_file_list : list
            配体文件列表
        failed_list : list
            此前不能成功对接的映射关系列表 将不再重新对接
        '''
        mapping_results = []
        failed_list = [] if failed_list is None else failed_list
        logger.debug(f'Prepare to map {len(ligand_file_list)} ligands to {len(grid_file_list)} receptors')

        for grid_file in grid_file_list:
            for ligand_file in ligand_file_list:
                if (grid_file.pdbid, grid_file.ligand, ligand_file.ligand_name) in failed_list:
                    logger.debug(f'Skip mapping {grid_file.pdbid}-{grid_file.ligand} to {ligand_file.ligand_name}')
                    continue
                mapping_results.append((grid_file, ligand_file))
            # mapping_results.extend([(grid_file, ligand_file) for ligand_file in ligand_file_list])

        return mapping_results

    def download_all_pdb(self, overwrite:bool=False) -> None:
        '''
        下载列表中的所有PDB文件

        Parameters
        ----------
        overwrite : bool
            是否覆盖已存在的文件
        '''
        pdbid_list = self.pdbid_list
        pdb_save_dir = self.pdb_save_dir
        download_pdb_list(pdbid_list, pdb_save_dir, overwrite)
        self.pdbfile_list = [PDBFile(pdbfile_path) for pdbfile_path in self.input_file.get_pdbfile_path_list(pdb_save_dir)]

    def keep_single_chain(self):
        '''
        将所有PDB文件转换为单链构象
        '''
        logger.debug(f'Prepare to keep single chain for {len(self.pdbid_list)} PDB files')
        _cwd = os.getcwd()
        os.chdir(self.pdb_save_dir)
        self.pdbfile_list = [PDBFile(os.path.join(self.pdb_save_dir, pdbid + '.pdb'), ligand_id).keep_chain(select_first_lig=True) for pdbid, ligand_id in self.pairs_list]
        os.chdir(_cwd)

    def multi_minimize(self, keep_single_chain:bool=True, num_parallel:int=NUM_PARALLEL, side_chain:bool=True, missing_loop:bool=True, del_water:bool=True, overwrite:bool=False) -> list:
        '''
        使用多进程调用prepwizard 运行多个受体结构的优化
        
        Parameter
        ---------
        keep_single_chain : bool
            是否保留单链
        num_parallel : int
            并行进程数
        overwrite : bool
            是否覆盖已存在的mae文件
        
        Returns
        -------
        list
            优化后的mae文件列表
        '''
        logger.debug(f'Prepare to optimize and minimize {len(self.pairs_list)} structures')

        minimize_save_dir = self.minimize_save_dir
        self.download_all_pdb(overwrite)
        if keep_single_chain:
            self.keep_single_chain()

        self.minimized_file_list = _multiprocssing_run(minimize, self.pdbfile_list, side_chain, missing_loop, del_water, minimize_save_dir, overwrite, job_name='Minimizing Structures', num_parallel=num_parallel)

        return self.minimized_file_list

    def multi_grid_generate(self, gridbox_size:int=20, num_parallel:int=NUM_PARALLEL, overwrite:bool=False) -> list:
        '''
        使用多进程调用Glide 运行多个受体结构的格点文件生成
        
        Parameter
        ---------
        gridbox_size : int
            格点大小
        num_parallel : int
            并行进程数
        overwrite : bool
            是否覆盖已存在的zip文件
        
        Returns
        -------
        list
            生成的网格文件列表
        '''
        pairs_list = self.pairs_list
        logger.debug(f'Prepare to generate grids for {len(pairs_list)} structures')

        _pairs_list = self.minimized_file_list
        grid_save_dir = self.grid_save_dir

        if _pairs_list is None:
            raise FileNotFoundError('No minimized file found. Please run minimize first.')

        self.grid_file_list = _multiprocssing_run(grid_generate, _pairs_list, gridbox_size, grid_save_dir, overwrite, job_name='Generating Grids', num_parallel=num_parallel)
        
        return self.grid_file_list

    def minimized_split(self) -> None:
        '''
        将优化的结构拆分为ligand和protein 保存至相应位置
        '''
        minimized_file_list = self.minimized_file_list
        if minimized_file_list is None:
            raise RuntimeError('No minimized file found. Please run minimize first.')

        logger.debug(f'Prepare to split {len(minimized_file_list)} structures')
        logger.debug(f'Protein file will be saved in {self.protein_save_dir}')
        logger.debug(f'Ligand file will be saved in {self.ligand_save_dir}')
        logger.debug(f'Complex file will be saved in {self.complex_save_dir}')
        # split不进行多进程化
        for minimized_file in minimized_file_list:
            minimized_file.split(protein_dir=self.protein_save_dir, ligand_dir=self.ligand_save_dir, complex_dir=self.complex_save_dir)
    
    def ligand_split(self, external_ligand_file:LigandFile, overwrite:bool=False) -> list:
        '''
        拆分外部ligand文件
        
        Parameter
        ---------
        external_ligand_file : LigandFile
            外部ligand文件
        
        Returns
        -------
        list
            拆分后的ligand文件列表
        '''
        logger.debug(f'Prepare to split {external_ligand_file}')
        ligand_save_dir = self.ligand_save_dir
        self.ligand_path_list = split_ligand(external_ligand_file, ligand_save_dir, overwrite)
        return self.ligand_path_list
        
    def creat_mapping(self, precision:str='SP'):
        '''
        建立映射

        Parameter
        ---------
        precision : str
            计划对接精度
        '''
        if self.ligand_path_list is None:
            raise RuntimeError('Please run ligand_split first.')
        if self.grid_file_list is None:
            raise RuntimeError('Please run grid_generate first.')

        self.ligand_file_list = [LigandFile(ligand_file_path) for ligand_file_path in self.ligand_path_list]
        self.mapping = self._creat_mapping(self.grid_file_list, self.ligand_file_list, self._get_failed_list(precision))
        
    def multi_dock(self, precision:str='SP', calc_rmsd:bool=False, num_parallel:int=NUM_PARALLEL, overwrite:bool=False) -> list:
        '''
        使用多进程调用Glide 执行批量分子对接

        Parameter
        ---------
        precision : str
            分子对接精度
        calc_rmsd : bool
            是否计算rmsd
        num_parallel : int
            并行进程数
        overwrite : bool
            是否覆盖已存在的mae文件
        '''
        logger.debug(f'Grid files in {self.grid_save_dir} will be used.')
        logger.debug(f'Ligand files in {self.ligand_save_dir} will be used.')
        logger.debug(f'Number of all jobs: {len(self.grid_file_list) * len(self.ligand_file_list)}')
        logger.debug(f'Docking precision: {precision}')
        logger.debug(f'Calculate rmsd: {calc_rmsd}')
        logger.debug(f'Number of parallel jobs: {num_parallel}')

        if self.mapping is None:
            raise RuntimeError('Please run creat_mapping first.')
        
        self.dock_file_list = _multiprocssing_run(dock, self.mapping, precision, calc_rmsd, self.base_dock_save_dir, overwrite, job_name='Ensemble Docking', num_parallel=num_parallel)
        
        # Failed check
        total_result = [f'{mapping_item[0].pdbid},{mapping_item[0].internal_ligand},{mapping_item[1].ligand_name}' for mapping_item in self.mapping]
        success_result = [f'{dock_result_item.pdbid},{dock_result_item.internal_ligand_name},{dock_result_item.docking_ligand_name}' for dock_result_item in self.dock_file_list]
        self.docking_failed_list = list(set(total_result) - set(success_result))

        if len(self.docking_failed_list) != 0:
            with open(os.path.join(self.result_save_dir, f'docking_failed_{precision}.csv'), 'w') as f:
                f.write('\n'.join(self.docking_failed_list))
        
    def multi_extract_data(self, precision:str='SP', num_parallel:int=NUM_PARALLEL, overwrite:bool=False) -> list:
        '''
        多进程 提取对接结果数据
        '''
        if self.dock_file_list is None:

            if self.ligand_path_list is None:
                raise RuntimeError('Please run ligand_split first.')
            ligand_name_list = [os.path.basename(ligand_path).split('.')[0] for ligand_path in self.ligand_path_list]

            dockfile_path_list = []
            _failed_list = self._get_failed_list(precision)

            for pdbid, ligid in self.pairs_list:
                for ligand_name in ligand_name_list:
                    # 跳过失败的对接
                    if (pdbid, ligid, ligand_name) in _failed_list:
                        logger.debug(f'Skip extracting data from {pdbid},{ligid},{ligand_name}')
                        continue
                    dockfile_path_list.append(os.path.join(self.base_dock_save_dir, pdbid, f'{pdbid}_{ligid}_glide-dock_{ligand_name}_{precision}.maegz'))
                    
                #dockfile_path_list.extend([os.path.join(self.base_dock_save_dir, pdbid, f'{pdbid}_{ligid}_glide-dock_{ligand}_{precision}.maegz') for ligand in ligand_name_list])
            self.dock_file_list = [DockResultFile(dockresult_file_path) for dockresult_file_path in dockfile_path_list]
        
        total_data_list = _multiprocssing_run(extra_docking_data, self.dock_file_list, job_name='Extract Docking Data', num_parallel=num_parallel)
        
        return total_data_list