"""
配置同步模块（HinokamiDev çatalı: ağ bağlantısı tamamen kaldırıldı）

Upstream bu modülde yapılandırmayı, kazanma oranını ve makine kimliğinden türetilen bir
karmayı Supabase'e yüklüyor, "热门配置" için oradan indiriyordu. Bu çatalda hiçbir şey
gönderilmez ve indirilmez; fonksiyonlar yalnız arayüz bozulmasın diye boş döner.
"""
from ok import TriggerTask
from config_io import (
    _import_config_from_text,
    refresh_task_config_widgets,
)

# 上传间隔（秒）
UPLOAD_INTERVAL = 300  # 5分钟

# 有效数据最低场数（后期用户多了可以改大）
MIN_ROUNDS = 5
SUPPORTED_GAME_LANGUAGES = ("简体中文", "繁体中文")


def _get_version():
    """从 src/config.py 读取当前版本号。"""
    try:
        from src.config import version
        return version
    except Exception:
        return "dev"


def _get_win_rate(task: TriggerTask) -> float:
    """从 task.node_status 读取当前胜率。"""
    ns = getattr(task, 'node_status', None)
    if not ns:
        return 0.0
    total = ns.get('total_rounds', 0)
    success = ns.get('success_rounds', 0)
    if total < MIN_ROUNDS:
        return -1.0  # 数据不足
    return success / total if total > 0 else 0.0


def _should_upload(task: TriggerTask) -> bool:
    """检查是否满足上传条件：
    1. 全局配置"是否上传配置"为 True
    2. 有足够的战斗场数
    """
    try:
        lang_config = task.executor.global_config.get_config('配置上传')
        enabled = lang_config.get('是否上传配置', True)
    except Exception:
        enabled = True
    win_rate = _get_win_rate(task)
    if win_rate < 0:
        task.log_debug(f"[配置同步] 数据不足{MIN_ROUNDS}场，跳过上传")
        return False
    return bool(enabled)


def upload_config(task: TriggerTask, mode: str) -> bool:
    """Bu çatalda yükleme yok: hiçbir veri ağa gönderilmez."""
    return False


def fetch_popular_configs(
    mode: str,
    sort_by: str = "winrate",
    limit: int = 20,
    version: str = None,
) -> list:
    """Bu çatalda indirme yok: ağdan yapılandırma çekilmez."""
    return []

def check_upload_disabled_and_warn(task: TriggerTask) -> bool:
    """检查配置上传是否已关闭，若关闭则弹窗提示并返回 True。"""
    try:
        lang_config = task.executor.global_config.get_config('配置上传')
        upload_enabled = lang_config.get('是否上传配置', True)
    except Exception:
        upload_enabled = True
    if not upload_enabled:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.warning(
            None, "热门配置不可用",
            "请先在左下角设置页中开启「配置上传」功能，才能使用热门配置。\n\n"
            "开启后，您可以浏览和下载其他高胜率玩家分享的配置。"
        )
        return True
    return False


def check_upload_if_needed(task: TriggerTask, mode: str):
    """每 UPLOAD_INTERVAL 秒自动上传一次配置。"""
    import time
    now = time.time()
    if now - getattr(task, '_last_upload_time', 0) >= UPLOAD_INTERVAL:
        task._last_upload_time = now
        upload_config(task, mode)


