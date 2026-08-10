import json
from datetime import datetime
import akshare as ak
from pathlib import Path

# ===================== 全局配置 =====================
JSON_SAVE_PATH = Path("./daily_price.json")
TXT_LOG_PATH = Path("./price_log.txt")

global_cache = {
    "today_trade_date": datetime.now().strftime("%Y-%m-%d"),
    "shfe_1015_price": None,
    "usd_buy_rate": None
}

def get_cst_now() -> datetime:
    return datetime.now()

def write_runtime_log(content: str):
    """运行日志写入txt"""
    now_str = get_cst_now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{now_str}] {content}\n"
    with open(TXT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line)

# 1、获取中行美元现汇买入价
def get_boc_usd_buy_rate() -> float:
    try:
        df = ak.currency_boc_sina()
        usd_row = df[df["货币名称"] == "美元"]
        if usd_row.empty:
            write_runtime_log("汇率获取失败：未找到美元牌价")
            return 0.0
        # 页面单位：100外币兑换人民币，换算成1USD兑CNY
        rate = round(float(usd_row["现汇买入价"].iloc[0]) / 100, 4)
        global_cache["usd_buy_rate"] = rate
        write_runtime_log(f"中行USD现汇买入价：{rate}")
        return rate
    except Exception as e:
        write_runtime_log(f"汇率接口异常：{str(e)}")
        return 0.0

# 2、上期所沪铝价格（修复，替换废弃接口）
def get_shfe_al_price() -> float | None:
    try:
        df = ak.futures_zh_realtime(symbol="沪铝")
        if df.empty:
            write_runtime_log("上期所沪铝当日无行情数据")
            return None
        close_price = float(df.iloc[0]["最新"])
        global_cache["shfe_1015_price"] = close_price
        write_runtime_log(f"沪铝10:15基准价：{close_price} 元/吨")
        return close_price
    except Exception as e:
        write_runtime_log(f"上期所数据异常：{str(e)}")
        return None

# 3、SMM铝现货价格，仅提取现货价，舍弃基差
def get_smm_al_spot_price() -> float | None:
    try:
        df = ak.futures_spot_price(prod_code="al", trade_date=global_cache["today_trade_date"])
        if df.empty:
            write_runtime_log("SMM现货数据为空")
            return None
        spot_price = float(df.iloc[0]["spot_price"])
        write_runtime_log(f"SMM铝现货报价：{spot_price} 元/吨")
        return spot_price
    except Exception as e:
        write_runtime_log(f"SMM现货接口异常：{str(e)}")
        return None

# 数据落地：JSON归档 + 文本日志
def save_all_data(fut_price: float, spot_price: float, fx_rate: float):
    cst_now = get_cst_now().strftime("%Y-%m-%d %H:%M:%S")
    trade_dt = global_cache["today_trade_date"]

    # 结构化JSON，只保留你需要的字段
    record = {
        "collect_time": cst_now,
        "trade_date": trade_dt,
        "shfe_al_1015_price": fut_price,
        "smm_spot_price": spot_price,
        "boc_usd_cny_buy": fx_rate,
        "collect_period": "当日10:18~10:22一次性采集固化"
    }

    # 写入JSON，剔除当日重复数据
    history = []
    if JSON_SAVE_PATH.exists():
        with open(JSON_SAVE_PATH, "r", encoding="utf-8") as f:
            history = json.load(f)
    history = [item for item in history if item["trade_date"] != trade_dt]
    history.append(record)
    with open(JSON_SAVE_PATH, "w", encoding="utf-8") as f:
        json.dump(history, ensure_ascii=False, indent=2)

    # 格式化写入price_log.txt
    log_content = f"""
=============================================
采集时间：{cst_now}
交易日：{trade_dt}
上期所沪铝10:15价格：{fut_price} 元/吨
SMM铝现货报价：{spot_price} 元/吨
中国银行美元现汇买入汇率：{fx_rate}
=============================================
"""
    with open(TXT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(log_content)

    write_runtime_log("当日全部数据归档完成（JSON + price_log.txt）")

# 主定时时序逻辑
def main():
    now = get_cst_now()
    hour = now.hour
    minute = now.minute
    current_time = f"{hour:02d}:{minute:02d}"
    write_runtime_log(f"定时任务触发，当前北京时间：{current_time}")

    # 超过10:30直接退出
    if hour > 10 or (hour == 10 and minute > 30):
        write_runtime_log("超出10:00~10:30采集时段，程序退出")
        return

    # 先拉取期货价格缓存
    get_shfe_al_price()
    fut_price = global_cache["shfe_1015_price"]
    if fut_price is None:
        write_runtime_log("无有效期货价格，本次不归档")
        return

    # 分时段控制
    if 0 <= minute <= 17:
        write_runtime_log("10:00-10:17，仅缓存期货价格，暂不采集现货、汇率")

    elif 18 <= minute <= 22:
        write_runtime_log("进入核心采集窗口10:18-10:22，采集现货+汇率")
        spot_price = get_smm_al_spot_price()
        if spot_price is None:
            write_runtime_log("现货数据缺失，终止归档")
            return
        if global_cache["usd_buy_rate"] is None:
            get_boc_usd_buy_rate()
        fx_rate = global_cache["usd_buy_rate"]
        save_all_data(fut_price, spot_price, fx_rate)

    elif 23 <= minute <= 30:
        write_runtime_log("10:23-10:30，当日数据已锁定，无需重复采集")

if __name__ == "__main__":
    main()
