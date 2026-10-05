import unittest

from ok.feature.Box import Box
from src.task.EnhanceEchoTask import EnhanceEchoTask, is_echo_ui_noise


class FakeEnhanceTask:
    """Drives the drop/lock status checks with scripted feature boxes.

    The recording hooks let a test assert the search box covers both sibling
    templates: a sibling template larger than the search area crashes
    cv2.matchTemplate (#1238, #1291).
    """

    def __init__(self, boxes, match_name):
        self.boxes = boxes
        self.match_name = match_name
        self.best_match_calls = []
        self.key_presses = []
        self.fail_reason = ''
        self.config = {
            '必须有双爆': False,
            '双爆出现之前必须全有效词条': False,
            '首条双爆>=': 0,
            '双爆总计>=': 0,
            '有效词条>=': 0,
            '第一条必须为有效词条': False,
            '有效词条': [],
        }
        self.counters = {}

    def get_box_by_name(self, name):
        return self.boxes[name]

    def find_best_match_in_box(self, box, names, threshold=0):
        self.best_match_calls.append((box, names, threshold))
        return Box(0, 0, 1, 1, 0.9, name=self.match_name)

    def next_frame(self):
        """No-op pacing: toast polling advances frames between OCR reads."""

    def info_incr(self, name):
        self.counters[name] = self.counters.get(name, 0) + 1

    def info_get(self, name):
        return self.counters.get(name, 0)

    def info_set(self, name, value):
        """IoT counter store, mirroring the real task's info_tracker."""
        self.counters[name] = value

    def send_key(self, key, after_sleep=0):
        self.key_presses.append(key)

    def log_info(self, *args, **kwargs):
        """No-op: logging is irrelevant to the assertions."""

    def log_debug(self, *args, **kwargs):
        """No-op: logging is irrelevant to the assertions."""

    def screenshot_echo(self, name):
        """No-op: screenshots are irrelevant to the assertions."""

    def screenshot(self, name):
        """No-op: failure screenshots are irrelevant to the assertions."""

    def esc(self):
        """No-op: leaving the screen is irrelevant to the assertions."""

    def wait_ocr(self, *args, **kwargs):
        return None


class FakeSelectTask:
    """Scripts the +0 check after each click on the bag grid.

    3.7 keeps the just-enhanced echo selected (and scrolled into view) when
    returning to the bag, so the task must pick a +0 echo itself.
    """

    targets = {(0.13, 0.21): 'first card', (0.35, 0.917): 'sort order'}

    def __init__(self, zero_level_results):
        self.zero_level_results = list(zero_level_results)
        self.clicks = []

    def click(self, x, y, after_sleep=0):
        self.clicks.append(self.targets[(x, y)])

    def is_0_level(self):
        return self.zero_level_results.pop(0)


def make_lock_task(ocr_results):
    """Scripts the toast OCR: each lock_and_esc poll pops the next page."""
    task = FakeEnhanceTask({}, match_name='')
    scripted = [list(page) for page in ocr_results]

    def ocr(*args, **kwargs):
        page = scripted.pop(0) if scripted else []
        return [Box(0, 0, 1, 1, name=n) for n in page]

    task.ocr = ocr
    return task


