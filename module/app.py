from model import test
from module import utils
from module.config import config
from module.mode import LabelMode
from ui.form import Ui_form
from PyQt5.QtCore import pyqtBoundSignal, QCoreApplication, QEvent, QObject, QPoint, QPointF, QRectF, QSize, Qt
from PyQt5.QtGui import QColor, QCursor, QFont, QIcon, QMouseEvent, QPainter, QPen, QPixmap, QResizeEvent
from PyQt5.QtWidgets import QAction, QFileDialog, QGraphicsScene, QInputDialog, QMainWindow, QMenu, QMessageBox, \
                            QStatusBar
from typing import Dict, List, Optional, Set, Tuple


class LabelApp(QMainWindow, Ui_form):
    def __init__(self):
        super().__init__()

        # init UI
        self.setupUi(self)
        self.retranslateUi(self)
        with open('static/style.qss', 'r', encoding='utf-8') as file:
            self.setStyleSheet(file.read())
        self.init_color_box()
        self.color = QColor(config.default_color)
        self.init_action_box()
        self.mode = LabelMode.DEFAULT_MODE
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # init image size
        self.img_size = 1

        # init image
        self.src: Optional[QPixmap] = None
        self.img: Optional[QPixmap] = None
        self.path: Optional[str] = None
        self.ratio_from_old = 1
        self.ratio_to_src = 1

        # init pixel spacing
        self.pixel_spacing: Optional[Tuple[float, float]] = None

        # init events
        self.target_event_type = [QMouseEvent.MouseButtonPress, QMouseEvent.MouseMove, QMouseEvent.MouseButtonRelease]
        self.init_event_connections()

        # init indexs
        self.index_a: Optional[int] = None
        self.index_b: Optional[int] = None
        self.index_c: Optional[int] = None

        # a: index_a - a, color
        self.points: Dict[int, Tuple[QPointF, QColor]] = {}

        # ab: index_a, index_b - color
        self.lines: Dict[Tuple[int, int], QColor] = {}

        # ∠abc: index_a, index_b, index_c - color
        self.angles: Dict[Tuple[int, int, int], QColor] = {}

        # ⊙a, r = ab: index_a, index_b - color
        self.circles: Dict[Tuple[int, int], QColor] = {}

        # init pivots
        self.pivots: Set[int] = set()

        # init highlight
        self.highlight_move_index: Optional[int] = None
        self.highlight_points: Set[int] = set()

        # init right button menu
        self.right_btn_menu = QMenu(self)

        # init image dir
        self.dir: Optional[str] = None

    def init_color_box(self):
        size = self.color_box.iconSize()
        default_index = -1
        index = 0
        for color in config.color_list:
            if color == config.default_color:
                default_index = index
            color_icon = QPixmap(size)
            color_icon.fill(QColor(color))
            self.color_box.addItem(QIcon(color_icon), f'  {color.capitalize()}')
            index += 1
        self.color_box.setCurrentIndex(default_index)

    def init_action_box(self):
        default_index = -1
        index = 0
        for mode in config.action_mode_list:
            if mode == config.default_action_mode:
                default_index = index
            self.action_box.addItem(f'    {config.action_name_list[index]}')
            index += 1
        self.action_box.setCurrentIndex(default_index)

    def init_event_connections(self):
        self.img_view.viewport().installEventFilter(self)
        self.load_img_btn.triggered.connect(self.upload_img)
        self.delete_img_btn.triggered.connect(self.delete_img)
        self.save_img_btn.triggered.connect(self.save_img)
        self.import_btn.triggered.connect(self.import_labels)
        self.export_all_btn.triggered.connect(self.export_all)
        self.export_pivots_btn.triggered.connect(self.export_pivots)
        self.quit_app_btn.triggered.connect(QCoreApplication.instance().quit)
        self.inc_size_btn.triggered.connect(self.inc_img_size)
        self.dec_size_btn.triggered.connect(self.dec_img_size)
        self.reset_size_btn.triggered.connect(self.reset_img_size)
        self.clear_all_btn.triggered.connect(self.clear_labels)
        self.color_box.currentIndexChanged.connect(self.change_color)
        self.action_box.currentIndexChanged.connect(self.switch_mode)
        self.img_size_slider.valueChanged.connect(self.set_img_size_slider)
        self.auto_add_pts_btn.triggered.connect(self.auto_add_points)

    def reset_img(self):
        self.src = None
        self.img = None
        self.path = None
        self.ratio_from_old = 1
        self.ratio_to_src = 1
        self.pixel_spacing = None
        self.patient_info.setMarkdown('')

    def reset_index(self):
        self.index_a = None
        self.index_b = None
        self.index_c = None

    def reset_highlight(self):
        self.highlight_move_index = None
        self.highlight_points.clear()

    def reset_except_img(self):
        self.reset_index()
        self.points.clear()
        self.lines.clear()
        self.angles.clear()
        self.circles.clear()
        self.pivots.clear()
        self.reset_highlight()

    def reset_all(self):
        self.reset_img()
        self.reset_except_img()

    def update_img(self):
        if not self.src:
            self.reset_img()
            return None
        old = self.img if self.img else self.src
        size = QSize(
            (self.img_view.width() - 2 * self.img_view.lineWidth()) * self.img_size,
            (self.img_view.height() - 2 * self.img_view.lineWidth()) * self.img_size
        )
        self.img = self.src.scaled(size, Qt.KeepAspectRatio)
        self.ratio_from_old = self.img.width() / old.width()
        self.ratio_to_src = self.src.width() / self.img.width()

    def update_points(self):
        if not self.img or not self.points or self.ratio_from_old == 1:
            return None
        for point, _ in self.points.values():
            point.setX(point.x() * self.ratio_from_old)
            point.setY(point.y() * self.ratio_from_old)
        self.ratio_from_old = 1

    def get_src_point(self, point: QPointF):
        return QPointF(point.x() * self.ratio_to_src, point.y() * self.ratio_to_src)

    def get_img_point(self, point: QPointF):
        return QPointF(point.x() / self.ratio_to_src, point.y() / self.ratio_to_src)

    def label_points(self, img: Optional[QPixmap], to_src: bool):
        if not img or not self.points:
            return None
        painter = QPainter()
        painter.begin(img)
        painter.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen()
        pen.setCapStyle(Qt.RoundCap)
        pen.setWidthF(config.point_width * (self.ratio_to_src if to_src else 1))
        font = QFont('Consolas')
        font.setPointSizeF(config.font_size * (self.ratio_to_src if to_src else 1))
        painter.setFont(font)
        for index, (point, color) in self.points.items():
            if to_src:
                pen.setColor(color)
                label_point = self.get_src_point(point)
            else:
                pen.setColor(
                    color if index != self.highlight_move_index and index not in self.highlight_points
                    else QColor.lighter(color)
                )
                label_point = point
            painter.setPen(pen)
            painter.drawPoint(label_point)
            painter.drawText(utils.get_index_shift(label_point), str(index))
        painter.end()

    def label_lines(self, img: Optional[QPixmap], to_src: bool):
        if not img or not self.lines:
            return None
        painter = QPainter()
        painter.begin(img)
        painter.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen()
        pen.setCapStyle(Qt.RoundCap)
        pen.setWidthF(config.line_width * (self.ratio_to_src if to_src else 1))
        font = QFont('Consolas')
        font.setPointSizeF(config.font_size * (self.ratio_to_src if to_src else 1))
        painter.setFont(font)
        for (index_a, index_b), color in self.lines.items():
            is_highlight = index_a in self.highlight_points and index_b in self.highlight_points \
                          and (self.mode == LabelMode.ANGLE_MODE or self.mode == LabelMode.VERTICAL_MODE)
            pen.setColor(QColor.lighter(color) if is_highlight else color)
            painter.setPen(pen)
            a = self.points[index_a][0]
            b = self.points[index_b][0]
            src_a = self.get_src_point(a)
            src_b = self.get_src_point(b)
            label_a = src_a if to_src else a
            label_b = src_b if to_src else b
            painter.drawLine(label_a, label_b)
            real_a = src_a
            real_b = src_b
            if self.pixel_spacing:
                real_a = QPointF(src_a.x() * self.pixel_spacing[0], src_a.y() * self.pixel_spacing[1])
                real_b = QPointF(src_b.x() * self.pixel_spacing[0], src_b.y() * self.pixel_spacing[1])
            painter.drawText(
                utils.get_distance_shift(a, b, utils.get_midpoint(label_a, label_b)),
                str(round(utils.get_distance(real_a, real_b), 2)) + ('mm' if self.pixel_spacing else 'px')
            )
        painter.end()

    def label_angles(self, img: Optional[QPixmap], to_src: bool):
        if not img or not self.angles:
            return None
        painter = QPainter()
        painter.begin(img)
        painter.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen()
        pen.setCapStyle(Qt.RoundCap)
        pen.setWidthF(config.angle_width * (self.ratio_to_src if to_src else 1))
        font = QFont('Consolas')
        font.setPointSizeF(config.font_size * (self.ratio_to_src if to_src else 1))
        painter.setFont(font)
        for (index_a, index_b, index_c), color in self.angles.items():
            pen.setColor(color)
            painter.setPen(pen)
            a = self.points[index_a][0]
            b = self.points[index_b][0]
            c = self.points[index_c][0]
            d, e = utils.get_diag_points(self.points[index_a][0], b, c)
            f = utils.get_arc_midpoint(a, b, c)
            label_d = self.get_src_point(d) if to_src else d
            label_e = self.get_src_point(e) if to_src else e
            label_rect = QRectF(label_d, label_e)
            label_a = self.get_src_point(b) if to_src else b
            label_b = self.get_src_point(f) if to_src else f
            deg = utils.get_degree(a, b, c)
            painter.drawArc(label_rect, int(utils.get_begin_degree(a, b, c) * 16), int(deg * 16))
            painter.drawText(utils.get_degree_shift(label_a, label_b), str(round(deg, 2)) + '°')
        painter.end()

    def label_circles(self, img: Optional[QPixmap], to_src: bool):
        if not img or not self.circles:
            return None
        painter = QPainter()
        painter.begin(img)
        painter.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen()
        pen.setCapStyle(Qt.RoundCap)
        pen.setWidthF(config.line_width if not to_src else config.line_width * self.ratio_to_src)
        for (index_a, index_b), color in self.circles.items():
            is_highlight = index_a in self.highlight_points and index_b in self.highlight_points \
                          and self.mode == LabelMode.CIRCLE_MODE
            pen.setColor(QColor.lighter(color) if is_highlight else color)
            painter.setPen(pen)
            a = self.points[index_a][0]
            b = self.points[index_b][0]
            painter.drawEllipse(
                utils.get_min_bounding_rect(a, b) if not to_src
                else utils.get_min_bounding_rect(self.get_src_point(a), self.get_src_point(b))
            )
        painter.end()

    def update_labels(self, img: Optional[QPixmap], to_src: bool):
        self.label_points(img, to_src)
        self.label_lines(img, to_src)
        self.label_angles(img, to_src)
        self.label_circles(img, to_src)

    def update_img_view(self):
        scene = QGraphicsScene()
        if self.img:
            scene.addPixmap(self.img)
        self.img_view.setScene(scene)

    def update_pivots_info(self):
        if not self.img or not self.points or not self.pivots:
            self.pivots_info.setMarkdown('')
            return None
        pivots = list(self.pivots)
        pivots.sort()
        md_info = ''
        for index in pivots:
            point = self.get_src_point(self.points[index][0])
            md_info += f'{index}: ({round(point.x(), 2)}, {round(point.y(), 2)})\n\n'
        self.pivots_info.setMarkdown(md_info)

    def update_all(self):
        self.update_img()
        self.update_points()
        self.update_labels(self.img, False)
        self.update_img_view()
        self.update_pivots_info()

    def resizeEvent(self, _: QResizeEvent):
        self.update_all()

    def get_point_index(self, point: QPointF):
        if not self.img or not self.points:
            return None
        distance = config.point_width - config.eps
        index = None
        for idx, (pt, _) in self.points.items():
            if (dis := utils.get_distance(point, pt)) < distance:
                distance = dis
                index = idx
        return index

    def is_point_out_of_bound(self, point: QPointF):
        return point.x() < config.point_width / 2 or point.x() > self.img.width() - config.point_width / 2 \
               or point.y() < config.point_width / 2 or point.y() > self.img.height() - config.point_width / 2

    def get_index_cnt(self):
        return len([i for i in (self.index_a, self.index_b, self.index_c) if i])

    def trigger_index(self, index: int):
        if not self.img or not self.points or not index:
            return None
        if index in (self.index_a, self.index_b, self.index_c):
            indexs = [i for i in (self.index_a, self.index_b, self.index_c) if i != index]
            self.index_a = indexs[0]
            self.index_b = indexs[1]
            self.index_c = None
            self.highlight_points.remove(abs(index))
        else:
            indexs = [i for i in (self.index_a, self.index_b, self.index_c) if i]
            indexs.append(index)
            while len(indexs) < 3:
                indexs.append(None)
            self.index_a = indexs[0]
            self.index_b = indexs[1]
            self.index_c = indexs[2]
            self.highlight_points.add(abs(index))

    def end_trigger(self):
        self.reset_index()
        self.reset_highlight()

    def end_trigger_with(self, index: int):
        self.end_trigger()
        self.highlight_move_index = index

    def get_new_index(self):
        return max(self.points.keys() if self.points else [0]) + 1

    def add_new_point(self, point: QPointF):
        if self.img:
            index = self.get_new_index()
            self.points[index] = point, self.color
            return index

    def add_line(self, index_a: int, index_b: int):
        if self.img and index_a in self.points and index_b in self.points:
            self.lines[utils.get_line_key(index_a, index_b)] = self.color

    def add_angle(self, index_a: int, index_b: int, index_c: int):
        if self.img and utils.get_line_key(index_a, index_b) in self.lines \
                and utils.get_line_key(index_b, index_c) in self.lines:
            self.angles[utils.get_angle_key(index_a, index_b, index_c)] = self.color

    def add_circle(self, index_a: int, index_b: int):
        if self.img and index_a in self.points and index_b in self.points:
            self.circles[(index_a, index_b)] = self.color

    def erase_point(self, index: int):
        if index not in self.points:
            return None
        self.points.pop(index)
        for line in list(self.lines.keys()):
            if index in line:
                self.lines.pop(line)
        for angle in list(self.angles.keys()):
            if index in angle:
                self.angles.pop(angle)
        for circle in list(self.circles.keys()):
            if index in circle:
                self.circles.pop(circle)
        self.pivots.discard(index)

    def erase_highlight(self):
        for index in (self.index_a, self.index_b, self.index_c):
            if index and index < 0:
                self.erase_point(-index)
        self.reset_index()
        self.reset_highlight()
        self.update_all()

    def handle_point_mode(self, evt: QMouseEvent):
        if evt.type() != QMouseEvent.MouseButtonPress or evt.button() != Qt.LeftButton:
            return None
        point = self.img_view.mapToScene(evt.pos())
        if index := self.get_point_index(point):
            self.points[index] = self.points[index][0], self.color
        else:
            self.add_new_point(point)
        self.update_all()

    def handle_line_mode(self, evt: QMouseEvent):
        if evt.type() != QMouseEvent.MouseButtonPress or evt.button() != Qt.LeftButton:
            return None
        point = self.img_view.mapToScene(evt.pos())
        index = self.get_point_index(point)
        self.trigger_index(index if index else -self.add_new_point(point))
        if self.get_index_cnt() == 2:
            index_a = abs(self.index_a)
            index_b = abs(self.index_b)
            self.add_line(index_a, index_b)
            self.end_trigger_with(index_b)
        self.update_all()

    def handle_angle_mode(self, evt: QMouseEvent):
        if evt.type() != QMouseEvent.MouseButtonPress or evt.button() != Qt.LeftButton:
            return None
        self.trigger_index(self.get_point_index(self.img_view.mapToScene(evt.pos())))
        if self.get_index_cnt() == 2 and utils.get_line_key(self.index_a, self.index_b) not in self.lines:
            self.trigger_index(self.index_a)
        elif self.get_index_cnt() == 3:
            if utils.get_line_key(self.index_b, self.index_c) in self.lines:
                self.add_angle(self.index_a, self.index_b, self.index_c)
                self.end_trigger_with(self.index_c)
            else:
                index_c = self.index_c
                self.end_trigger()
                self.trigger_index(index_c)
        self.update_all()

    def handle_circle_mode(self, evt: QMouseEvent):
        point = self.img_view.mapToScene(evt.pos())
        if evt.type() == QMouseEvent.MouseButtonPress and evt.button() == Qt.LeftButton:
            if self.get_index_cnt() == 0:
                index = self.get_point_index(point)
                self.trigger_index(index if index else -self.add_new_point(point))
                self.trigger_index(
                    -self.add_new_point(QPointF(point.x() + 2 * config.eps, point.y() + 2 * config.eps))
                )
                self.add_circle(abs(self.index_a), abs(self.index_b))
            elif self.get_index_cnt() == 2:
                self.end_trigger_with(abs(self.index_b))
        elif evt.type() == QMouseEvent.MouseMove and self.get_index_cnt() == 2 \
                and not self.is_point_out_of_bound(point):
            index_b = abs(self.index_b)
            self.points[index_b][0].setX(point.x())
            self.points[index_b][0].setY(point.y())
        self.update_all()

    def handle_midpoint_mode(self, evt: QMouseEvent):
        if evt.type() != QMouseEvent.MouseButtonPress or evt.button() != Qt.LeftButton:
            return None
        self.trigger_index(self.get_point_index(self.img_view.mapToScene(evt.pos())))
        if self.get_index_cnt() == 2:
            if utils.get_line_key(self.index_a, self.index_b) in self.lines:
                a = self.points[self.index_a][0]
                b = self.points[self.index_b][0]
                self.add_new_point(utils.get_midpoint(a, b))
                self.end_trigger_with(self.index_b)
            else:
                self.trigger_index(self.index_a)
        self.update_all()

    def handle_vertical_mode(self, evt: QMouseEvent):
        if evt.type() != QMouseEvent.MouseButtonPress or evt.button() != Qt.LeftButton:
            return None
        self.trigger_index(self.get_point_index(self.img_view.mapToScene(evt.pos())))
        if self.get_index_cnt() == 2:
            if utils.get_line_key(self.index_a, self.index_b) not in self.lines:
                self.trigger_index(self.index_a)
        elif self.get_index_cnt() == 3:
            a = self.points[self.index_a][0]
            b = self.points[self.index_b][0]
            c = self.points[self.index_c][0]
            if utils.is_on_a_line(a, b, c):
                if utils.get_line_key(self.index_b, self.index_c) in self.lines:
                    self.trigger_index(self.index_a)
                else:
                    index_c = self.index_c
                    self.end_trigger()
                    self.trigger_index(index_c)
            else:
                d = utils.get_foot_point(a, b, c)
                index_d = self.add_new_point(d)
                if not utils.is_on_segment(a, b, d):
                    self.add_line(
                        (self.index_a if utils.get_distance(a, d) < utils.get_distance(b, d) else self.index_b),
                        index_d
                    )
                self.add_line(self.index_c, index_d)
                self.end_trigger_with(self.index_c)
            self.update_all()

    def handle_drag_mode(self, evt: QMouseEvent):
        point = self.img_view.mapToScene(evt.pos())
        if evt.type() == QMouseEvent.MouseButtonPress and evt.button() == Qt.LeftButton and self.get_index_cnt() == 0:
            self.trigger_index(self.get_point_index(point))
        elif evt.type() == QMouseEvent.MouseMove and self.get_index_cnt() == 1 \
                and not self.is_point_out_of_bound(point):
            self.points[self.index_a][0].setX(point.x())
            self.points[self.index_a][0].setY(point.y())
        elif evt.type() == QMouseEvent.MouseButtonRelease and self.get_index_cnt() == 1:
            self.trigger_index(self.index_a)
        self.update_all()

    def handle_erase_point_mode(self, evt: QMouseEvent):
        if evt.type() == QMouseEvent.MouseButtonPress and evt.button() == Qt.LeftButton:
            self.erase_point(self.get_point_index(self.img_view.mapToScene(evt.pos())))
        self.update_all()

    def handle_highlight_move(self, evt: QMouseEvent):
        point = self.img_view.mapToScene(evt.pos())
        self.highlight_move_index = self.get_point_index(point)
        point = self.get_src_point(point)
        text = f'坐标：{round(point.x(), 2)}, {round(point.y(), 2)}'
        self.status_bar.showMessage(text, 1000)
        self.update_all()

    def modify_index(self, index: int):
        new_index, modify = QInputDialog.getInt(self, '更改标号', '请输入一个新的标号', index, 0, step=1)
        if not modify or new_index == index:
            return None
        if new_index <= 0:
            self.warning('标号必须为正整数！')
            return None
        if new_index in self.points:
            self.warning('此标号已存在！')
            return None
        self.points[new_index] = self.points[index]
        self.points.pop(index)
        for line in list(self.lines.keys()):
            if index in line:
                fixed_index = line[0] + line[1] - index
                self.lines[utils.get_line_key(new_index, fixed_index)] = self.lines[line]
                self.lines.pop(line)
        for angle in list(self.angles.keys()):
            if index in angle:
                if index == angle[1]:
                    self.angles[angle[0], new_index, angle[2]] = self.angles[angle]
                else:
                    fixed_index = angle[0] + angle[2] - index
                    self.angles[utils.get_angle_key(new_index, angle[1], fixed_index)] = self.angles[angle]
                self.angles.pop(angle)
        for circle in list(self.circles.keys()):
            if index in circle:
                key = (new_index, circle[1]) if index == circle[0] else (circle[0], new_index)
                self.circles[key] = self.circles[circle]
                self.circles.pop(circle)
        if index in self.pivots:
            self.pivots.remove(index)
            self.pivots.add(new_index)

    def add_pivots(self, index: int):
        if self.img and index in self.points:
            self.pivots.add(index)

    def remove_pivots(self, index: int):
        if self.img and self.pivots:
            self.pivots.discard(index)

    def switch_pivot_state(self, index: int):
        self.remove_pivots(index) if index in self.pivots else self.add_pivots(index)

    def create_right_btn_menu(self, index: int, point: QPointF):
        self.right_btn_menu = QMenu(self)
        modify_index = QAction('更改标号', self.right_btn_menu)
        modify_index_triggered: pyqtBoundSignal = modify_index.triggered
        modify_index_triggered.connect(lambda: self.modify_index(index))
        switch_pivot_state = QAction('删除该点信息' if index in self.pivots else '查看该点信息', self.right_btn_menu)
        switch_pivot_state_triggered: pyqtBoundSignal = switch_pivot_state.triggered
        switch_pivot_state_triggered.connect(lambda: self.switch_pivot_state(index))
        erase_point = QAction('清除该点', self.right_btn_menu)
        erase_point_triggered: pyqtBoundSignal = erase_point.triggered
        erase_point_triggered.connect(lambda: self.erase_point(index))
        self.right_btn_menu.addAction(modify_index)
        self.right_btn_menu.addAction(switch_pivot_state)
        self.right_btn_menu.addAction(erase_point)
        self.right_btn_menu.exec(QPoint(int(point.x()), int(point.y())))

    def handle_right_btn_menu(self, evt: QMouseEvent):
        if index := self.get_point_index(self.img_view.mapToScene(evt.pos())):
            self.erase_highlight()
            self.highlight_move_index = index
            self.update_all()
            global_pos = evt.globalPos()
            self.create_right_btn_menu(index, QPointF(float(global_pos.x()), float(global_pos.y())))
            self.highlight_move_index = self.get_point_index(
                self.img_view.mapToScene(self.img_view.mapFromParent(self.mapFromParent(QCursor.pos())))
            )
            self.update_all()

    def eventFilter(self, obj: QObject, evt: QEvent):
        if not self.img or obj is not self.img_view.viewport() or evt.type() not in self.target_event_type:
            return super().eventFilter(obj, evt)
        # noinspection PyTypeChecker
        evt = QMouseEvent(evt)
        if self.mode == LabelMode.POINT_MODE:
            self.handle_point_mode(evt)
        elif self.mode == LabelMode.LINE_MODE:
            self.handle_line_mode(evt)
        elif self.mode == LabelMode.ANGLE_MODE:
            self.handle_angle_mode(evt)
        elif self.mode == LabelMode.CIRCLE_MODE:
            self.handle_circle_mode(evt)
        elif self.mode == LabelMode.MIDPOINT_MODE:
            self.handle_midpoint_mode(evt)
        elif self.mode == LabelMode.VERTICAL_MODE:
            self.handle_vertical_mode(evt)
        elif self.mode == LabelMode.MOVE_POINT_MODE:
            self.handle_drag_mode(evt)
        elif self.mode == LabelMode.ERASE_POINT_MODE:
            self.handle_erase_point_mode(evt)
        if evt.type() == QMouseEvent.MouseMove:
            self.handle_highlight_move(evt)
        elif evt.type() == QMouseEvent.MouseButtonPress and QMouseEvent(evt).button() == Qt.RightButton:
            self.handle_right_btn_menu(evt)
        return super().eventFilter(obj, evt)

    def warning(self, text: str):
        QMessageBox.warning(self, '警告', text)

    # DICOM (*.dcm)
    def load_dcm_img(self, path: str):
        if utils.is_file_readable(path):
            self.src, md_info, self.pixel_spacing = utils.get_dcm_img_with_info(path)
            self.path = utils.rename_path_ext(path, '.jpg')
            self.patient_info.setMarkdown(md_info)
            self.update_all()
        else:
            self.warning('Dicom 文件不存在或不可读！')

    # JPEG (*.jpg;*.jpeg;*.jpe), PNG (*.png)
    def load_img(self, path: str):
        if utils.is_file_readable(path):
            self.src = QPixmap()
            self.src.load(path)
            self.path = path
            self.update_all()
        else:
            self.warning('图片文件不存在或不可读！')

    def upload_img(self):
        caption = '新建'
        init_dir = self.dir if self.dir else utils.get_home_img_dir()
        ext_filter = 'DICOM (*.dcm);;JPEG (*.jpg;*.jpeg;*.jpe);;PNG (*.png)'
        dcm_filter = 'DICOM (*.dcm)'
        path, img_ext = QFileDialog.getOpenFileName(self, caption, init_dir, ext_filter, dcm_filter)
        if not path:
            return None
        self.reset_all()
        self.load_dcm_img(path) if img_ext == dcm_filter else self.load_img(path)
        self.dir = utils.get_parent_dir(path)

    def delete_img(self):
        if not self.src:
            self.warning('请先新建一个项目！')
            return None
        self.reset_all()
        self.update_all()

    def save_img(self):
        if not self.src:
            self.warning('请先新建一个项目！')
            return None
        img = self.src.copy()
        self.erase_highlight()
        self.update_labels(img, True)
        caption = '保存'
        ext_filter = 'JPEG (*.jpg;*.jpeg;*.jpe);;PNG (*.png)'
        init_filter = 'JPEG (*.jpg;*.jpeg;*.jpe)'
        path, _ = QFileDialog.getSaveFileName(self, caption, self.path, ext_filter, init_filter)
        if path:
            img.save(path)

    def import_labels(self):
        if not self.img:
            self.warning('请先新建一个项目！')
            return None
        caption = '导入'
        init_path = utils.rename_path_ext(self.path, '.json')
        json_filter = 'JSON (*.json)'
        path, _ = QFileDialog.getOpenFileName(self, caption, init_path, json_filter)
        if not path:
            return None
        if not utils.is_file_readable(path):
            self.warning('JSON 文件不存在或不可读！')
        if data := utils.load_from_json(path):
            self.reset_except_img()
            if len(data) == 1:
                pivots: List[Tuple[int, float, float]] = data['pivots']
                for index, x, y in pivots:
                    self.points[index] = self.get_img_point(QPointF(x, y)), self.color
                    self.pivots.add(index)
            else:
                points: List[Tuple[int, float, float, str]] = data['points']
                for index, x, y, color in points:
                    self.points[index] = self.get_img_point(QPointF(x, y)), QColor(color)
                lines: List[Tuple[int, int, str]] = data['lines']
                for index_a, index_b, color in lines:
                    self.lines[utils.get_line_key(index_a, index_b)] = QColor(color)
                angles: List[Tuple[int, int, int, str]] = data['angles']
                for index_a, index_b, index_c, color in angles:
                    self.angles[utils.get_angle_key(index_a, index_b, index_c)] = QColor(color)
                circles: List[Tuple[int, int, str]] = data['circles']
                for index_a, index_b, color in circles:
                    self.circles[(index_a, index_b)] = QColor(color)
                self.pivots = set(data['pivots'])
            self.update_all()

    def export_all(self):
        if not self.img:
            self.warning('请先新建一个项目！')
            return None
        caption = '导出全部'
        init_path = utils.rename_path_ext(self.path, '.json')
        json_filter = 'JSON (*.json)'
        path, _ = QFileDialog.getSaveFileName(self, caption, init_path, json_filter)
        if not path:
            return None
        if utils.is_file_exists(path) and not utils.is_file_writable(path):
            self.warning('JSON 文件不可读！')
            return None
        data = dict(points=[], lines=[], angles=[], circles=[], pivots=[])
        points: List[Tuple[int, float, float, str]] = data['points']
        for index, point in self.points.items():
            src_point = self.get_src_point(point[0])
            points.append((index, src_point.x(), src_point.y(), point[1].name()))
        lines: List[Tuple[int, int, str]] = data['lines']
        for index, color in self.lines.items():
            lines.append((index[0], index[1], color.name()))
        angles: List[Tuple[int, int, int, str]] = data['angles']
        for index, color in self.angles.items():
            angles.append((index[0], index[1], index[2], color.name()))
        circles: List[Tuple[int, int, str]] = data['circles']
        for index, color in self.circles.items():
            circles.append((index[0], index[1], color.name()))
        data['pivots'] = list(self.pivots)
        utils.save_json_file(data, path)

    def export_pivots(self):
        if not self.img:
            self.warning('请先新建一个项目！')
            return None
        caption = '导出关键点'
        init_path = utils.rename_path_ext(self.path, '_pivots.json')
        json_filter = 'JSON (*.json)'
        json_path, _ = QFileDialog.getSaveFileName(self, caption, init_path, json_filter)
        if not json_path:
            return None
        if utils.is_file_exists(json_path) and not utils.is_file_writable(json_path):
            self.warning('JSON 文件不可读！')
            return None
        data = dict(pivots=[])
        pivots: List[Tuple[int, float, float]] = data['pivots']
        for index in self.pivots:
            point = self.get_src_point(self.points[index][0])
            pivots.append((index, point.x(), point.y()))
        utils.save_json_file(data, json_path)

    def inc_img_size(self):
        size = min(int(self.img_size * 100 + 10), 200)
        self.img_size_slider.setValue(size)
        self.img_size = size / 100
        self.img_size_label.setText(f'大小：{size}%')
        self.update_all()

    def dec_img_size(self):
        size = max(int(self.img_size * 100 - 10), 50)
        self.img_size_slider.setValue(size)
        self.img_size = size / 100
        self.img_size_label.setText(f'大小：{size}%')
        self.update_all()

    def reset_img_size(self):
        size = 100
        self.img_size_slider.setValue(size)
        self.img_size = size / 100
        self.img_size_label.setText(f'大小：{size}%')
        self.update_all()

    def clear_labels(self):
        if not self.img:
            return None
        self.reset_except_img()
        self.update_all()

    def change_color(self):
        self.color = QColor(config.color_list[self.color_box.currentIndex()])

    def switch_mode(self):
        self.erase_highlight()
        self.mode = config.action_mode_list[self.action_box.currentIndex()]

    def set_img_size_slider(self):
        size = self.img_size_slider.value()
        self.img_size = size / 100
        self.img_size_label.setText(f'大小：{size}%')
        self.update_all()

    def add_real_point(self, index, x: float, y: float):
        if self.img:
            self.points[index] = self.get_img_point(QPointF(x, y)), self.color

    def add_new_real_point(self, x: float, y: float):
        index = self.get_new_index()
        self.add_real_point(index, x, y)
        return index

    # add_real_point(index, x, y) or add_new_real_point(x, y)
    '''
    ----------> x
    |
    |
    |
    ↓
    y
    '''
    def auto_add_points(self):
        if not self.src:
            self.warning('请先新建一个项目！')
            return None
        cv2_img = utils.get_cv2_img(self.src)
        points = test.auto_get_points(cv2_img)
        for point in points:
            index = self.add_new_real_point(point[0], point[1])
            self.add_pivots(index)
        self.update_all()
