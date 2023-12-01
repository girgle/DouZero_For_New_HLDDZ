# -*- coding: utf-8 -*-
# Created by: Raf
# Modify by: Vincentzyx

import GameHelper as gh
from GameHelper import GameHelper
import os
import sys
import time
import threading
import pyautogui
import win32gui
from PIL import Image
import multiprocessing as mp
import DetermineColor as DC
from skimage.metrics import structural_similarity as ssim
from collections import defaultdict
from douzero.env.move_detector import get_move_type
import cv2
import numpy as np

from PyQt5 import QtGui, QtWidgets, QtCore
from PyQt5.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsItem, QGraphicsPixmapItem, QInputDialog, QMessageBox
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtCore import QTime, QEventLoop
from MainWindow import Ui_Form

from douzero.env.game import GameEnv
from douzero.evaluation.deep_agent import DeepAgent
import traceback

import BidModel
import LandlordModel
import FarmerModel

EnvCard2RealCard = {3: '3', 4: '4', 5: '5', 6: '6', 7: '7',
                    8: '8', 9: '9', 10: 'T', 11: 'J', 12: 'Q',
                    13: 'K', 14: 'A', 17: '2', 20: 'X', 30: 'D'}

RealCard2EnvCard = {'3': 3, '4': 4, '5': 5, '6': 6, '7': 7,
                    '8': 8, '9': 9, 'T': 10, 'J': 11, 'Q': 12,
                    'K': 13, 'A': 14, '2': 17, 'X': 20, 'D': 30}

AllEnvCard = [3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5, 6, 6, 6, 6, 7, 7, 7, 7,
              8, 8, 8, 8, 9, 9, 9, 9, 10, 10, 10, 10, 11, 11, 11, 11, 12,
              12, 12, 12, 13, 13, 13, 13, 14, 14, 14, 14, 17, 17, 17, 17, 20, 30]

AllCards = ['D', 'X', '2', 'A', 'K', 'Q', 'J', 'T',
            '9', '8', '7', '6', '5', '4', '3']

helper = GameHelper()
helper.ScreenZoomRate = 1.0  # 请修改屏幕缩放比


