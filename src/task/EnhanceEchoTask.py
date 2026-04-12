# EnhanceEchoTask.py
import re
import time
import os
import zlib
import threading
import requests
import json
import traceback

from qfluentwidgets import FluentIcon

from ok import FindFeature, Logger
from ok.util.file import clear_folder
from src.scene.WWScene import WWScene
from src.task.BaseWWTask import BaseWWTask

logger = Logger.get_logger(__name__)

number_pattern = re.compile(r"^[\d.%％ ]+$")
property_pattern = re.compile(r"[\u4e00-\u9fff]{2,}")


def safe_sync_to_echo_sight(echo_stats_pairs, status="completed", cost_class=4, main_stat_key="crit_rate", nickname=None, echo_id=None):
    def worker():
        try:
            stat_map = {
                "暴击伤害": "crit_dmg", "暴击": "crit_rate",
                "大攻击": "atk_pct", "小攻击": "atk_flat", "攻击": "atk_flat", "攻击百分比": "atk_pct",
                "大生命": "hp_pct", "小生命": "hp_flat", "生命": "hp_flat", "生命百分比": "hp_pct",
                "大防御": "def_pct", "小防御": "def_flat", "防御": "def_flat", "防御百分比": "def_pct",
                "共鸣效率": "energy_regen",
                "普攻伤害加成": "basic_dmg",
                "重击伤害加成": "heavy_dmg",
                "共鸣解放伤害加成": "liberation_dmg",
                "共鸣技能伤害加成": "skill_dmg",
                "治疗效果加成": "healing_bonus", "冷凝伤害加成": "glacio_dmg", "热熔伤害加成": "fusion_dmg", "导电伤害加成": "electro_dmg", "气动伤害加成": "aero_dmg", "衍射伤害加成": "spectro_dmg", "湮灭伤害加成": "havoc_dmg"
            }
            
            substats = []
            for i, (prop_name_raw, prop_val) in enumerate(echo_stats_pairs):
                cleaned_val = prop_val.replace('%', '').replace('％', '').strip()
                val_float = float(cleaned_val) if cleaned_val.replace('.', '', 1).isdigit() else 0.0
                has_pct = '%' in prop_val or '％' in prop_val
                
                cleaned_name = prop_name_raw.replace(" ", "")
                if '攻击' in cleaned_name and cleaned_name != '攻击百分比':
                    cleaned_name = '攻击百分比' if has_pct else '攻击'
                elif '生命' in cleaned_name and cleaned_name != '生命百分比':
                    cleaned_name = '生命百分比' if has_pct else '生命'
                elif '防御' in cleaned_name and cleaned_name != '防御百分比':
                    cleaned_name = '防御百分比' if has_pct else '防御'

                mapped_key = stat_map.get(cleaned_name, cleaned_name)
                
                if has_pct:
                    val_scaled = int(val_float * 10)
                else:
                    val_scaled = int(val_float)
                
                substats.append({
                    "slot_no": i + 1,
                    "stat_key": mapped_key,
                    "value_scaled": val_scaled
                })

              
            local_main_stat = main_stat_key
            if local_main_stat in ["攻击", "生命", "防御"]:
                local_main_stat = local_main_stat + "百分比"
            parsed_main_stat = stat_map.get(local_main_stat.replace(" ", ""), "crit_rate") if local_main_stat else "crit_rate"

            payload = {
                "echo_id": echo_id if echo_id else f"auto_enh_{int(time.time()*1000)}",
                "main_stat_key": parsed_main_stat,
                "cost_class": int(cost_class) if str(cost_class).isdigit() else 4, 
                "status": status,
                "opened_slots_count": len(substats),
                "substats": substats
            }
            if nickname:
                payload["nickname"] = nickname
            
            logger.debug(f"[EchoSync] 准备发送声骸推送数据: {json.dumps(payload, ensure_ascii=False)}")
            res = requests.post("http://127.0.0.1:8192/api/sync_echo", json=payload, timeout=1.0)
            if res.status_code == 200:
                logger.info("[EchoSync] 成功推送到 WuWa_Echo_Sight")
            else:
                logger.warning(f"[EchoSync] 推送失败，返回: {res.text}")
        except requests.exceptions.ConnectionError:
            logger.debug("[EchoSync] 同步服务未开启(Connection Refused)")
        except requests.exceptions.Timeout:
            logger.warning("[EchoSync] 同步服务响应超时!")
        except Exception as e:
            logger.error(f"[EchoSync] 未知错误: {e}")
    
    t = threading.Thread(target=worker, daemon=True)
    t.start()

