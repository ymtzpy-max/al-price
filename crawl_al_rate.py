import os
import re
import json
from datetime import datetime
import tushare as ts
import requests
from pathlib import Path

# ===================== 全局基础配置 =====================
# 数据文件
JSON_SAVE_PATH = Path("./daily_price.json")
TXT_LOG_PATH = Path("./price_log.txt")
# 中行汇率页面
BOC_URL = "https://www.boc.cn/sourcedb/whpj/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9"
}

# 读取Tushare Token，禁止硬编码
TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN", "")
if not TUSHARE_TOKEN:
    raise RuntimeError("环境变量 TUSHARE_TOKEN 未注入，请检查Actions Secrets配置")
ts.set_token(TUSHARE_TOKEN)
pro = ts.pro_api()

# 当日全局缓存变量
global_cache = {
    "today_trade_date": datetime.now().strftime("%Y-%m-%d"),
    "shfe_1015_price": None,
    "usd_cny_buy_rate": None
}

# ===================== 工具函数 =====================
def get_cst_now() -> datetime:
    """获取当前北京时间"""
    return datetime.now()

def write_runtime_log(content: str):
    """写入简易运行日志到txt尾部"""
    now_str = get_cst_now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{now_str}] {content}\n"
    with open(TXT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line)

def fetch_boc_usd_buy_rate() -> float:
    """抓取中国银行美元现汇买入价，返回 1USD=XXX CNY"""
    try:
        resp = requests.get(BOC_URL, headers=HEADERS, timeout=20)
        resp.encoding = "utf-8"
        html = resp.text
        pattern = re.compile(r"美元.*?现汇买入价.*?(\d+\.\d+)", re.S)
        match_ret = pattern.search(html)
        if not match_ret:
            write_runtime_log("汇率抓取失败：页面未匹配到美元现汇买入价")
            return 0.0
        hundred_usd_val = float(match_ret.group(1))
        rate = round(hundred_usd_val / 100, 4)
        write_runtime_log(f"成功抓取当日中行USD现汇买入价：{rate}")
        return rate
    except Exception as e:
        err_msg = f"汇率接口异常：{str(e)}"
        write_runtime_log(err_msg)
        return 0.0

def get_shfe_al_close() -> float | None:
    """Tushare获取上期所沪铝当日日线收盘价，锁定10:15休市基准价"""
    try:
        df = pro.get_shfe_daily(symbol="al", trade_date=global_cache["today_trade_date"])
        if df.empty:
            write_runtime_log("上期所沪铝当日行情数据为空")
            return None
        close_price = float(df.iloc[0]["close"])
        global_cache["shfe_1015_price"] = close_price
        write_runtime_log(f"同步缓存上期所10:15基准收盘价：{close_price} 元/吨")
        return close_price
    except Exception as e:
        write_runtime_log(f"上期所数据拉取异常：{str(e)}")
        return None

def get_smm_spot_basis() -> dict:
    """Tushare拉取SMM铝现货价格、基差"""
    try:
        df = pro.futures_spot_price(prod_code="al", trade_date=global_cache["today_trade_date"])
        if df.empty:
            write_runtime_log("SMM现货基差数据为空")
            return {}
        row = df.iloc[0]
        spot_data = {
            "spot_price": float(row["spot_price"]),
            "basis": float(row["basis"]),
            "source": "SMM",
            "bind_ref_price": "上期所10:15早盘收盘价格"
        }
        write_runtime_log(f"SMM现货：{spot_data['spot_price']} 元/吨，基差：{spot_data['basis']} 元/吨")
        return spot_data
    except Exception as e:
        write_runtime_log(f"SMM现货接口异常：{str(e)}")
        return {}

def save_full_data(shfe_price: float, spot_info: dict, fx_rate: float):
    """
    1. 写入结构化JSON归档；
    2. 格式化写入price_log.txt明细台账；
    """
    cst_now = get_cst_now().strftime("%Y-%m-%d %H:%M:%S")
    trade_dt = global_cache["today_trade_date"]

    # 组装单条结构化数据
    record_item = {
        "record_cst_time": cst_now,
        "trade_date": trade_dt,
        "shfe_al_1015_close": shfe_price,
        "smm_spot_detail": spot_info,
        "boc_usd_cny_buy_rate": fx_rate,
        "rate_collect_window": "当日10:18~10:22一次性抓取",
        "remark": "汇率、期价、现货三者绑定固化，历史核算固定取值"
    }

    # 写入JSON
    history_data = []
    if JSON_SAVE_PATH.exists():
        with open(JSON_SAVE_PATH, "r", encoding="utf-8") as f:
            history_data = json.load(f)
    # 剔除当日旧数据，防止重复
    history_data = [item for item in history_data if item["trade_date"] != trade_dt]
    history_data.append(record_item)
    with open(JSON_SAVE_PATH, "w", encoding="utf-8") as f:
        json.dump(history_data, f, ensure_ascii=False, indent=2)

    # 格式化写入price_log.txt
    log_text = f"""
=============================================
采集北京时间：{cst_now}
交易日：{trade_dt}
上期所沪铝10:15基准收盘：{shfe_price} 元/吨
SMM现货报价：{spot_info.get('spot_price', 0)} 元/吨
现货基差：{spot_info.get('basis', 0)} 元/吨
中国银行USD现汇买入汇率：{fx_rate}
=============================================
"""
    with open(TXT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(log_text)

    write_runtime_log("当日全套数据已完成归档（JSON+price_log.txt）")

# ===================== 主时序调度逻辑 =====================
def main():
    now = get_cst_now()
    hour = now.hour
    minute = now.minute
    current_time_tag = f"{hour:02d}:{minute:02d}"
    write_runtime_log(f"定时任务触发，当前北京时间：{current_time_tag}")

    # 10:30之后直接终止任务
    if hour > 10 or (hour == 10 and minute > 30):
        write_runtime_log("已超出10:00~10:30采集窗口期，程序直接退出")
        return

    # 优先拉取并缓存上期所价格
    get_shfe_al_close()
    base_shfe_price = global_cache["shfe_1015_price"]
    if base_shfe_price is None:
        write_runtime_log("无有效上期所基准价格，本次不执行归档")
        return

    # 分时段逻辑控制
    if 0 <= minute <= 17:
        # 10:00~10:17：仅缓存期货，不抓现货、汇率
        write_runtime_log("当前时段10:00-10:17，仅缓存上期所价格，跳过现货与汇率采集")

    elif 18 <= minute <= 22:
        # 核心窗口期：抓取现货+一次性抓取汇率，全量归档
        write_runtime_log("进入核心采集窗口10:18-10:22，开始拉取SMM现货与美元汇率")
        spot_result = get_smm_spot_basis()
        if not spot_result:
            write_runtime_log("SMM现货数据缺失，终止本次完整归档")
            return
        # 只抓取一次汇率并全局缓存
        if global_cache["usd_cny_buy_rate"] is None:
            global_cache["usd_cny_buy_rate"] = fetch_boc_usd_buy_rate()
        fx_final = global_cache["usd_cny_buy_rate"]
        # 双文件落地保存
        save_full_data(base_shfe_price, spot_result, fx_final)

    elif 23 <= minute <= 30:
        # 10:23~10:30：当日现货、汇率已锁定，不再重复采集
        write_runtime_log("当前时段10:23-10:30，当日现货与汇率已锁定，无需重复采集")

if __name__ == "__main__":
    main()
