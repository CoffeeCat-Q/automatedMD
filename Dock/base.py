from pyCADD.utils import getinfo, check
from pyCADD.Dock import core
from pyCADD.Dock import data
from schrodinger.protein.getpdb import get_pdb

import os
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
log_dir = base_dir + '/logs'

from datetime import datetime
date = datetime.now()
year = str(date.year)
month = str(date.month)
day = str(date.day)
now = year + month.rjust(2, '0') + day.rjust(2, '0')

# 配置log
import logging
logger = logging.getLogger('pyCADD')
logger.setLevel(level = logging.INFO)
file_fmt = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_fmt = logging.Formatter('%(levelname)s - %(message)s')

filehandler = logging.FileHandler(log_dir + '/%s.log' % now, 'a')
filehandler.setLevel(logging.INFO)
filehandler.setFormatter(file_fmt)
consolehandler = logging.StreamHandler()
consolehandler.setLevel(logging.INFO)
consolehandler.setFormatter(console_fmt)

logger.addHandler(filehandler)
logger.addHandler(consolehandler)

class Docker:

    '''
    Script Core For Schrodinger Suite Analysis 
    Version 1.12

    Author: YH. W
    Last Update: 2021/11/26
        
    Parameters
    ----------
    pdbid : str
        PDB ID
    ligname : str
        配体文件PATH

    '''
    def __init__(self) -> None:

        self.pdbid = getinfo.get_pdbid()

        if not os.path.exists(self.pdbid + '.pdb'):
            get_pdb(self.pdbid)

        self.pdbfile = check.check_chain(self.pdbid + '.pdb')
        self.ligname = getinfo.get_ligname(self.pdbid)

        self.precision = 'SP'                       # 默认对接精度SP
        self.calc_rmsd = False                      # 默认不计算RMSD

        self.minimized_file = ''                    # Minimized化完成的文件名
        self.grid_file = ''                         # 格点文件名
        self.lig_file = ''                          # 内源配体文件名
        self.recep_file = ''                        # 受体文件名
        self.dock_file = ''                         # 对接结果文件名
        self.mmgbsa_file = ''                       # 结合能计算结果文件名
        self.sitemap_file = ''                      # 结合口袋体积计算结果文件名
        self.admet_file = ''                        # ADMET计算结果文件名

        self.data_dic = {}                          # 一般计算结果字典
        self.admet_dic = {}                         # ADMET计算结果字典
    
    def minimize(self):
        '''
        优化晶体并执行OPLS3能量最小化
        '''

        self.minimized_file = core.minimize(self.pdbfile)

    def split(self):
        '''
        拆分复合结构
        '''

        split = core.split_com(self.minimized_file, self.ligname)
        self.lig_file = split[0]
        self.recep_file = split[1]
    
    def grid_generate(self, gridbox_size=20):
        '''
        生成格点文件
        '''
        self.grid_file = core.grid_generate(self.pdbid, self.ligname, self.minimized_file, gridbox_size)
    
    def set_precision(self, precision:str):
        '''
        设定对接精度
        '''
        self.precision = precision

    def set_calc_rmsd(self, flag:bool):
        '''
        设定是否计算RMSD
        '''
        self.calc_rmsd = flag

    def dock(self, lig_file:str=None):
        '''
        对接
        '''
        if not lig_file:
            lig_file = self.lig_file
        self.dock_file = core.dock(lig_file, self.grid_file, self.precision, self.calc_rmsd)
    
    def cal_volume(self):
        '''
        计算口袋体积
        '''
        self.sitemap_file = core.cal_volume(self.recep_file, self.lig_file)
    
    def cal_mmgbsa(self, dock_file:str=None):
        '''
        计算MMGBSA结合能
        '''
        if not dock_file:
            dock_file = self.dock_file

        self.mmgbsa_file = core.cal_mmgbsa(dock_file)
    
    def cal_admet(self, lig_file_path=None):
        '''
        计算ADMET性质
        '''
        if not lig_file_path:
            lig_file_path = self.lig_file

        self.admet_file = core.cal_admet(lig_file_path)

    def extra_data(self):
        '''
        提取一般性计算数据
        '''
        if self.mmgbsa_file:
            dock_file = self.mmgbsa_file
        else:
            dock_file = self.dock_file

        self.data_dic = data.extra_data(dock_file)
        self._temp_ligname = dock_file.split('_')[4]
        return self.data_dic
    
    def extra_admet_data(self):
        '''
        提取ADMET计算数据
        '''
        self.admet_dic = data.extra_admet_data(self.admet_file)
        self._temp_admet_ligname = self.admet_file.split('.')[0].split('_')[-2]
        return self.admet_dic

    def save_data(self):
        '''
        保存一般性计算数据
        '''
        data.save_data(self.data_dic, self.pdbid, self._temp_ligname, self.precision)
    
    def save_admet_data(self):
        '''
        保存ADMET数据文件
        '''
        data.save_admet_data(self.admet_dic, self._temp_admet_ligname)

    

    
