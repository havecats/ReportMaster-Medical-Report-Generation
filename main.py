# IMPORT / GUI AND MODULES AND WIDGETS
# ///////////////////////////////////////////////////////////////
# from PyQt5.QtGui import QIcon #删除了pyqt5
# from PyQt5.QtWidgets import QMainWindow, QHeaderView, QApplication #删除了pyqt5


from PySide6.QtGui import QIcon #删除了pyqt5
from PySide6.QtWidgets import QMainWindow, QHeaderView, QApplication, QWidget, QLineEdit, QMessageBox #删除了pyqt5

from modules import *

import  os
import sys
import tester
import cv2
import time

from modules.ui_login import Ui_login
import database
os.environ["QT_FONT_DPI"] = "110" # FIX Problem for High DPI and Scale above 100%

# SET AS GLOBAL WIDGETS
# ///////////////////////////////////////////////////////////////
widgets = None

class MainWindow(QMainWindow):
    def __init__(self):
        QMainWindow.__init__(self)

        # SET AS GLOBAL WIDGETS
        # ///////////////////////////////////////////////////////////////
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        global widgets
        widgets = self.ui

        # USE CUSTOM TITLE BAR | USE AS "False" FOR MAC OR LINUX
        # ///////////////////////////////////////////////////////////////
        Settings.ENABLE_CUSTOM_TITLE_BAR = True

        # APP NAME
        # ///////////////////////////////////////////////////////////////
        title = "ReportMaster"
        description = "ReportMaster - Medical report generation system."
        # APPLY TEXTS
        self.setWindowTitle(title)
        widgets.titleRightInfo.setText(description)

        # TOGGLE MENU
        # ///////////////////////////////////////////////////////////////
        widgets.toggleButton.clicked.connect(lambda: UIFunctions.toggleMenu(self, True))

        # SET UI DEFINITIONS
        # ///////////////////////////////////////////////////////////////
        UIFunctions.uiDefinitions(self)

        # QTableWidget PARAMETERS
        # ///////////////////////////////////////////////////////////////
        widgets.tableWidget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        # BUTTONS CLICK
        # ///////////////////////////////////////////////////////////////

        # LEFT MENUS
        widgets.btn_home.clicked.connect(self.buttonClick)
        # widgets.btn_widgets.clicked.connect(self.buttonClick)
        widgets.btn_report.clicked.connect(self.buttonClick)
        widgets.btn_history.clicked.connect(self.buttonClick)
        # 切换主题
        widgets.btn_theme.clicked.connect(self.buttonClick)

        # 报告生成
        widgets.btn_open.clicked.connect(self.openFile)
        widgets.btn_generate.clicked.connect(self.generate)
        widgets.btn_translate.clicked.connect(self.translate_reports)
        widgets.btn_copy.clicked.connect(self.copy_report)
        widgets.btn_clean.clicked.connect(self.clean_report)


        # EXTRA LEFT BOX
        def openCloseLeftBox():
            UIFunctions.toggleLeftBox(self, True)
        widgets.toggleLeftBox.clicked.connect(openCloseLeftBox)
        widgets.extraCloseColumnBtn.clicked.connect(openCloseLeftBox)

        # EXTRA RIGHT BOX
        def openCloseRightBox():
            UIFunctions.toggleRightBox(self, True)
        widgets.settingsTopBtn.clicked.connect(openCloseRightBox)

        # SHOW APP
        # ///////////////////////////////////////////////////////////////
        # self.show()

        # SET CUSTOM THEME
        # ///////////////////////////////////////////////////////////////
        #路径冻结，防止打包成exe后路径错乱
        if getattr(sys, 'frozen', False):
            absPath = os.path.dirname(os.path.abspath(sys.executable))
        elif __file__:
            absPath = os.path.dirname(os.path.abspath(__file__))
        useCustomTheme = False
        themeFile = os.path.abspath(os.path.join(absPath, "themes\light.qss"))

        self.useCustomTheme = useCustomTheme
        self.absPath = absPath
        # SET THEME AND HACKS
        if useCustomTheme:
            # LOAD AND APPLY STYLE
            UIFunctions.theme(self, themeFile, True)

            # SET HACKS
            # AppFunctions.setThemeHack(self)

        # SET HOME PAGE AND SELECT MENU
        # ///////////////////////////////////////////////////////////////
        widgets.stackedWidget.setCurrentWidget(widgets.home)
        widgets.btn_home.setStyleSheet(UIFunctions.selectMenu(widgets.btn_home.styleSheet()))

    def openFile(self):
        widgets.label_loading.setText('请上传胸片')
        pathTuple= QFileDialog.getOpenFileName(self, '打开文件', './', '图片 (*.jpg *.png *.bmp)')
        self.path = pathTuple[0]

        image_label = widgets.label_image
        pix = QPixmap(self.path).scaled(image_label.size(), aspectMode=Qt.KeepAspectRatio) #自适应尺寸
        image_label.setPixmap(pix)
        image_label.repaint()

        widgets.label_loading.setText('请点击开始生成')

        # print(self.path) #'D:/coding/Jupyter/Medical-Report-Generation-OntheAutomaticGeneration/data/images/CXR1000_IM-0003-1001.png'

    def set_cam(self):
        image_label = widgets.label_image
        pix = QPixmap('./data/images/cam/'+self.path.split('/')[-1]+'/0.png').scaled(image_label.size(), aspectMode=Qt.KeepAspectRatio)  # 自适应尺寸
        image_label.setPixmap(pix)
        image_label.repaint()

    def generate(self):
        widgets.label_loading.setText('生成中')


        pix = QPixmap('./images/images/loading.gif').scaled(widgets.label_loading.size(), aspectMode=Qt.KeepAspectRatio)  # 自适应尺寸
        widgets.label_loading.setPixmap(pix)
        widgets.label_loading.repaint()

        img = cv2.imread(self.path, 1)
        save_image_path = 'data/images'
        image_name = self.path.split('/')[-1]
        # save_image_path = os.path.join(save_image_path, str(time.strftime('%m%d_%H%M')+'.png'))
        save_image_path = os.path.join(save_image_path, image_name)
        cv2.imwrite(save_image_path, img)

        model = widgets.combo_model.currentText()
        result = tester.test_generate(model, save_image_path)

        widgets.label_loading.setPixmap(QPixmap(''))
        widgets.label_loading.repaint()

        widgets.label_loading.setText('生成完成')

        pred_tags = ''
        if result[image_name]['Pred Tags'][0] == 'normal':
            pred_tags = 'normal'
        else:
            j=0
            for i in result[image_name]['Pred Tags']:
                pred_tags = pred_tags + i + ', '
                j = j+1
                if j>=5:
                    break


        pred_sent = ''
        for i in result[image_name]['Pred Sent'].values():
            pred_sent = pred_sent + i +', '
        widgets.report.setPlainText('tags:'+pred_tags+' ;reports:'+pred_sent)
        self.set_cam()


    def translate_reports(self):
        def youdao_translate(query, from_lang='AUTO', to_lang='AUTO'):
            import requests as r
            url = 'http://fanyi.youdao.com/translate'
            data = {
                "i": query,  # 待翻译的字符串
                "from": from_lang,
                "to": to_lang,
                "smartresult": "dict",
                "client": "fanyideskweb",
                "salt": "16081210430989",
                "doctype": "json",
                "version": "2.1",
                "keyfrom": "fanyi.web",
                "action": "FY_BY_CLICKBUTTION"
            }
            res = r.post(url, data=data).json()
            return res['translateResult'][0][0]['tgt']

        report_text = widgets.report.toPlainText()
        # print(type(report_text))

        trans_text = youdao_translate(report_text)
        # print(trans_text)
        widgets.report.setPlainText(trans_text)

    def copy_report(self):
        import pyperclip
        report_text = widgets.report.toPlainText()
        # os.system('echo '+report_text+' | clip')
        pyperclip.copy(report_text)

    def clean_report(self):
        widgets.report.setPlainText('')
        widgets.label_image.setPixmap(QPixmap(''))
        widgets.label_image.repaint()
        widgets.label_loading.setText('')

    # BUTTONS CLICK
    # Post here your functions for clicked buttons
    # ///////////////////////////////////////////////////////////////
    def buttonClick(self):
        # GET BUTTON CLICKED
        btn = self.sender()
        btnName = btn.objectName()

        # SHOW HOME PAGE
        if btnName == "btn_home":
            widgets.stackedWidget.setCurrentWidget(widgets.home)
            UIFunctions.resetStyle(self, btnName)
            btn.setStyleSheet(UIFunctions.selectMenu(btn.styleSheet()))

        # # SHOW WIDGETS PAGE
        # if btnName == "btn_widgets":
        #     widgets.stackedWidget.setCurrentWidget(widgets.widgets)
        #     UIFunctions.resetStyle(self, btnName)
        #     btn.setStyleSheet(UIFunctions.selectMenu(btn.styleSheet()))

        # SHOW NEW PAGE
        if btnName == "btn_report":
            widgets.stackedWidget.setCurrentWidget(widgets.new_page) # SET PAGE
            UIFunctions.resetStyle(self, btnName) # RESET ANOTHERS BUTTONS SELECTED
            btn.setStyleSheet(UIFunctions.selectMenu(btn.styleSheet())) # SELECT MENU

        if btnName == "btn_history":
            widgets.stackedWidget.setCurrentWidget(widgets.history_page)  # SET PAGE
            UIFunctions.resetStyle(self, btnName)  # RESET ANOTHERS BUTTONS SELECTED
            btn.setStyleSheet(UIFunctions.selectMenu(btn.styleSheet()))  # SELECT MENU

        if btnName == 'btn_theme':
            if self.useCustomTheme:
                themeFile = os.path.abspath(os.path.join(self.absPath, "themes/dark.qss"))
                UIFunctions.theme(self, themeFile, True)
                #set hacks
                # AppFunctions.setThemeHack(self)
                self.useCustomTheme = False
            else:
                themeFile = os.path.abspath(os.path.join(self.absPath, "themes/light.qss"))
                UIFunctions.theme(self, themeFile, True)
                # set hacks
                # AppFunctions.setThemeHack(self)
                self.useCustomTheme = True

        # PRINT BTN NAME
        print(f'Button "{btnName}" pressed!')


    # RESIZE EVENTS
    # ///////////////////////////////////////////////////////////////
    def resizeEvent(self, event):
        # Update Size Grips
        UIFunctions.resize_grips(self)

    # MOUSE CLICK EVENTS
    # ///////////////////////////////////////////////////////////////
    def mousePressEvent(self, event):
        # SET DRAG POS WINDOW
        self.dragPos = event.globalPos()

        # PRINT MOUSE EVENTS
        if event.buttons() == Qt.LeftButton:
            print('Mouse click: LEFT CLICK')
        if event.buttons() == Qt.RightButton:
            print('Mouse click: RIGHT CLICK')

