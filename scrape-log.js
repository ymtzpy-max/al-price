const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

(async () => {
  let spot, fut, rate;
  // 启动浏览器，加载登录缓存auth.json
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ storageState: "./auth.json" });

  try {
    // 1. 抓取SMM分时页面，匹配10:15行
    const pageSmm = await ctx.newPage();
    // 替换成你自己SMM分时完整URL
    await pageSmm.goto("SMM分时报价网页地址", { timeout: 40000 });
    await pageSmm.waitForTimeout(4000);
    const rows = await pageSmm.locator("table tr").all();
    for (const tr of rows) {
      const tds = await tr.locator("td").allTextContents();
      const arr = tds.map(t => t.trim());
      if (arr.includes("10:15")) {
        spot = Number(arr[1]);
        fut = Number(arr[2]);
        break;
      }
    }
    await pageSmm.close();

    // 2. 抓取银行美元现汇买入价，替换银行页面地址
    const pageBank = await ctx.newPage();
    await pageBank.goto("银行外汇牌价页面URL");
    // 这里后面本地调试改选择器
    const rateText = await pageBank.locator("body").textContent();
    rate = Number(rateText.match(/现汇买入价[:：](\d+\.\d+)/)[1]);
    await pageBank.close();
  } finally {
    await browser.close();
  }

  // 价格区间校验，异常不写入日志
  if (!spot || !fut || !rate || spot < 18000 || spot > 28000 || rate < 6 || rate > 8) {
    console.log("今日数据抓取异常，放弃保存");
    process.exit(1);
  }

  // 生成日期
  const today = new Date().toLocaleDateString("zh-CN").replace(/\//g, "-");
  const fullTime = new Date().toLocaleString("zh-CN");
  // 1. 追加纯文本日志
  const logLine = `【${fullTime}】日期：${today}｜现汇买入价：${rate}｜SMM10:15现货：${spot}｜SMM10:15期货：${fut}\n`;
  fs.appendFileSync("./price_log.txt", logLine, "utf8");

  // 2. 结构化json记录
  let jsonArr = [];
  if (fs.existsSync("./daily_price.json")) {
    const raw = fs.readFileSync("./daily_price.json", "utf8");
    jsonArr = JSON.parse(raw);
  }
  const record = { date: today, usdRate: rate, smmSpot: spot, smmFut: fut };
  const idx = jsonArr.findIndex(item => item.date === today);
  idx > -1 ? (jsonArr[idx] = record) : jsonArr.push(record);
  fs.writeFileSync("./daily_price.json", JSON.stringify(jsonArr, null, 2), "utf8");
  console.log("抓取完成，日志已更新");
})();