class MyPyQT_Form(QtWidgets.QWidget, Ui_Form):
    def __init__(self):
        super(MyPyQT_Form, self).__init__()
        self.stop_sign = None
        self.loop_sign = None
        self.env = None
        self.three_landlord_cards_env = None
        self.three_landlord_cards_real = None
        self.user_hand_cards_env = None
        self.user_hand_cards_real = None
        self.play_order = None
        self.card_play_data_list = None
        self.other_hand_cards = None
        self.other_played_cards_env = None
        self.other_played_cards_real = None
        self.user_position = None
        self.user_position_code = None
        self.setupUi(self)
        self.setWindowFlags(QtCore.Qt.WindowMinimizeButtonHint |  # 使能最小化按钮
                            QtCore.Qt.WindowStaysOnTopHint |  # 窗体总在最前端
                            QtCore.Qt.WindowCloseButtonHint)
        self.setWindowIcon(QIcon(':/favicon.ico'))
        self.setWindowTitle("（新）欢乐斗地主修复版v1.1")
        self.setFixedSize(self.width(), self.height())  # 固定窗体大小
        self.move(240, 100)
        # self.setWindowIcon(QIcon('pics/favicon.ico'))
        window_pale = QtGui.QPalette()
        # window_pale.setBrush(self.backgroundRole(), QtGui.QBrush(QtGui.QPixmap("pics/bg.png")))

        self.setPalette(window_pale)
        self.SingleButton.clicked.connect(self.game_single)
        self.LoopButton.clicked.connect(self.game_loop)
        self.StopButton.clicked.connect(self.stop)

        # self.Players = [self.RPlayer, self.Player, self.LPlayer]
        self.Players = [self.RPlayedCard, self.PredictedCard, self.LPlayedCard]
        self.counter = QTime()

        # 参数
        self.MyConfidence = 0.8  # 我的牌的置信度
        self.OtherConfidence = 0.8  # 别人的牌的置信度
        self.WhiteConfidence = 0.85  # 检测白块的置信度
        self.LandlordFlagConfidence = 0.8  # 检测地主标志的置信度
        self.ThreeLandlordCardsConfidence = 0.8  # 检测地主底牌的置信度
        self.PassConfidence = 0.7

        self.PassConfidence = 0.8
        self.WaitTime = 1  # 等待状态稳定延时
        self.MyFilter = 40  # 我的牌检测结果过滤参数
        self.OtherFilter = 25  # 别人的牌检测结果过滤参数
        self.SleepTime = 0.1  # 循环中睡眠时间
        self.RunGame = False
        self.AutoPlay = False
        self.BidThreshold1 = 65  # 叫地主阈值
        self.BidThreshold2 = 72  # 抢地主阈值
        self.JiabeiThreshold = (
            (85, 72),  # 叫地主 超级加倍 加倍 阈值
            (85, 75)  # 叫地主 超级加倍 加倍 阈值  (在地主是抢来的情况下)
        )
        self.MingpaiThreshold = 92
        # 坐标
        self.MyHandCardsPos = (192, 692, 1448, 221)  # 我的截图区域
        self.LPlayedCardsPos = (400, 428, 472, 170)  # 左边出牌截图区域
        self.RPlayedCardsPos = (889, 428, 475, 170)  # 右边出牌截图区域
        self.LandlordCardsPos = (704, 36, 368, 142)  # 地主底牌截图区域，resize成349x168
        self.LPassPos = (462, 475, 138, 78)  # 左边不出截图区域
        self.RPassPos = (1320, 524, 65, 63)  # 右边不出截图区域

        self.LCardsCorner = (307, 490, 152, 102)  # 左边牌角截图区域
        self.RCardsCorner = (1293, 488, 173, 106)  # 右边牌角截图区域

        self.PassBtnPos = (322, 508, 1124, 213)
        self.LPassPos = (462, 475, 138, 78)  # 左边不出截图区域
        self.RPassPos = (1173, 469, 142, 87)  # 右边不出截图区域
        self.GeneralBtnPos = (357, 596, 1060, 108)
        self.LandlordFlagPos = [(1561, 317, 56, 44), (18, 817, 58, 65), (152, 312, 65, 62)]  # 地主标志截图区域(右-我-左)
        # 信号量
        self.shouldExit = 0  # 通知上一轮记牌结束
        self.canRecord = threading.Lock()  # 开始记牌
        self.card_play_model_path_dict = {
            'landlord': "baselines/resnet/resnet_landlord.ckpt",
            'landlord_up': "baselines/resnet/resnet_landlord_up.ckpt",
            'landlord_down': "baselines/resnet/resnet_landlord_down.ckpt"
        }

    def game_single(self):
        self.loop_sign = 0
        self.stop_sign = 0
        self.detect_start_btn()
        self.before_start()
        self.init_cards()

    def game_loop(self):
        self.loop_sign = 1
        self.stop_sign = 0
        while True:
            if self.stop_sign == 1:
                break
            self.detect_start_btn()
            self.before_start()
            self.init_cards()
            self.sleep(5000)

    def stop(self):
        self.stop_sign = 1
        print("按下停止键")
        try:
            self.RunGame = False
            self.loop_sign = 0

            self.env.game_over = True
            self.env.reset()
            self.init_display()
            self.PreWinrate.setText("局前预估得分: ")
            self.BidWinrate.setText("叫牌预估得分: ")
        except AttributeError as e:
            traceback.print_exc()

    def init_display(self):
        self.WinRate.setText("评分")
        self.label.setText("游戏状态")
        self.label.setStyleSheet('background-color: rgba(255, 0, 0, 0);')
        self.UserHandCards.setText("手牌")
        self.LPlayedCard.setText("上家出牌区域")
        self.RPlayedCard.setText("下家出牌区域")
        self.PredictedCard.setText("AI出牌区域")
        self.ThreeLandlordCards.setText("地主牌")
        for player in self.Players:
            player.setStyleSheet('background-color: rgba(0, 255, 0, 0);')

    def init_cards(self):
        self.RunGame = True
        GameHelper.Interrupt = False
        self.user_hand_cards_real = ""
        self.user_hand_cards_env = []
        # 其他玩家出牌
        self.other_played_cards_real = ""
        self.other_played_cards_env = []
        # 其他玩家手牌（整副牌减去玩家手牌，后续再减掉历史出牌）
        self.other_hand_cards = []
        # 三张底牌
        self.three_landlord_cards_real = ""
        self.three_landlord_cards_env = []
        # 玩家角色代码：0-地主上家, 1-地主, 2-地主下家
        self.user_position_code = None
        self.user_position = ""
        # 开局时三个玩家的手牌
        self.card_play_data_list = {}

        # 识别玩家手牌
        self.user_hand_cards_real = self.find_my_cards()
        self.user_hand_cards_env = [RealCard2EnvCard[c] for c in list(self.user_hand_cards_real)]
        # 识别三张底牌
        self.three_landlord_cards_real = self.find_landlord_cards()
        self.ThreeLandlordCards.setText("底牌：" + self.three_landlord_cards_real)
        self.three_landlord_cards_env = [RealCard2EnvCard[c] for c in list(self.three_landlord_cards_real)]
        while len(self.three_landlord_cards_env) != 3:
            if not self.RunGame:
                break
            if len(self.three_landlord_cards_env) > 3:
                self.ThreeLandlordCardsConfidence += 0.05
                self.sleep(200)
            elif len(self.three_landlord_cards_env) < 3:
                self.ThreeLandlordCardsConfidence -= 0.05
                self.sleep(200)
            self.three_landlord_cards_real = self.find_landlord_cards()
            self.ThreeLandlordCards.setText("底牌：" + self.three_landlord_cards_real)
            self.three_landlord_cards_env = [RealCard2EnvCard[c] for c in list(self.three_landlord_cards_real)]

        # 识别玩家的角色
        self.user_position_code = self.find_landlord(self.LandlordFlagPos)
        self.sleep(200)
        while self.user_position_code is None:
            if not self.RunGame:
                break
            self.user_position_code = self.find_landlord(self.LandlordFlagPos)
            self.sleep(200)

        print("正在出牌人的代码： ", self.user_position_code)
        if self.user_position_code is None:
            items = ("地主上家", "地主", "地主下家")
            item, okPressed = QInputDialog.getItem(self, "选择角色", "未识别到地主，请手动选择角色:", items, 0, False)
            if okPressed and item:
                self.user_position_code = items.index(item)
            else:
                return
        self.user_position = ['landlord_up', 'landlord', 'landlord_down'][self.user_position_code]
        print("我现在在地主的方向：", self.user_position)
        for player in self.Players:
            player.setStyleSheet('background-color: rgba(0, 255, 0, 0);')

        # 整副牌减去玩家手上的牌，就是其他人的手牌,再分配给另外两个角色（如何分配对AI判断没有影响）
        for i in set(AllEnvCard):
            self.other_hand_cards.extend([i] * (AllEnvCard.count(i) - self.user_hand_cards_env.count(i)))
        self.card_play_data_list.update({
            'three_landlord_cards': self.three_landlord_cards_env,
            ['landlord_up', 'landlord', 'landlord_down'][(self.user_position_code + 0) % 3]:
                self.user_hand_cards_env,
            ['landlord_up', 'landlord', 'landlord_down'][(self.user_position_code + 1) % 3]:
                self.other_hand_cards[0:17] if (self.user_position_code + 1) % 3 != 1 else self.other_hand_cards[17:],
            ['landlord_up', 'landlord', 'landlord_down'][(self.user_position_code + 2) % 3]:
                self.other_hand_cards[0:17] if (self.user_position_code + 1) % 3 == 1 else self.other_hand_cards[17:]
        })
        print("开始对局")
        print("手牌:", self.user_hand_cards_real)
        print("地主牌:", self.three_landlord_cards_real)
        # 生成手牌结束，校验手牌数量
        if len(self.card_play_data_list["three_landlord_cards"]) != 3:
            QMessageBox.critical(self, "底牌识别出错", "底牌必须是3张！", QMessageBox.Yes, QMessageBox.Yes)
            self.init_display()
            return
        if len(self.card_play_data_list["landlord_up"]) != 17 or \
                len(self.card_play_data_list["landlord_down"]) != 17 or \
                len(self.card_play_data_list["landlord"]) != 20:
            QMessageBox.critical(self, "手牌识别出错", "初始手牌数目有误", QMessageBox.Yes, QMessageBox.Yes)
            self.init_display()
            return
        # 出牌顺序：0-玩家出牌, 1-玩家下家出牌, 2-玩家上家出牌
        self.play_order = 0 if self.user_position == "landlord" else 1 if self.user_position == "landlord_up" else 2

        # 创建一个代表玩家的AI
        ai_players = [0, 0]
        ai_players[0] = self.user_position
        ai_players[1] = DeepAgent(self.user_position, self.card_play_model_path_dict[self.user_position])

        self.env = GameEnv(ai_players)

        try:
            self.start()
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            print(e)
            traceback.print_tb(exc_tb)
            self.stop()

    def sleep(self, ms):
        self.counter.restart()
        while self.counter.elapsed() < ms:
            QtWidgets.QApplication.processEvents(QEventLoop.AllEvents, 50)

    def start(self):
        # print("现在的出牌顺序是谁：0是我；1是下家；2是上家：", self.play_order)
        self.env.card_play_init(self.card_play_data_list)
        print("开始出牌\n")
        while not self.env.game_over:
            if not self.RunGame:
                break
            if self.play_order == 0:
                self.PredictedCard.setText("...")
                action_message = self.env.step(self.user_position)
                score = float(action_message['win_rate'])
                if "resnet" in self.card_play_model_path_dict[self.user_position]:
                    score *= 8
                self.UserHandCards.setText("手牌：" + str(''.join(
                    [EnvCard2RealCard[c] for c in self.env.info_sets[self.user_position].player_hand_cards]))[::-1])

                self.PredictedCard.setText(action_message["action"] if action_message["action"] else "不出")
                self.PredictedCard.setStyleSheet('background-color: rgba(0, 255, 0, 0.2);')
                self.WinRate.setText("评分：" + action_message["win_rate"])
                print("出牌：", action_message["action"] if action_message["action"] else "不出", "，得分：",
                      action_message["win_rate"])
                print("\n手牌：", str(''.join(
                    [EnvCard2RealCard[c] for c in self.env.info_sets[self.user_position].player_hand_cards])))
                if action_message["action"] == "":
                    tryCount = 5
                    result = helper.LocateOnScreen("pass_btn", region=self.PassBtnPos, confidence=0.7)
                    passSign = helper.LocateOnScreen("pass", region=(838, 597, 222, 106), confidence=0.7)
                    while result is None and passSign is None:
                        if not self.RunGame:
                            break
                        self.detect_start_btn()
                        result = helper.LocateOnScreen("pass_btn", region=self.PassBtnPos, confidence=0.7)
                        passSign = helper.LocateOnScreen("pass", region=(838, 597, 222, 106), confidence=0.7)

                    if result is not None:
                        helper.ClickOnImage("pass_btn", region=self.PassBtnPos, confidence=0.7)
                        self.sleep(200)
                    if passSign is not None:
                        self.sleep(500)
                        # helper.ClickOnImage("pass", region=(838, 597, 222, 106))
                        helper.LeftClick((941, 639))

                    self.sleep(200)
                else:
                    hand_cards_str = ''.join(
                        [EnvCard2RealCard[c] for c in self.env.info_sets[self.user_position].player_hand_cards])

                    # if len(hand_cards_str) >= len(action_message["action"]):
                    self.click_cards(action_message["action"])

                    tryCount = 20
                    result = helper.LocateOnScreen("play_card", region=self.PassBtnPos)
                    while result is None and tryCount > 0:
                        if not self.RunGame:
                            break
                        print("等待出牌按钮")
                        self.detect_start_btn()
                        tryCount -= 1
                        result = helper.LocateOnScreen("play_card", region=self.PassBtnPos)
                        self.sleep(200)
                    if tryCount <= 0 or result is None:
                        print("出牌按钮被挡住")
                        break
                    else:
                        self.sleep(200)
                        helper.ClickOnImage("play_card", region=self.PassBtnPos)
                    ani = self.animation(action_message["action"])
                    if ani:
                        self.sleep(1000)
                    if len(hand_cards_str) == 0:
                        self.RunGame = False
                        self.env.game_over = True
                        break


                self.detect_start_btn()
                self.PredictedCard.setStyleSheet('background-color: rgba(0, 255, 0, 0);')
                self.play_order = 1
                self.sleep(1000)

            elif self.play_order == 1:
                self.RPlayedCard.setText("等待下家出牌")
                self.RPlayer.setStyleSheet('background-color: rgba(0, 255, 0, 0.2);')
                pass_flag = helper.LocateOnScreen('buchu', region=self.RPlayedCardsPos)
                rightCards = self.find_other_cards(self.RPlayedCardsPos)
                self.detect_start_btn()
                while self.RunGame and len(rightCards) == 0 and pass_flag is None:
                    print("等待下家出牌")
                    self.sleep(200)
                    pass_flag = helper.LocateOnScreen('buchu', region=self.RPassPos)
                    rightCards = self.find_other_cards(self.RPlayedCardsPos)
                    self.detect_start_btn()
                self.sleep(50)
                # 未找到"不出"
                if pass_flag is None:
                    # 识别下家出牌
                    # self.RPlayedCard.setText("等待动画")
                    # self.waitUntilNoAnimation()
                    self.RPlayedCard.setText("...")
                    while True:
                        rightOne = self.find_other_cards(self.RPlayedCardsPos)
                        self.sleep(1000)
                        rightTwo = self.find_other_cards(self.RPlayedCardsPos)
                        if rightOne == rightTwo:
                            break
                    self.other_played_cards_real = rightOne

                    ani = self.animation(rightOne)
                    if ani:
                        self.sleep(1500)
                # 找到"不出"
                else:
                    self.other_played_cards_real = ""
                print("\n下家出牌：", self.other_played_cards_real)
                self.detect_start_btn()
                self.other_played_cards_env = [RealCard2EnvCard[c] for c in list(self.other_played_cards_real)]
                self.other_played_cards_env.sort()
                self.env.step(self.user_position, self.other_played_cards_env)
                # 更新界面
                self.RPlayedCard.setText(self.other_played_cards_real if self.other_played_cards_real else "不出")
                self.RPlayer.setStyleSheet('background-color: rgba(0, 255, 0, 0);')
                self.play_order = 2
                self.sleep(500)

            elif self.play_order == 2:
                self.LPlayedCard.setText("等待上家出牌")
                self.LPlayer.setStyleSheet('background-color: rgba(0, 255, 0, 0.2);')
                pass_flag = helper.LocateOnScreen('buchu', region=self.LPlayedCardsPos)
                leftCards = self.find_other_cards(self.LPlayedCardsPos)
                self.detect_start_btn()
                while self.RunGame and len(leftCards) == 0 and pass_flag is None:
                    print("等待上家出牌")
                    self.sleep(200)
                    pass_flag = helper.LocateOnScreen('buchu', region=self.LPlayedCardsPos)
                    leftCards = self.find_other_cards(self.LPlayedCardsPos)
                    self.detect_start_btn()
                self.sleep(50)
                # 不出
                # 未找到"不出"
                if pass_flag is None:
                    # 识别上家出牌
                    # self.LPlayedCard.setText("等待动画")
                    # self.waitUntilNoAnimation()
                    self.LPlayedCard.setText("...")
                    while True:
                        leftOne = self.find_other_cards(self.LPlayedCardsPos)
                        self.sleep(1000)
                        leftTwo = self.find_other_cards(self.LPlayedCardsPos)
                        if leftOne == leftTwo:
                            break
                    self.other_played_cards_real = leftOne

                    ani = self.animation(leftOne)
                    if ani:
                        self.sleep(1500)
                # 找到"不出"
                else:
                    self.other_played_cards_real = ""
                print("\n上家出牌：", self.other_played_cards_real)
                self.detect_start_btn()
                self.other_played_cards_env = [RealCard2EnvCard[c] for c in list(self.other_played_cards_real)]
                self.other_played_cards_env.sort()
                self.env.step(self.user_position, self.other_played_cards_env)
                self.LPlayer.setStyleSheet('background-color: rgba(0, 255, 0, 0);')
                self.play_order = 0

                # 更新界面
                self.LPlayedCard.setText(self.other_played_cards_real if self.other_played_cards_real else "不出")
            self.sleep(100)

        if self.stop_sign == 1 or self.loop_sign == 0:
            self.stop()
        self.label.setText("游戏结束")
        self.label.setStyleSheet('background-color: rgba(255, 0, 0, 0);')
        self.init_display()
        print("{}胜，本局结束!\n".format("农民" if self.env.winner == "farmer" else "地主"))

    def detect_start_btn(self):
        result = helper.LocateOnScreen("continue", region=(1317, 686, 410, 268))
        if result is not None:
            if self.loop_sign == 0:
                print("检测到本局游戏已结束")
                self.label.setText("游戏已结束")
                self.label.setStyleSheet('background-color: rgba(255, 0, 0, 0);')
                self.stop()
                self.RunGame = False
            else:
                helper.ClickOnImage("continue", region=(1317, 686, 410, 268))
                self.sleep(100)
                try:
                    if self.env is not None:
                        self.env.game_over = True
                        self.env.reset()
                    self.init_display()
                    self.PreWinrate.setText("局前预估得分: ")
                    self.BidWinrate.setText("叫牌预估得分: ")
                except AttributeError as e:
                    traceback.print_exc()

        result = helper.LocateOnScreen("start_game", region=(874, 574, 386, 185))
        if result is not None:
            helper.ClickOnImage("start_game", region=(874, 574, 386, 185))
            self.sleep(100)
        result = helper.LocateOnScreen("chacha", region=(1120, 96, 623, 805), confidence=0.7)
        if result is not None:
            helper.ClickOnImage("chacha", region=(1120, 96, 623, 805), confidence=0.7)
            self.sleep(100)

        result = helper.LocateOnScreen("good", region=(481, 673, 841, 267))
        if result is not None:
            helper.ClickOnImage("good", region=(481, 673, 841, 267))
            self.sleep(100)

    def cards_filter(self, location, distance):  # 牌检测结果滤波
        if len(location) == 0:
            return 0
        locList = [location[0][0]]
        poslist = [location[0]]
        count = 1
        for e in location:
            flag = 1  # “是新的”标志
            for have in locList:
                # print(abs(e[0] - have))
                if abs(e[0] - have) <= distance:
                    flag = 0
                    break
            if flag:
                count += 1
                locList.append(e[0])
                poslist.append(e)
        # print(poslist)
        return count, poslist

    def find_cards(self, img, pos, mark="", confidence=0.8):
        cards_real = ""
        D_king = 0
        X_king = 0
        for card in AllCards:
            result = gh.LocateAllOnImage(img, helper.PicsCV[mark + card], region=pos, confidence=confidence)

            if len(result) > 0:
                count, s = self.cards_filter(list(result), 20)
                if card == "X" or card == "D":
                    for a in s:
                        classifier = DC.ColorClassify(debug=True)
                        img1 = img[pos[1]:pos[1] + pos[3], pos[0]:pos[0] + pos[2]]
                        img2 = img1[a[1]:a[1] + a[3] - 50, a[0]:a[0] + 20]  # 注意连着裁切时img不能重名
                        # gh.ShowImg(img2)
                        result = classifier.classify(img2)
                        # print(result)
                        for b in result:
                            if b[0] == "Red":
                                if b[1] > 0.54:
                                    D_king = 1
                                else:
                                    X_king = 1
                else:
                    cards_real += card[0] * count

        if X_king:
            cards_real += "X"
            cards_real = cards_real[-1] + cards_real[:-1]

        if D_king:
            cards_real += "D"
            cards_real = cards_real[-1] + cards_real[:-1]
        return cards_real

    def find_my_cards(self):
        # img = cv2.imread("11.png")
        img, _ = helper.Screenshot()
        img = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)
        my_cards_real = self.find_cards(img, self.MyHandCardsPos, mark="m")
        return my_cards_real

    def find_other_cards(self, pos):
        # img = cv2.imread("2.png")
        img, _ = helper.Screenshot()
        img = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)
        other_cards_real = self.find_cards(img, pos, mark="o")
        return other_cards_real

    def find_landlord_cards(self):
        img, _ = helper.Screenshot()
        img = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)
        landlord__cards_real = self.find_cards(img, self.LandlordCardsPos, mark="z",
                                               confidence=self.ThreeLandlordCardsConfidence)
        return landlord__cards_real

    def my_cards_area(self):
        res1 = helper.LocateOnScreen("top_left_corner", region=self.MyHandCardsPos, confidence=0.7)
        res2 = helper.LocateOnScreen("top_right_corner", region=self.MyHandCardsPos, confidence=0.7)
        while res1 is None or res2 is None:
            if not self.RunGame:
                break
            print("未找到手牌区域")
            self.sleep(500)
            res1 = helper.LocateOnScreen("top_left_corner", region=self.MyHandCardsPos, confidence=0.7)
            res2 = helper.LocateOnScreen("top_right_corner", region=self.MyHandCardsPos, confidence=0.7)

        pos = res1[0] + 15, res1[1] + 10, res2[0] - res1[0] - 100, 200
        return pos

    def click_cards(self, out_cards):
        cards = self.find_my_cards()
        area = self.my_cards_area()
        num = len(cards)
        space = int(area[2] / len(cards))
        pos_list = [(area[0] + i * space, area[1]) for i in range(num)]
        print(cards)

        # 将两个列表合并转为字典
        cards_dict = defaultdict(list)
        for key, value in zip(cards, pos_list):
            cards_dict[key].append(value)
        # 转换为普通的字典
        cards_dict = dict(cards_dict)
        # print(cards_dict)
        for i in out_cards:
            cars_pos = cards_dict[i][-1][0:2]

            # print("准备点击的牌：", cards_dict[i])
            point = cars_pos[0] + 30, cars_pos[1] + 50
            check_white = helper.LocateOnScreen("selected", region=(cars_pos[0] - 20, cars_pos[1] - 30, 100, 40),
                                                confidence=0.7)
            print("检查要出的牌上面有没有牌：", check_white)

            if check_white is None:
                helper.LeftClick(point)
                self.sleep(100)
            else:
                print("腾讯自动提示帮你选牌")
            cards_dict[i].remove(cards_dict[i][-1])
            self.sleep(100)
        self.sleep(200)
        img, _ = helper.Screenshot()
        img = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)
        check_cards = self.find_cards(img, (192, 730, 1448, 200), mark="m")
        for i in out_cards:
            cards = cards.replace(i, "", 1)
        print("检查剩的牌： ", check_cards, "应该剩的牌： ", cards)
        if len(check_cards) < len(cards):
            for m in check_cards:
                cards = cards.replace(m, "", 1)
            print("系统多点的牌： ", cards)
            for n in cards:
                print("字典里还剩的牌： ", cards_dict)
                cars_pos2 = cards_dict[n][-1][0:2]
                # print("准备点击的牌：", cards_dict[i])
                point2 = cars_pos2[0] + 30, cars_pos2[1] + 50
                helper.LeftClick(point2)
                self.sleep(1000)

    def find_landlord(self, landlord_flag_pos):
        tryCount = 3
        self.sleep(200)
        while tryCount > 0:
            if not self.RunGame:
                break
            img, _ = helper.Screenshot()
            img = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2HSV)
            for pos in landlord_flag_pos:
                classifier = DC.ColorClassify(debug=True)
                imgCut = img[pos[1]:pos[1] + pos[3], pos[0]:pos[0] + pos[2]]
                result = classifier.classify(imgCut)
                for b in result:
                    if b[0] == "Orange":
                        if b[1] > 0.7:
                            return landlord_flag_pos.index(pos)
            tryCount -= 1
            self.sleep(200)

    def have_white(self, pos):  # 是否有白块
        img, _ = helper.Screenshot()
        img = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)
        result = helper.LocateOnScreen("white", img=img, region=pos)

        if result is None:
            return 0
        else:
            return 1

    def before_start(self):
        self.RunGame = True
        GameHelper.Interrupt = True
        HaveBid = False
        isTaodou = False
        is_stolen = 0
        in_game = helper.LocateOnScreen("chat", region=(1500, 986, 286, 56), confidence=0.8)

        while self.RunGame and in_game is None:
            self.sleep(1000)
            print("还没进入到游戏中。。。")
            self.label.setText("未进入游戏")
            self.label.setStyleSheet('background-color: rgba(255, 0, 0, 0);')

            if self.loop_sign == 1:
                self.detect_start_btn()
            in_game = helper.LocateOnScreen("chat", region=(1500, 986, 286, 56), confidence=0.8)
        self.detect_start_btn()
        self.sleep(300)
        print(in_game, "进入到游戏中")
        self.label.setText("游戏开始")
        self.label.setStyleSheet('background-color: rgba(255, 0, 0, 0.5);')
        while True:
            if not self.RunGame:
                break
            outterBreak = False
            jiaodizhu_btn = helper.LocateOnScreen("jiaodizhu_btn", region=(584, 590, 244, 122), confidence=0.8)
            qiangdizhu_btn = helper.LocateOnScreen("qiangdizhu_btn", region=(590, 587, 235, 118), confidence=0.8)
            jiabei_btn = helper.LocateOnScreen("jiabei_btn", region=self.GeneralBtnPos)
            self.detect_start_btn()
            while jiaodizhu_btn is None and qiangdizhu_btn is None and jiabei_btn is None:
                if not self.RunGame:
                    break
                self.detect_start_btn()
                print("等待加倍或叫地主")
                self.sleep(100)
                jiaodizhu_btn = helper.LocateOnScreen("jiaodizhu_btn", region=(584, 590, 244, 122), confidence=0.8)
                qiangdizhu_btn = helper.LocateOnScreen("qiangdizhu_btn", region=(590, 587, 235, 118), confidence=0.8)
                jiabei_btn = helper.LocateOnScreen("jiabei_btn", region=self.GeneralBtnPos, confidence=0.8)
            print("jiaodizhu_btn, qiangdizhu_btn ,jiabei_btn", jiaodizhu_btn, qiangdizhu_btn, jiabei_btn)
            if jiabei_btn is None:
                cards = self.find_my_cards()
                cards_str = "".join([card[0] for card in cards])
                self.UserHandCards.setText("手牌：" + cards_str)
                win_rate = BidModel.predict(cards_str)
                if not HaveBid:
                    with open("cardslog.txt", "a") as f:
                        f.write(str(int(time.time())) + " " + cards_str + " " + str(round(win_rate, 2)) + "\n")
                print("预计叫地主胜率：", win_rate)
                self.BidWinrate.setText("叫牌预估胜率：" + str(round(win_rate, 2)) + "%")
                is_stolen = 0
                if jiaodizhu_btn is not None:
                    HaveBid = True
                    if win_rate > self.BidThreshold1:
                        helper.ClickOnImage("jiaodizhu_btn", region=(584, 590, 244, 122), confidence=0.8)
                    else:
                        helper.ClickOnImage("bujiao_btn", region=self.GeneralBtnPos)
                elif qiangdizhu_btn is not None:
                    is_stolen = 1
                    HaveBid = True
                    if win_rate > self.BidThreshold2:
                        helper.ClickOnImage("qiangdizhu_btn", region=(590, 587, 235, 118), confidence=0.8)
                    else:
                        helper.ClickOnImage("buqiang_btn", region=self.GeneralBtnPos)
                else:
                    helper.ClickOnImage("buqiang_btn", region=self.GeneralBtnPos)
                self.sleep(500)
            else:
                self.label.setText("游戏开始")
                self.label.setStyleSheet('background-color: rgba(255, 0, 0, 0.5);')
                upwhite = helper.LocateOnScreen("upwhite", region=(929, 107, 84, 55), confidence=0.8)
                while upwhite is None:
                    if not self.RunGame:
                        break
                    laotou = helper.LocateOnScreen("laotou", region=(761, 45, 255, 100), confidence=0.8)
                    if laotou is not None:
                        self.sleep(100)
                        print("在游戏里，还在抢地主。。。。")
                        self.label.setText("在抢地主")
                        self.label.setStyleSheet('background-color: rgba(255, 0, 0, 0.5);')
                    else:
                        print("底牌现身。。。")
                        self.label.setText("抢完地主")
                        self.label.setStyleSheet('background-color: rgba(255, 0, 0, 0.5);')
                    upwhite = helper.LocateOnScreen("upwhite", region=(929, 107, 84, 55), confidence=0.8)
                    self.sleep(300)

                self.sleep(200)
                llcards = self.find_landlord_cards()

                while len(llcards) != 3:
                    if not self.RunGame:
                        break
                    if len(llcards) > 3:
                        self.ThreeLandlordCardsConfidence += 0.05
                        time.sleep(200)
                    elif len(llcards) < 3:
                        self.ThreeLandlordCardsConfidence -= 0.05
                        time.sleep(200)
                    llcards = self.find_landlord_cards()

                self.ThreeLandlordCards.setText("底牌：" + llcards)
                print("地主牌:", llcards)
                cards = self.find_my_cards()
                cards_str = "".join([card[0] for card in cards])
                self.UserHandCards.setText("手牌：" + cards_str)
                if len(cards_str) == 20:
                    win_rate = LandlordModel.predict(cards_str)
                    self.PreWinrate.setText("局前预估胜率：" + str(round(win_rate, 2)) + "%")
                    print("预估地主胜率:", win_rate)
                else:
                    user_position_code = self.find_landlord(self.LandlordFlagPos)
                    while user_position_code is None:
                        if not self.RunGame:
                            break
                        user_position_code = self.find_landlord(self.LandlordFlagPos)
                        self.sleep(200)
                    user_position = ['up', 'landlord', 'down'][user_position_code]

                    win_rate = FarmerModel.predict(cards_str, llcards, user_position) - 5
                    print("预估农民胜率:", win_rate)
                    self.PreWinrate.setText("局前预估胜率：" + str(round(win_rate, 2)) + "%")

                self.sleep(50)
                if win_rate > self.JiabeiThreshold[is_stolen][0]:
                    chaojijiabei_btn = helper.LocateOnScreen("chaojijiabei_btn", region=self.GeneralBtnPos)
                    if chaojijiabei_btn is not None:
                        helper.ClickOnImage("chaojijiabei_btn", region=self.GeneralBtnPos)
                    else:
                        helper.ClickOnImage("jiabei_btn", region=self.GeneralBtnPos)
                elif win_rate > self.JiabeiThreshold[is_stolen][1]:
                    helper.ClickOnImage("jiabei_btn", region=self.GeneralBtnPos)
                else:
                    helper.ClickOnImage("bujiabei_btn", region=self.GeneralBtnPos)
                    print("点击不加倍！！！！！！！！")

            self.sleep(1000)
            llcards = self.find_landlord_cards()
            self.ThreeLandlordCards.setText("底牌：" + llcards)
            for testCount in range(1, 5):
                if len(llcards) > 3:
                    self.ThreeLandlordCardsConfidence += 0.05
                    self.sleep(1000)
                elif len(llcards) < 3:
                    self.ThreeLandlordCardsConfidence -= 0.05
                    self.sleep(1000)
                llcards = self.find_landlord_cards()
                self.ThreeLandlordCards.setText("底牌：" + llcards)

            self.ThreeLandlordCards.setText("底牌：" + llcards)
            self.UserHandCards.setText("手牌：" + cards_str)
            print("地主牌", llcards)

            if win_rate > self.JiabeiThreshold[is_stolen][0]:
                chaojijiabei_btn = helper.LocateOnScreen("chaojijiabei_btn", region=self.GeneralBtnPos)
                if chaojijiabei_btn is not None:
                    helper.ClickOnImage("chaojijiabei_btn", region=self.GeneralBtnPos)
                else:
                    helper.ClickOnImage("jiabei_btn", region=self.GeneralBtnPos)
            elif win_rate > self.JiabeiThreshold[is_stolen][1]:
                helper.ClickOnImage("jiabei_btn", region=self.GeneralBtnPos)
            else:
                helper.ClickOnImage("bujiabei_btn", region=self.GeneralBtnPos)
                print("点击不加倍！！！！！！！！")
            self.sleep(200)
            if win_rate > self.MingpaiThreshold:
                helper.ClickOnImage("mingpai_btn", region=self.GeneralBtnPos)
            print("等待加倍环节结束")
            break

    def animation(self, cards):
        move_type = get_move_type(self.real_to_env(cards))
        animation_types = {4, 5, 13, 14, 8, 9, 10, 11, 12}
        if move_type["type"] in animation_types or len(cards) >= 6:
            return True

    def waitUntilNoAnimation(self, ms=150):
        ani = self.haveAnimation(ms)
        iter_cnt = 0
        # wait at most (3 * 2 * 150)ms, about 1 sec
        while ani and iter_cnt < 3:
            if not self.RunGame:
                break
            if iter_cnt == 0:
                print("等待动画", end="")
            elif iter_cnt % 2 == 0:
                print(".", end="")
            iter_cnt += 1
            ani = self.haveAnimation(ms)
        if iter_cnt > 0:
            print("\t动画结束", end="")
        print()
        self.sleep(600)

    def haveAnimation(self, waitTime=200):
        regions = [
            (1122, 585, 1122 + 30, 585 + 30),  # 开始游戏右上
            (763, 625, 763 + 30, 625 + 30),  # 自家出牌上方
            (600, 400, 1200, 630),  # 经典玩法新手场 对家使用
            (880, 540, 880 + 20, 540 + 20)  # 炸弹时使用，正中央
        ]
        img, _ = helper.Screenshot()
        # img = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)
        lastImg = img
        for i in range(2):
            self.sleep(waitTime)
            img, _ = helper.Screenshot()
            # img = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)
            for region in regions:
                if not self.compareImage(img.crop(region), lastImg.crop(region)):
                    return True
            lastImg = img

        return False

    def compareImage(self, im1, im2):
        if im1.size != im2.size:
            return False
        size = im1.size
        for y in range(size[1]):
            for x in range(size[0]):
                if im1.getpixel((x, y)) != im2.getpixel((x, y)):
                    return False
        return True

    def real_to_env(self, cards):
        env_card = [RealCard2EnvCard[c] for c in cards]
        env_card.sort()
        return env_card

    """def compare_images(self, image1, image2):
        # 读取图像
        # 将图像转换为灰度图
        gray1 = cv2.cvtColor(np.asarray(image1), cv2.COLOR_RGB2GRAY)

        gray2 = cv2.cvtColor(np.asarray(image2), cv2.COLOR_RGB2GRAY)
        # 计算结构相似性指数
        (score, _) = ssim(gray1, gray2, full=True)
        diff_percentage = (1 - score) * 100  # 不同度百分比

        return round(diff_percentage, 2)"""

    def compare_images(self, image1, image2, position):
        # 读取图像
        # 将图像转换为灰度图
        pic1 = cv2.cvtColor(np.asarray(image1), cv2.COLOR_RGB2BGR)
        pic2 = cv2.cvtColor(np.asarray(image2), cv2.COLOR_RGB2BGR)
        # 计算结构相似性指数
        cutPic = pic2[position[1]:position[1] + position[3], position[0]:position[0] + position[2]]
        result = gh.LocateOnImage(pic1, cutPic,
                                  region=(position[0] - 20, position[1] - 20, position[2] + 40, position[3] + 40))
        return result


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    main = MyPyQT_Form()
    main.show()
    sys.exit(app.exec_())