def show_hot_configs_dialog(task: TriggerTask, mode: str):
    """弹出热门配置选择对话框。
    
    Args:
        task: TriggerTask 实例
        mode: "chaos" 或 "sortie"
    """
    from PySide6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
        QListWidgetItem, QPushButton, QMessageBox, QComboBox, QApplication,
    )
    from PySide6.QtCore import Qt

    if check_upload_disabled_and_warn(task):
        return

    mode_name = "卡厄思模式" if mode == "chaos" else "出击模式"
    dialog = QDialog()
    dialog.setWindowTitle(f"热门配置 - {mode_name}")
    dialog.resize(650, 500)

    layout = QVBoxLayout(dialog)

    # 筛选行：排序方式 + 出战主战员筛选
    filter_layout = QHBoxLayout()
    sort_label = QLabel("排序方式：")
    sort_combo = QComboBox()
    sort_combo.addItem("按胜率降序", "winrate")
    sort_combo.addItem("按使用人数降序", "users")
    filter_layout.addWidget(sort_label)
    filter_layout.addWidget(sort_combo)

    # 语言筛选
    lang_filter_label = QLabel("语言：")
    lang_filter_combo = QComboBox()
    lang_filter_combo.addItem("不限", "")
    filter_layout.addWidget(lang_filter_label)
    filter_layout.addWidget(lang_filter_combo)

    # 成员筛选：出击模式筛选首选主战员，卡厄思模式筛选刷存档主战员
    member_filter_label = QLabel(
        "出战主战员：" if mode == "sortie" else "刷存档主战员："
    )
    member_filter_combo = QComboBox()
    member_filter_combo.addItem("不限", "")
    filter_layout.addWidget(member_filter_label)
    filter_layout.addWidget(member_filter_combo)

    filter_layout.addStretch()
    layout.addLayout(filter_layout)

    # 加载提示
    loading_label = QLabel("正在加载热门配置，请稍候...")
    loading_label.setStyleSheet("color: gray; padding: 20px;")
    loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(loading_label)

    # 列表
    config_list = QListWidget()
    config_list.setVisible(False)
    layout.addWidget(config_list)

    # 按钮
    btn_layout = QHBoxLayout()
    refresh_btn = QPushButton("刷新")
    apply_btn = QPushButton("应用所选配置")
    apply_btn.setEnabled(False)
    cancel_btn = QPushButton("取消")
    btn_layout.addWidget(refresh_btn)
    btn_layout.addStretch()
    btn_layout.addWidget(apply_btn)
    btn_layout.addWidget(cancel_btn)
    layout.addLayout(btn_layout)

    # 缓存所有结果
    all_results = []

    def load_configs():
        nonlocal all_results
        sort_by = sort_combo.currentData()
        all_results = fetch_popular_configs(mode=mode, sort_by=sort_by, limit=200)
        # 更新语言筛选下拉框选项
        current_lang = lang_filter_combo.currentData() or ""
        lang_filter_combo.blockSignals(True)
        lang_filter_combo.clear()
        lang_filter_combo.addItem("不限", "")
        langs = sorted(set(r.get("game_lang", "简体中文") for r in all_results if r.get("game_lang")))
        for lang in langs:
            lang_filter_combo.addItem(lang, lang)
        idx = lang_filter_combo.findData(current_lang)
        if idx >= 0:
            lang_filter_combo.setCurrentIndex(idx)
        lang_filter_combo.blockSignals(False)
        # 更新成员筛选下拉框选项
        if member_filter_combo is not None:
            current_member = member_filter_combo.currentData() or ""
            member_filter_combo.blockSignals(True)
            member_filter_combo.clear()
            member_filter_combo.addItem("不限", "")
            members = sorted(set(r.get("first_member", "") for r in all_results if r.get("first_member")))
            for m in members:
                member_filter_combo.addItem(m, m)
            # 恢复之前选择的筛选项
            idx = member_filter_combo.findData(current_member)
            if idx >= 0:
                member_filter_combo.setCurrentIndex(idx)
            member_filter_combo.blockSignals(False)
        apply_filters()

    def apply_filters():
        filtered = all_results
        # 语言筛选
        selected_lang = lang_filter_combo.currentData()
        if selected_lang:
            filtered = [r for r in filtered if r.get("game_lang", "简体中文") == selected_lang]
        # 成员筛选
        selected_member = member_filter_combo.currentData() if member_filter_combo else ""
        if selected_member:
            filtered = [r for r in filtered if r.get("first_member", "") == selected_member]
        config_list.clear()
        loading_label.setVisible(False)
        if not filtered:
            item = QListWidgetItem("暂无热门配置数据（至少需要5场有效数据才会被统计）")
            config_list.addItem(item)
            return
        for i, r in enumerate(filtered[:20], 1):
            wr = r["avg_win_rate"]
            uc = r["user_count"]
            ver = r.get("config_ver", "?")
            gl = r.get("game_lang", "简体中文")
            fm = r.get("first_member", "")
            if fm:
                member_label = "主战员" if mode == "sortie" else "刷存档主战员"
                text = f"#{i}  胜率: {wr:.0%}  使用人数: {uc}  {member_label}: {fm}  语言: {gl}  版本: {ver}"
            else:
                text = f"#{i}  胜率: {wr:.0%}  使用人数: {uc}  语言: {gl}  版本: {ver}"
            item = QListWidgetItem(text)
            item.setData(0x100, r)  # 36 = Qt.UserRole
            config_list.addItem(item)

    def on_filter_changed():
        loading_label.setVisible(True)
        config_list.setVisible(False)
        load_configs()
        config_list.setVisible(True)

    def on_apply():
        selected = config_list.selectedItems()
        if not selected:
            return
        r = selected[0].data(0x100)
        if not r:
            return
        reply = QMessageBox.question(
            dialog, "确认应用",
            f"将应用所选配置（胜率: {r['avg_win_rate']:.0%}, 使用人数: {r['user_count']}）\n当前配置将被覆盖。\n\n是否继续？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            success = _import_config_from_text(task, r["config_b64"])
            if success:
                QMessageBox.information(dialog, "导入成功", "热门配置已成功应用！")
                refresh_task_config_widgets(task)
                dialog.accept()
            else:
                QMessageBox.warning(dialog, "导入失败", "配置解析失败，请重试。")

    # 绑定事件
    sort_combo.currentIndexChanged.connect(on_filter_changed)
    lang_filter_combo.currentIndexChanged.connect(on_filter_changed)
    if member_filter_combo is not None:
        member_filter_combo.currentIndexChanged.connect(on_filter_changed)
    config_list.itemSelectionChanged.connect(lambda: apply_btn.setEnabled(len(config_list.selectedItems()) > 0))
    refresh_btn.clicked.connect(on_filter_changed)
    apply_btn.clicked.connect(on_apply)
    cancel_btn.clicked.connect(dialog.reject)

    # 初始加载
    loading_label.setVisible(True)
    load_configs()
    config_list.setVisible(True)
    loading_label.setVisible(False)

    dialog.exec_()