class TestEnhanceEchoStatusBox(unittest.TestCase):
    # Sibling templates deliberately differ in size, with the sibling BIGGER
    # than the anchor box: the geometry that crashed the lock pair in
    # #1238/#1291.

    def assertCovers(self, search, template_box):
        self.assertLessEqual(search.x, template_box.x)
        self.assertLessEqual(search.y, template_box.y)
        self.assertGreaterEqual(search.x + search.width,
                                template_box.x + template_box.width)
        self.assertGreaterEqual(search.y + search.height,
                                template_box.y + template_box.height)

    def test_drop_search_box_covers_both_drop_templates(self):
        dropped = Box(534, 152, 28, 26, name='echo_dropped')
        not_dropped = Box(534, 151, 28, 29, name='echo_not_dropped')
        task = FakeEnhanceTask({'echo_dropped': dropped,
                                'echo_not_dropped': not_dropped},
                               match_name='echo_dropped')

        EnhanceEchoTask.trash_and_esc(task)

        [(search, names, threshold)] = task.best_match_calls
        self.assertEqual(names, ['echo_dropped', 'echo_not_dropped'])
        self.assertEqual(threshold, 0.6)
        self.assertCovers(search, dropped)
        self.assertCovers(search, not_dropped)

    def test_lock_presses_once_when_toast_says_locked(self):
        # 真机 2026-09-23 20:34 现场文案: 上锁弹「物品锁定成功」;
        # 「物品上锁成功」不是真机文案, 但保留兼容.
        for wording in ('物品锁定成功', '物品上锁成功'):
            task = make_lock_task([[wording]])

            EnhanceEchoTask.lock_and_esc(task)

            self.assertEqual(task.key_presses, ['c'])
            self.assertEqual(task.counters.get('成功声骸数量'), 1)

    def test_lock_presses_again_after_unlock_toast(self):
        # 声骸原本已锁定: 第 1 按弹「解锁成功」, 第 2 按弹「锁定成功」.
        task = make_lock_task([['物品解锁成功'], ['物品锁定成功']])

        EnhanceEchoTask.lock_and_esc(task)

        self.assertEqual(task.key_presses, ['c', 'c'])
        self.assertEqual(task.counters.get('成功声骸数量'), 1)

    def test_lock_retries_when_toast_missing(self):
        # 游戏 UI 吞首击 (怪癖 #1): 第 1 按整个轮询窗 (15 次) 都无提示,
        # 第 2 按生效.
        task = make_lock_task([[]] * 15 + [['物品锁定成功']])

        EnhanceEchoTask.lock_and_esc(task)

        self.assertEqual(task.key_presses, ['c', 'c'])
        self.assertEqual(task.counters.get('成功声骸数量'), 1)

    def test_lock_failure_raises_after_six_presses(self):
        # 提示条始终无「上锁」→ 6 挡后抛错, 消息带上最后读到的提示文本.
        task = make_lock_task([['物品解锁成功']] + [[]] * 200)

        with self.assertRaisesRegex(Exception, '上锁失败'):
            EnhanceEchoTask.lock_and_esc(task)

        self.assertEqual(len(task.key_presses), 6)

    def test_ui_noise_filtered_from_properties(self):
        # 真机 2026-09-23 15:04:40 现场: OCR 把按钮截断成 '强化至+25并激活辅',
        # 旧守卫('辅音' not in name)因缺字漏网, '强化至' 混入属性列表.
        self.assertTrue(is_echo_ui_noise('强化至+25并激活辅'))
        self.assertTrue(is_echo_ui_noise('强化至+25并激活辅音属性'))
        self.assertTrue(is_echo_ui_noise('强化至'))

    def test_value_pairing_prefers_same_row(self):
        # 同帧两个词条+两个数值: 远处一个数值紧贴第 2 词条行, 也应在同行为先.
        task = FakeEnhanceTask({}, match_name='')
        props = [Box(0, 100, 0, 0, name='暴击'),
                 Box(0, 180, 0, 0, name='共鸣解放伤害加成')]
        values = [Box(90, 101, 0, 0, name='8.1%'),
                  Box(90, 179, 0, 0, name='12.6%')]

        ok = EnhanceEchoTask.check_echo_stats(task, props, values)

        self.assertTrue(ok)
        self.assertEqual(task.last_paired_stats,
                         [('暴击', '8.1%'), ('共鸣解放伤害加成', '12.6%')])

    def test_first_card_is_used_when_it_is_0_level(self):
        task = FakeSelectTask([True])

        self.assertTrue(EnhanceEchoTask.select_0_level_echo(task))

        self.assertEqual(['first card'], task.clicks)

    def test_list_returns_to_top_when_first_visible_card_is_enhanced(self):
        task = FakeSelectTask([False, True])

        self.assertTrue(EnhanceEchoTask.select_0_level_echo(task))

        self.assertEqual(['first card', 'sort order', 'sort order', 'first card'], task.clicks)

    def test_no_0_level_echo_left(self):
        task = FakeSelectTask([False, False])

        self.assertFalse(EnhanceEchoTask.select_0_level_echo(task))

        self.assertEqual(['first card', 'sort order', 'sort order', 'first card'], task.clicks)


if __name__ == '__main__':
    unittest.main()
