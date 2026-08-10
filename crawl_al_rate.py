from datetime import datetime
import csv
import os
import time

# ====================== 配置参数（北京时间）======================
SAVE_CSV = "al_daily_basis.csv"

# 总采集窗口：10:00 ~ 10:30
WINDOW_START_H, WINDOW_START_M = 10, 0
WINDOW_END_H, WINDOW_END_M = 10, 30

# SMM现货抓取窗口：10:18～10:22（给后台5分钟刷新缓冲）
SPOT_TARGET_H, SPOT_TARGET_M = 10, 20
SPOT_TIME_TOLERANCE = 2

# =================================================================

def current_total_minute(dt: datetime) -> int:
    """把时分换算成当日总分钟数"""
    return dt.hour * 60 + dt.minute

def is_in_valid_window(dt: datetime) -> bool:
    """校验是否处于 10:00 ~ 10:30"""
    now_min = current_total_minute(dt)
    start_min = WINDOW_START_H * 60 + WINDOW_START_M
    end_min = WINDOW_END_H * 60 + WINDOW_END_M
    return start_min <= now_min < end_min

def can_fetch_spot(dt: datetime) -> bool:
    """判断是否进入现货专属抓取区间"""
    now_min = current_total_minute(dt)
    target_min = SPOT_TARGET_H * 60 + SPOT_TARGET_M
    return abs(now_min - target_min) <= SPOT_TIME_TOLERANCE

def get_future_price():
    """
    【此处替换为你真实沪铝期货接口】
    10:15之后行情冻结，拿到的就是10:15基准收盘价
    """
    now_dt = datetime.now()
    remark = "10:15早盘休市锁定基准价" if current_total_minute(now_dt) >= 10*60+15 else "10:00-10:14盘中实时行情"
    return {
        "collect_time": now_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "category": "future",
        "price": 0.0,
        "remark": remark
    }

def get_spot_price():
    """
    【此处替换SMM铝现货官方接口】
    仅10:18~10:22执行，取依托10:15期货更新的当日现货定价
    """
    time.sleep(2)
    now_dt = datetime.now()
    return {
        "collect_time": now_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "category": "spot",
        "price": 0.0,
        "remark": "当日现货基准价，绑定10:15期货收盘数据"
    }

def init_csv_header():
    """文件不存在则初始化表头"""
    if not os.path.exists(SAVE_CSV):
        headers = ["collect_time", "category", "price", "remark"]
        with open(SAVE_CSV, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(headers)

def write_data_row(data: dict):
    """追加一行数据写入CSV"""
    row = [
        data["collect_time"],
        data["category"],
        data["price"],
        data["remark"]
    ]
    with open(SAVE_CSV, "a", encoding="utf-8", newline="") as f:
        csv.writer(f).writerow(row)

def main():
    init_csv_header()
    now = datetime.now()
    print(f"===== 本轮执行时间：{now.strftime('%Y-%m-%d %H:%M:%S')} =====")

    # 不在10:00~10:30直接终止运行，不产生任何数据
    if not is_in_valid_window(now):
        print("当前不在 10:00~10:30 采集时段，退出程序")
        return

    # 只要在窗口内，必定采集并写入期货数据
    future_info = get_future_price()
    write_data_row(future_info)
    print(f"已写入期货数据：{future_info}")

    # 仅命中10:18~10:22才抓取现货，其余时段跳过现货
    if can_fetch_spot(now):
        spot_info = get_spot_price()
        write_data_row(spot_info)
        print(f"命中现货采集窗口，当日现货已入库：{spot_info}")
    else:
        print("未到现货抓取时间，跳过现货拉取")

if __name__ == "__main__":
    main()
