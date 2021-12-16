import logging

from pyCADD.ui import UI

try:
    from pyCADD.VSW import register
    from pyCADD.VSW.base import VSW
except ImportError:
    import os
    os.system('run python3 -m pip install rich ConcurrentLogHandler')

    from pyCADD.VSW import register
    from pyCADD.VSW.base import VSW

logger = logging.getLogger('pyCADD.VSW')


class UI_VSW(UI):
    '''
    虚拟筛选UI
    '''

    def __init__(self, menu_name: str = 'VSW') -> None:
        super().__init__(menu_name=menu_name)
        self.vsw = VSW()
        self.gene = ''
        self.database = ''
        self.main_options = [
            '1. Select Gene',
            '2. Select Database',
            '3. Create input file for VSW',
            '4. Run Virtual Screening Workflow (VSW)',
            '5. Regist Gene',
            '6. Regist database',
            '7. Delete Gene from registed list',
            '8. Delete database from registed list',
            '0. Exit'
        ]

    def get_gene(self) -> None:
        '''
        打印当前基因信息并获取用户指定的VSW基因
        '''

        _options = self.vsw.genelist
        self.create_panel(_options, options_label='Registed Gene')
        self.gene = self.vsw.get_gene()
        self.vsw.get_receptor_list()
        self.create_panel(additional_info='Current Gene: %s' %
                          self.gene, show_panel=False)
        self.create_panel(additional_info='Current Gene PDB list: %s' %
                          self.vsw.pdblist, show_panel=False)

    def get_database(self) -> None:
        '''
        打印当前化合物库信息并获取用户指定的化合物库名称
        '''
        _options = self.vsw.database_list
        self.create_panel(_options, options_label='Registed Database')
        self.database = self.vsw.select_database()
        self.create_panel(additional_info='Current Database: %s' %
                          self.database, show_panel=False)

    def run(self, flag) -> None:
        if flag == '1':
            self.get_gene()
            self.create_panel(self.main_options)

        elif flag == '2':
            self.get_database()
            self.create_panel(self.main_options)

        elif flag == '3':
            if not self.gene:
                logger.error('No Gene selected.')
                return
            elif not self.database:
                logger.error('No database selected.')
                return

            self.inputfile = self.vsw.generate_input_file()
            self.create_panel(
                additional_info='Current input file: %s' % self.inputfile)

        elif flag == '4':
            if not self.inputfile:
                logger.error('No input file created.')
                return

            self.vsw.optimize()
            self.vsw.split()
            self.vsw.grid_generate()
            self.vsw.run()
            logger.info('VSW job completed.')
            self.create_panel()

        elif flag == '5':
            gene_name = input('Enter the gene name: ').strip()
            pdbids_path = input(
                'Enter the PDBID list file path of %s: ' % gene_name)
            family = 'GENE'

            register.reg_gene(gene_name, family, pdbids_path)
            self.create_panel()

        elif flag == '6':
            database_name = input('Enter the database name: ').strip()
            database_path = input(
                'Enter the structure file path of %s: ' % database_name)
            label = 'DATABASE'

            register.reg_database(database_name, label, database_path)
            self.create_panel()

        elif flag == '7':
            gene_name = input('Enter the gene name: ').strip()
            family = 'GENE'
            register.del_gene(gene_name, family)
            self.create_panel()

        elif flag == '8':
            database_name = input('Enter the database name: ').strip()
            label = 'DATABASE'
            register.del_database(database_name, label)
            self.create_panel()


if __name__ == '__main__':

    enter_text = '[bold]Enter the Code of Options'
    ui_vsw = UI_VSW()
    ui_vsw.create_panel(ui_vsw.main_options)
    while True:
        flag = ui_vsw.get_input(enter_text, choices=[
                                str(i) for i in range(0, 9)], default='0')
        if flag == '0':
            break
        ui_vsw.run(flag)