class EnhanceEchoTask(BaseWWTask, FindFeature):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "批量强化声骸(游戏与okww语言必须为简体/繁体中文)"
        self.description = "点击B进入背包, 在过滤器中选择需要强化的声骸, 并按照等级从0排序后开始."
        self.icon = FluentIcon.ADD
        self.group_name = "强化声骸"
        self.group_icon = FluentIcon.ADD
        self.fail_reason = ""
        self.supported_languages = ["zh_CN", "zh_TW"]
        self.default_config.update({
            '必须有双爆': True,
            '双爆出现之前必须全有效词条': True,
            '双爆总计>=': 13.8,
            '首条双爆>=': 6.9,
            '有效词条>=': 3,
            '第一条必须为有效词条': True,
            '有效词条': ['暴击', '暴击伤害', '攻击百分比'],
            '同步到EchoSight': True
        })
        self.config_type["有效词条"] = {'type': "multi_selection",
                                        'options': ['暴击伤害', '暴击', '攻击百分比', '生命百分比', '防御百分比',
                                                    '攻击', '生命', '防御',
                                                    '共鸣效率', '普攻伤害加成',
                                                    '重击伤害加成', '共鸣解放伤害加成',
                                                    '共鸣技能伤害加成']}
        self.config_description = {
            '必须有双爆': '如果开启，声骸最终必须同时拥有暴击和暴击伤害。如果剩余孔位不足以凑齐双爆，则丢弃',
            '双爆出现之前必须全有效词条': '开启后，在暴击或暴击伤害词条出现之前，前面的所有词条必须都在有效词条列表中',
            '双爆总计>=': '当声骸同时存在暴击和爆伤时，需要满足 暴击 + (爆伤/2) >= 此数值',
            '首条双爆>=': '仅检查第一条出现的暴击或暴击伤害是否满足条件, 爆伤/2',
            '有效词条>=': '声骸满级时需达到的有效词条数量，若剩余孔位无法凑齐该数量，则停止强化并丢弃',
            '第一条必须为有效词条': '如果开启，第一个副词条必须在有效词条列表中且符合数值要求，否则直接丢弃',
            '有效词条': '定义哪些属性被视为有效',
            '同步到EchoSight': '如果开启，在强化提取词条后会自动推送数据到本地 8192 端口供 WuWa_Echo_Sight 记录',
        }

    def find_echo_enhance(self):
        return self.ocr(0.82, 0.86, 0.97, 0.96, match='培养')

    def is_0_level(self):
        return self.ocr(0.65, 0.35, 1, 0.57, match=re.compile('声骸技能'))

    def run(self):
        self.info_set('成功声骸数量', 0)
        self.info_set('失败声骸数量', 0)
        clear_folder('screenshots')
        while True:
            enhance = self.find_echo_enhance()
            if not enhance:
                raise Exception('必须在背包声骸界面过滤后开始!')
            current_level = self.is_0_level()
            if not current_level:
                total = self.info_get('成功声骸数量') + self.info_get('失败声骸数量')
                if self.debug:
                    self.screenshot('无可强化声骸')
                self.log_info(f'无可强化声骸, 任务结束! 强化{total}个, 符合条件{self.info_get("成功声骸数量")}个',
                              notify=True)
                if self.info_get('成功声骸数量') >= 1:
                    try:
                        os.startfile(os.path.abspath("screenshots"))
                    except Exception as e:
                        self.log_error(f"无法打开截图文件夹: {e}")
                return
            start = time.time()
            while time.time() - start < 5:
                if enhance:
                    import uuid
                    try:
                        nickname_texts = self.ocr(1750/2560, 165/1440, 2450/2560, 215/1440)
                        main_stat_texts = self.ocr(1840/2560, 570/1440, 2450/2560, 620/1440)
                        cost_texts = self.ocr(2250/2560, 175/1440, 2550/2560, 425/1440)
                        
                        base_nickname = nickname_texts[0].name if nickname_texts else "未知声骸"
                        self.current_nickname = f"{base_nickname}_{uuid.uuid4().hex[:6]}"
                        
                        self.current_main_stat = main_stat_texts[0].name if main_stat_texts else "未识别主词条"
                        
                        cost_str = ""
                        has_cost_word = False
                        if cost_texts:
                            for t in cost_texts:
                                cost_str += str(t.name)
                                if 'COST' in str(t.name).upper() or '0' in str(t.name) or '+' in str(t.name):
                                    has_cost_word = True
                        
                        match = re.search(r'[134lI\|]', cost_str)
                        if match:
                            val = match.group(0)
                            if val in ['3', '4']:
                                self.current_cost = int(val)
                            else:
                                self.current_cost = 1
                        elif has_cost_word:
                            # PaddleOCR consistently drops the single bare vertical line '1' as noise
                            # But reliably recognizes the thick '3' and '4'.
                            # If we see "COST" or "+0" but no number, it's virtually guaranteed to be a 1-cost.
                            self.current_cost = 1
                        else:
                            self.current_cost = 4
                        
                        logger.debug(f"[EchoSight准备] 识别到名称: {self.current_nickname} | 主词条: {self.current_main_stat} | Cost: {self.current_cost}")
                    except Exception as e:
                        logger.error(f"[EchoSight准备] 读取基础数据失败: {e}")
                        self.current_nickname = f"未知声骸_{uuid.uuid4().hex[:6]}"
                        self.current_main_stat = "未识别主词条"
                        self.current_cost = 4
                
                    self.current_echo_id = f"auto_enh_{str(uuid.uuid4())}"
                    self.click(enhance, after_sleep=0.5)
                enhance = self.find_echo_enhance()
                if not enhance:
                    break

            while True:
                start_wait = time.time()
                have_add_mat = False
                while time.time() - start_wait < 5:
                    add_mat = self.find_add_mat()
                    if add_mat:
                        have_add_mat = True
                        self.click(add_mat, after_sleep=0.3)
                    else:
                        self.next_frame()
                        if have_add_mat:
                            break
                if not have_add_mat:
                    raise Exception('强化设置需要开启阶段放入!')

                if not self.wait_click_ocr(0.17, 0.88, 0.29, 0.96, match=['强化并调谐'],
                                           settle_time=0.1,
                                           after_sleep=1.5):
                    if self.ocr(0.17, 0.88, 0.29, 0.96, match=['强化']):
                        raise Exception('强化设置需要开启同步调谐!')
                    else:
                        raise Exception('找不到 强化并调谐!')
                while handle := self.wait_ocr(0.24, 0.18, 0.75, 0.93,
                                              match=[re.compile('不再提示'), '调谐成功', re.compile('点击任')],
                                              time_out=2):
                    if handle[0].name in ['本次登录不再提示', '本次登入不再提示']:
                        click = handle[0]
                        click.width = 1
                        click.x -= click.height * 1.1
                        self.click(click, after_sleep=0.5)
                        self.click(self.find_confirm(), after_sleep=0.5)
                    elif handle[0].name in ['点击任意位置返回', '调谐成功']:
                        self.click(handle, after_sleep=1)
                    else:
                        self.sleep(0.5)
                self.sleep(0.1)
                texts = self.ocr(0.09, 0.28, 0.40, 0.53)
                self.log_info(f'ocr values: {texts}')
                properties = [p for p in self.find_boxes(texts, match=property_pattern) if '辅音' not in p.name]
                for p in properties:
                    match = property_pattern.search(p.name)
                    if match:
                        p.name = match.group()
                values = self.find_boxes(texts, match=number_pattern)
                self.info_set('属性', properties)
                self.info_set('值', values)

                is_valid = self.check_echo_stats(properties, values)
                
                if hasattr(self, 'last_paired_stats') and self.config.get('同步到EchoSight', True):
                    safe_sync_to_echo_sight(self.last_paired_stats, status="tracking", cost_class=getattr(self, "current_cost", 4), main_stat_key=getattr(self, "current_main_stat", "crit_rate"), nickname=getattr(self, "current_nickname", "未知声骸"), echo_id=getattr(self, "current_echo_id", None))

                if not is_valid:
                    if hasattr(self, 'last_paired_stats') and self.config.get('同步到EchoSight', True):
                        safe_sync_to_echo_sight(self.last_paired_stats, status="abandoned", cost_class=getattr(self, "current_cost", 4), main_stat_key=getattr(self, "current_main_stat", "crit_rate"), nickname=getattr(self, "current_nickname", "未知声骸"), echo_id=getattr(self, "current_echo_id", None))
                    self.trash_and_esc()
                    break

                if len(properties) >= 5:
                    if hasattr(self, 'last_paired_stats') and self.config.get('同步到EchoSight', True):
                        safe_sync_to_echo_sight(self.last_paired_stats, status="completed", cost_class=getattr(self, "current_cost", 4), main_stat_key=getattr(self, "current_main_stat", "crit_rate"), nickname=getattr(self, "current_nickname", "未知声骸"), echo_id=getattr(self, "current_echo_id", None))
                    self.lock_and_esc()
                    break

    def find_confirm(self):
        box = self.box_of_screen(0.24, 0.18, 0.75, 0.93)
        self.screenshot('find_confirm', frame=box.crop_frame(self.frame))
        return self.ocr(box=box, match='确认')

    def check_echo_stats(self, properties, values):
        self.fail_reason = ""
        invalid_count = 0

        paired_stats = []
        unmatched_values = values.copy()
        for prop in properties:
            matched_val_text = "0"
            if unmatched_values:
                closest_val = min(unmatched_values, key=lambda v: abs(prop.y - v.y))
                matched_val_text = closest_val.name
                unmatched_values.remove(closest_val)
            paired_stats.append((prop.name, matched_val_text))

        total_count = len(paired_stats)
        self.last_paired_stats = paired_stats

        crit_rate_val = 0
        crit_dmg_val = 0
        has_crit_rate = False
        has_crit_dmg = False

        checked_first_crit = False
        has_encountered_crit = False

        valid_stats = self.config.get('有效词条') or []

        for p_raw, v_str in paired_stats:
            p = p_raw
            if '暴击伤害' in p:
                p = '暴击伤害'
            elif '暴击' in p:
                p = '暴击'
            elif '攻击' in p:
                p = '攻击' + ('百分比' if '%' in v_str or '％' in v_str else '')
            elif '生命' in p:
                p = '生命' + ('百分比' if '%' in v_str or '％' in v_str else '')
            elif '防御' in p:
                p = '防御' + ('百分比' if '%' in v_str or '％' in v_str else '')
            elif '效率' in p:
                p = '共鸣效率'
            elif '普攻' in p:
                p = '普攻伤害加成'
            elif '重击' in p:
                p = '重击伤害加成'
            elif '解放' in p:
                p = '共鸣解放伤害加成'
            elif '技能' in p:
                p = '共鸣技能伤害加成'

            v = parse_number(v_str)

            is_valid_prop = True
            is_crit_stat = p in ['暴击', '暴击伤害']

            if self.config.get(
                    '双爆出现之前必须全有效词条') and '暴击' in valid_stats and '暴击伤害' in valid_stats and not has_encountered_crit:
                if not is_crit_stat:
                    if p not in valid_stats:
                        self.fail_reason = f'双爆前含无效_{p}'
                        self.log_info(f'双爆出现前存在无效词条 {p}, 丢弃')
                        return False
                else:
                    has_encountered_crit = True

            if is_valid_prop and p not in valid_stats:
                is_valid_prop = False
                self.log_debug(f'非有效词条, {p} 不符合条件')

            if p == '暴击':
                has_crit_rate = True
                crit_rate_val += v
                if '暴击' in valid_stats and not checked_first_crit:
                    checked_first_crit = True
                    if v < self.config.get('首条双爆>='):
                        self.fail_reason = f'首条暴击不足_{v}'
                        self.log_info(f'首条暴击 {v} < {self.config.get("首条双爆>=")}，丢弃')
                        return False

            elif p == '暴击伤害':
                has_crit_dmg = True
                crit_dmg_val += v
                if '暴击伤害' in valid_stats and not checked_first_crit:
                    checked_first_crit = True
                    if v / 2 < self.config.get('首条双爆>='):
                        self.fail_reason = f'首条爆伤不足_{v}'
                        self.log_info(f'首条爆伤 {v} < {self.config.get("首条双爆>=")}，丢弃')
                        return False

            if not is_valid_prop:
                invalid_count += 1

        self.info_set('不符合条件属性', invalid_count)

        if self.config.get('必须有双爆'):
            missing_crit = (0 if has_crit_rate else 1) + (0 if has_crit_dmg else 1)
            remaining_slots = 5 - total_count
            if remaining_slots < missing_crit:
                self.fail_reason = f'无法凑齐双爆_缺{missing_crit}'
                self.log_info(f'无法凑齐双爆 (缺{missing_crit}种, 剩{remaining_slots}孔), 丢弃')
                return False

        if has_crit_rate and has_crit_dmg:
            total_score = crit_rate_val + (crit_dmg_val / 2)
            if total_score < self.config.get('双爆总计>='):
                self.fail_reason = f'双爆总计不足_{total_score:.1f}'
                self.log_info(f'双爆总计 {total_score:.1f} < {self.config.get("双爆总计>=")}，丢弃')
                return False

        if total_count == 1 and self.config.get('第一条必须为有效词条') and invalid_count == 1:
            self.fail_reason = '首条无效'
            self.log_info('第一条必须为有效词条, 丢弃')
            return False

        valid_count = total_count - invalid_count
        remaining_slots = 5 - total_count
        if (valid_count + remaining_slots) < self.config.get('有效词条>='):
            self.fail_reason = f'有效词条不足_上限{valid_count + remaining_slots}'
            self.log_info(f'剩余孔位不足以达到设定的有效词条数量, 丢弃')
            return False

        return True

    def find_add_mat(self):
        return self.wait_ocr(0.09, 0.6, 0.38, 0.86, match=['阶段放入'], time_out=1)

    def esc(self):
        start = time.time()
        while not self.find_echo_enhance() and time.time() - start < 10:
            self.send_key('esc', interval=4, after_sleep=0.2)
        self.sleep(0.1)

    def trash_and_esc(self):
        self.info_incr('失败声骸数量')
        start = time.time()
        success = False
        while time.time() - start < 5:
            drop_status = self.find_best_match_in_box(self.get_box_by_name('echo_dropped').scale(1.05),
                                                      ['echo_dropped', 'echo_not_dropped'], threshold=0.7)
            if not drop_status:
                raise Exception('无法找到声骸弃置状态!')
            if drop_status.name == 'echo_not_dropped':
                self.send_key('z', after_sleep=1)
            else:
                self.log_info('成功弃置!')
                success = True
                break
        if not success:
            raise Exception('弃置失败!')
        safe_reason = re.sub(r'[<>:"/\\|?*]', '', self.fail_reason)
        self.screenshot_echo(f'failed/{self.info_get("失败声骸数量")}_{safe_reason}')
        self.esc()
        self.log_info('不符合条件 丢弃')
        self.wait_ocr(0.82, 0.86, 0.97, 0.96, match='培养', settle_time=0.1)

    def screenshot_echo(self, name):
        echo = self.box_of_screen(0.09, 0.09, 0.37, 0.55).crop_frame(self.frame)
        self.screenshot(name=name, frame=echo)

    def lock_and_esc(self):
        self.info_incr('成功声骸数量')
        start = time.time()
        success = False
        while time.time() - start < 5:
            drop_status = self.find_best_match_in_box(self.get_box_by_name('echo_locked').scale(1.05),
                                                      ['echo_locked', 'echo_not_locked'], threshold=0.7)
            if not drop_status:
                raise Exception('无法找到声骸上锁状态!')
            if drop_status.name == 'echo_not_locked':
                self.send_key('c', after_sleep=1)
            else:
                self.log_info('成功弃置!')
                success = True
                break
        if not success:
            raise Exception('上锁失败!')
        self.screenshot_echo(f'success/{self.info_get("成功声骸数量")}')
        self.log_info('成功并上锁')
        self.esc()
        self.wait_ocr(0.82, 0.86, 0.97, 0.96, match='培养', settle_time=0.1)


def parse_number(text):
    try:
        return float(text.replace('％', '%').split('%')[0])
    except (ValueError, IndexError):
        return 0.0