class LoginWindow(QMainWindow):
    def __init__(self):
        QMainWindow.__init__(self)

        # SET AS GLOBAL WIDGETS
        # ///////////////////////////////////////////////////////////////
        self.ui = Ui_login()
        self.ui.setupUi(self)
        global widgets
        widgets = self.ui

        # USE CUSTOM TITLE BAR | USE AS "False" FOR MAC OR LINUX
        # ///////////////////////////////////////////////////////////////
        Settings.ENABLE_CUSTOM_TITLE_BAR = True

        widgets.line_password.setEchoMode(QLineEdit.Password)
        # BUTTONS CLICK
        # ///////////////////////////////////////////////////////////////
        widgets.btn_login.clicked.connect(self.login_or)
        widgets.btn_signup.clicked.connect(self.signup_or)
        # SHOW APP
        # ///////////////////////////////////////////////////////////////
        # self.show()


    # BUTTONS CLICK
    # Post here your functions for clicked buttons
    # ///////////////////////////////////////////////////////////////
    def buttonClick(self):
        # GET BUTTON CLICKED
        btn = self.sender()
        btnName = btn.objectName()

        # SHOW HOME PAGE
        # if btnName == "btn_home":
        #     widgets.stackedWidget.setCurrentWidget(widgets.home)
        #     UIFunctions.resetStyle(self, btnName)
        #     btn.setStyleSheet(UIFunctions.selectMenu(btn.styleSheet()))

        # PRINT BTN NAME
        print(f'Button "{btnName}" pressed!')


    def login_or(self):
        """登录功能实现"""
        username = self.ui.line_username.text()
        password = self.ui.line_password.text()
        db = database.Database('./data.db')
        data = db.find_password_by_username(username)  # 在数据库中查找数据
        if username and password:  # 如果两个输入框都不为空
            if data:
                if str(data[0][0]) == password:
                    # QMessageBox.information(self, 'Successfully', 'Login in successful \n Welcome {}'.format(username),
                    #                         QMessageBox.Yes | QMessageBox.No)
                    self.ui.line_username.setText('')  # 登录成功，将之前的用户信息清除
                    self.ui.line_password.setText('')
                    self.close()
                    if username == 'admin':  # 如果是管理员，进入管理界面
                        # self.admin_win.show()
                        pass
                    else:
                        mainwindow = MainWindow()
                        mainwindow.show()

                else:
                    QMessageBox.information(self, 'Failed', '密码错误，请再次输入',
                                            QMessageBox.Yes)
            else:
                QMessageBox.information(self, 'Error', '用户不存在', QMessageBox.Yes)
        elif username:  # 如果用户名写了
            QMessageBox.information(self, 'Error', '请输入密码', QMessageBox.Yes)
        else:
            QMessageBox.information(self, 'Error', '请输入用户名和密码', QMessageBox.Yes)
    def signup_or(self):
        """注册功能实现"""
        username = self.ui.line_username.text()
        password = self.ui.line_password.text()
        db = database.Database('./data.db')
        data = db.find_password_by_username(username)  # 在数据库中查找数据
        if username and password:  # 如果两个输入框都不为空
            if data:
                QMessageBox.information(self, 'Error', '用户已存在', QMessageBox.Yes)
            else:
                db.insert_table(username, password)
                QMessageBox.information(self, 'Info', '注册成功', QMessageBox.Yes)
        elif username:  # 如果用户名写了
            QMessageBox.information(self, 'Error', '请输入密码', QMessageBox.Yes)
        else:
            QMessageBox.information(self, 'Error', '请输入用户名和密码', QMessageBox.Yes)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon("icon.ico"))

    login = LoginWindow()
    login.show()
    #
    # window = MainWindow()
    #
    # login.ui.btn_login.clicked.connect(login.login_or(window))

    sys.exit(app.exec())
