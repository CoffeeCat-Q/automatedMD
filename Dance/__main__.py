import logging
import os

from pyCADD.Dance.base import Dancer
from pyCADD.ui import UI
from pyCADD.utils.check import check_file

logger = logging.getLogger('pyCADD.Dance.UI')


class UI_Dance(UI):
    '''
    数据处理程序UI
    '''

    def __init__(self, menu_name: str = 'Data Analyzer') -> None:
        super().__init__(menu_name=menu_name)
        self.merged = False
        self.dancer = None
        self.main_options = [
            '1. Read docking data matrix',
            '2. Calculate the arithmetic mean',
            '3. Calculate the geometric mean',
            '4. Calculate the minimum value',
            '5. Calculate the maximum value',
            '6. Calculate Z-score',
            '7. Merge datasets',
            '8. Draw ROC curve and calculate the AUC',
            '9. Draw Scatter',
            '0. Exit'
        ]

    def _print_current_data(self):
        self.clear_info()
        self.create_panel(additional_info='Current datasets: %s' %
                          self.dancer.current_data)

    def run(self, flag):

        if flag == '1':
            default_matrix_file = os.path.abspath('results/matrix.csv')
            if check_file(default_matrix_file):
                if self.get_confirm('Dectected results file: %s \nUse it?' % default_matrix_file):
                    file_path = default_matrix_file
                else:
                    file_path = input('Enter the matrix file path').strip()
            else:
                file_path = input('Enter the matrix file path: ').strip()

            if not check_file(file_path):
                self.create_panel()
                logger.error('File %s not found.' % file_path)
                return

            self.dancer = Dancer(file_path)
            self.create_panel(
                additional_info='Read the matrix file: %s' % file_path)
        else:
            if self.dancer is None:
                self.create_panel()
                logger.error('No matrix dataset read.')
                return

        if flag == '2':
            logger.info('Calculating the arithmetic mean of matrix')
            self.dancer.mean(method='ave')
            logger.info('Arithmetic mean calculate done.')

            self._print_current_data()

        elif flag == '3':
            logger.info('Calculating the geometric mean of matrix')
            self.dancer.mean(method='geo')
            logger.info('Geometric mean calculate done.')

            self._print_current_data()

        elif flag == '4':
            logger.info('Extracting the minimum value')
            self.dancer.min()
            logger.info('Minimum value Extracted.')
            self._print_current_data()

        elif flag == '5':
            logger.info('Extracting the maximum value')
            self.dancer.max()
            logger.info('Maximum value Extracted.')
            self._print_current_data()

        elif flag == '6':
            receptor_ratio = float(
                input('Enter the ratio of receptor z_score: '))
            ligand_ratio = float(input('Enter the ratio of ligand z_score: '))
            total = receptor_ratio + ligand_ratio

            receptor_ratio /= total
            ligand_ratio /= total
            ratio = (receptor_ratio, ligand_ratio)

            logger.info('Calculating Z-score with %s : %s' % ratio)
            self.dancer.z_score(ratio)
            logger.info('Z-score calculate done.')
            self._print_current_data()

        elif flag == '7':
            logger.info('Current data: %s' % self.dancer.current_data)
            if not self.get_confirm('Merge all current data?'):
                _need_merge = input(
                    'Enter the datasets need to be merge(separated by commas): ').split(',')
            else:
                _need_merge = self.dancer.current_data
            logger.info('Merging datasets: %s' % _need_merge)

            data_list = [self.dancer.current_data_dic[index]
                         for index in _need_merge]
            data_list.append(self.dancer.activity_data)
            self.dancer.merge(data_list)
            self.merged = True

            self.create_panel(
                additional_info='Merged datasets: %s' % _need_merge)

        elif flag == '8':
            if not self.merged:
                self.create_panel()
                logger.error('No merged dataset.')
                return

            logger.info('Label column: %s' % self.dancer.label_col)
            labels = list(self.dancer.activity_data.value_counts().index)
            logger.info('Labels in column: %s' % labels)

            pos_label = input(
                'Enter the positive labels(separated by commas): ').split(',')

            # 简易校验
            for label in pos_label:
                if label not in labels:
                    self.create_panel()
                    logger.error('%s is not in the label column.' % label)
                    return
            logger.info('Positive labels: %s' % pos_label)

            ascending = self.get_confirm(
                'Ascending sort(for negative number)?')
            logger.info('Sort by ascending order: %s' % ascending)

            self.dancer.auc(pos_label, True, ascending)
            self.create_panel()
            logger.info('ROC curve image file %s-ROC.jpg saved.' %
                        os.path.basename(os.getcwd()))

        elif flag == '9':

            logger.info('Label column: %s' % self.dancer.label_col)
            labels = list(self.dancer.activity_data.value_counts().index)
            logger.info('Labels in column: %s' % labels)
            pos_label = input(
                'Enter all positive labels(separated by commas): ').split(',')

            # 简易校验
            for label in pos_label:
                if label not in labels:
                    self.create_panel()
                    logger.error('%s is not in the label column.' % label)
                    return
            logger.info('Positive labels: %s' % pos_label)

            score_name = self.get_input(
                'Enter the name of score', default='Docking_Score')
            logger.info('Score Name: %s' % score_name)

            self.dancer.scatter(pos_label, score_name, True)
            self.create_panel()
            logger.info('Scatter plot %s-Scatter.jpg saved.' %
                        os.path.basename(os.getcwd()))


if __name__ == '__main__':
    enter_text = '[bold]Enter the Code of Options'
    ui_dance = UI_Dance()
    ui_dance.create_panel(ui_dance.main_options)

    while True:
        flag = ui_dance.get_input(enter_text, choices=[str(
            i) for i in range(len(ui_dance.main_options))], default='0')
        if flag == '0':
            break

        ui_dance.run(flag)
