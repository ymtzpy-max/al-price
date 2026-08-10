import akshare as ak
import json
from datetime import datetime

def get_smm_a00_al():
    # 获取SMM所有金属现货报价
    df = ak.metal_smm_aluminum_spot()
    # 筛选SMM A00铝，取均价
    target_row = df[df["品种"] == "SMM A00铝"].iloc[0]
    return float(target_row["均价"])

def get_usd_boc_rate():
    # 获取中行美元牌价，最新一条现汇买入价
    df = ak.currency_boc_sina(symbol="美元")
    latest = df.iloc[-1]
    raw = float(latest["现汇买入价"])
    # 中行单位100外币，换算真实汇率
    return raw / 100

def save_data(al_price, usd_rate):
    now = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    today = datetime.now().strftime("%Y-%m-%d")
    log_line = f"【{now}】日期：{today}｜美元现汇买入价：{usd_rate:.4f}｜SMM A00铝10:15报价均价：{al_price:.0f}\n"

    # 写入文本日志
    with open("price_log.txt", "a", encoding="utf-8") as f:
        f.write(log_line)

    # 写入结构化JSON
    record = {"date": today, "usdRate": usd_rate, "smmSpot": al_price}
    try:
        with open("daily_price.json", "r", encoding="utf-8") as f:
            data = json.load(f)
    except:
        data = []
    # 同一天覆盖旧记录
    update = False
    for item in data:
        if item["date"] == today:
            item.update(record)
            update = True
            break
    if not update:
        data.append(record)
    with open("daily_price.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(log_line)

if __name__ == "__main__":
    try:
        al = get_smm_a00_al()
        rate = get_usd_boc_rate()
        save_data(al, rate)
    except Exception as e:
        print("抓取失败：", str(e))
